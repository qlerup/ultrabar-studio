"""Persistent drafts and conflict-checked profile deployment through LineOS."""
from copy import deepcopy
from datetime import datetime, timezone
import hashlib
import json
import re
import time
import uuid
import threading
from functools import wraps

from flask import jsonify, request, Response
import bridge
from library_icons import CoreIcons


class EditError(ValueError):
    pass


def wake_for_deploy(server, target):
    """Wake without toggling power; verify Android has left standby before writing."""
    try:
        server.adb('-s', target, 'shell', 'input', 'keyevent', '224')  # KEYCODE_WAKEUP
        for attempt in range(20):
            power = server.adb('-s', target, 'shell', 'dumpsys', 'power')
            if re.search(r'mWakefulness=Awake\b', power) and re.search(r'Display Power: state=ON\b', power):
                return
            if attempt < 19:
                time.sleep(.25)  # Wait for the asynchronous standby/display transition.
    except server.DeviceError as exc:
        raise server.DeviceError('Could not wake Core. No settings were sent. Wake the screen and try Deploy again.') from exc
    raise server.DeviceError('Core did not leave standby. No settings were sent. Wake the screen and try Deploy again.')


def clean(value):
    # Never pass Fastjson class selectors supplied by the browser to LineOS.
    if isinstance(value, dict):
        return {k: clean(v) for k, v in value.items() if k != '@type'}
    if isinstance(value, list):
        return [clean(v) for v in value]
    return value


def digest(profiles):
    return hashlib.sha256(json.dumps(clean(profiles), sort_keys=True, separators=(',', ':'), allow_nan=False).encode()).hexdigest()


def atomic_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix('.tmp')
    temp.write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False), encoding='utf-8')
    temp.replace(path)


def draft_path(server, device_id):
    return server.DATA_DIR / 'drafts' / (hashlib.sha256(device_id.encode()).hexdigest()+'.json')


def fresh_draft(snapshot):
    return dict(device_id=snapshot['device_id'], base_hash=digest(snapshot['profiles']),
                base_profiles=deepcopy(snapshot['profiles']), profiles=deepcopy(snapshot['profiles']),
                revision=uuid.uuid4().hex, saved_at=datetime.now(timezone.utc).isoformat(), background_apps=[])


def background_path(server,device):
    return draft_path(server,device).with_suffix('.background.json')


def saved_background(server,device):
    try:
        value=json.loads(background_path(server,device).read_text(encoding='utf-8'))
    except FileNotFoundError:return []
    except (OSError,ValueError) as exc:raise EditError('Could not read saved background apps. Existing data was preserved.') from exc
    validate_background(value)
    return value


def validate_background(value):
    import store
    import screen_sync
    if not isinstance(value,list) or len(value)>64:raise EditError('Choose at most 64 background apps.')
    seen=set()
    for app in value:
        if not isinstance(app,dict) or set(app)-{'id','name','settings'}:raise EditError('Invalid background app.')
        key=app.get('id')
        if not isinstance(key,str) or not store.ANDROID_ID.fullmatch(key) or key.startswith(('android.','com.android.','com.ultrabar.')) or key in seen:raise EditError('Invalid or duplicate background app.')
        seen.add(key)
        if not isinstance(app.get('name'),str) or not 1<=len(app['name'])<=100:raise EditError('Give each background app a name.')
        settings=app.get('settings',{})
        if key==screen_sync.PACKAGE_ID:screen_sync.validate_settings(settings)
        elif not isinstance(settings,dict) or set(settings)-{'launch'} or type(settings.get('launch',True)) is not bool:raise EditError('Invalid background app settings.')


def load_draft(server, snapshot):
    path = draft_path(server, snapshot['device_id'])
    if path.exists():
        draft=json.loads(path.read_text(encoding='utf-8'))
        if 'background_apps' not in draft:draft['background_apps']=saved_background(server,snapshot['device_id'])
        return draft
    draft = fresh_draft(snapshot)
    draft['background_apps']=saved_background(server,snapshot['device_id'])
    atomic_json(path, draft)
    return draft


def validate(profiles, base):
    if not isinstance(profiles, list) or not 1 <= len(profiles) <= 64 or any(not isinstance(p, dict) for p in profiles):
        raise EditError('A draft must contain between 1 and 64 profiles.')
    if [p.get('id') for p in profiles] != [p.get('id') for p in base]:
        raise EditError('Keep the existing profiles and their IDs. Profile creation/removal is not supported yet.')
    if sum(p.get('default') is True for p in profiles) != 1:
        raise EditError('Exactly one profile must be the default.')
    for p, original in zip(profiles, base):
        if not isinstance(p.get('name'), str) or not 1 <= len(p['name'].strip()) <= 100:
            raise EditError('Give each profile a name of 1–100 characters.')
        widgets, modules = p.get('homeData'), p.get('module')
        if not isinstance(widgets, list) or len(widgets) > 128 or not isinstance(modules, list) or len(modules) > 128:
            raise EditError('Invalid widget or module list (maximum 128 each).')
        ids = set()
        original_widgets = {w['id']: w for w in original.get('homeData', [])}
        for w in widgets:
            if not isinstance(w, dict) or not isinstance(w.get('id'), str) or not w['id'] or not isinstance(w.get('type'), str):
                raise EditError('Each widget needs an ID and type.')
            if w['id'] in ids:
                raise EditError('The same widget cannot appear twice in a profile.')
            ids.add(w['id'])
            if w['type'] not in ('CPU', 'MEMORY', 'STORAGE', 'TIME', 'APPS', 'PC_CONTROL') and w != original_widgets.get(w['id']):
                raise EditError('This widget type can be preserved and reordered, but cannot be created or edited yet.')
            if 'name' in w and (not isinstance(w['name'], str) or len(w['name']) > 100):
                raise EditError('Widget names must contain at most 100 characters.')
            if 'bgColor' in w and w['bgColor'] and not re.fullmatch(r'#[0-9a-fA-F]{6}([0-9a-fA-F]{2})?', w['bgColor']):
                raise EditError('Widget colors must be hexadecimal colors.')
            if type(w.get('iconScale', 100)) is not int or not 0 <= w.get('iconScale', 100) <= 200:
                raise EditError('Icon size must be between 0 and 200 percent.')
        serials = set()
        for m in modules:
            if not isinstance(m, dict) or not isinstance(m.get('serialNo'), str) or not re.fullmatch(r'[0-9a-fA-F]{16}', m['serialNo']):
                raise EditError('Invalid module serial number.')
            if m['serialNo'] in serials:
                raise EditError('A module can only appear once in each profile.')
            serials.add(m['serialNo'])
            if not isinstance(m.get('config'), (list, dict)):
                raise EditError('Invalid module configuration.')
            if m.get('productId') not in ('DOT_KEY', 'VIVO_CUBE', 'KNOB_KEY', 'SENSE_CUBE'):
                if m not in original.get('module', []):
                    raise EditError('This module type can only be preserved unchanged.')
            elif m['productId'] == 'KNOB_KEY':
                if not isinstance(m['config'], dict):
                    raise EditError('KnobKey configuration must be an object.')
            else:
                if not isinstance(m['config'], list) or len(m['config']) > 128:
                    raise EditError('Module inputs must be a list of at most 128 slots.')
                key = 'mode' if m['productId'] == 'SENSE_CUBE' else 'keyCode'
                keys = set()
                for slot in m['config']:
                    if not isinstance(slot, dict) or type(slot.get(key)) is not int or slot[key] in keys:
                        raise EditError('Each module input needs a unique numeric key.')
                    keys.add(slot[key])
        # Keep slot records when clearing actions: omitting them leaves old scenes in runtime.
        for old in original.get('module', []):
            new = next((m for m in modules if m['serialNo'] == old['serialNo']), None)
            if new is None or new.get('productId') != old.get('productId'):
                raise EditError('Clear a module input instead of removing its configuration.')
            if isinstance(old.get('config'), list):
                key = 'mode' if old['productId'] == 'SENSE_CUBE' else 'keyCode'
                if not isinstance(new['config'], list) or any(not any(isinstance(x, dict) and x.get(key) == entry.get(key) for x in new['config']) for entry in old['config']):
                    raise EditError('Keep input slots and clear their action lists to remove actions safely.')
        # Validate the JSON tree and size before storing/sending anything.
    try:
        if len(json.dumps(profiles, allow_nan=False).encode()) > 2*1024*1024:
            raise EditError('The profile draft is too large.')
    except (ValueError, RecursionError) as exc:
        raise EditError('Invalid profile data.') from exc
    # The former accessibility overlay cannot track native scrolling reliably.
    # Reject old drafts too, so redeploy cannot bring back broken placeholder cards.
    for profile in profiles:
        for widget in profile['homeData']:
            param = widget.get('param')
            payload = param.get('payload') if isinstance(param, dict) else None
            if isinstance(payload, dict) and payload.get('action') == 'studioMetric':
                raise EditError('GPU and individual-drive overlay widgets are no longer supported. Remove these cards before saving or deploying.')
    from native_widgets import specifications
    specifications(profiles)


def retain_cleared_slots(profiles, current):
    """Restoration keeps empty input records so LineOS unloads newly added runtime scenes."""
    def emptied(value):
        if isinstance(value, dict):
            return {k: [] if k == 'actions' else emptied(v) for k, v in value.items()}
        if isinstance(value, list):
            return [emptied(v) for v in value]
        return value
    result = deepcopy(profiles)
    for p, present in zip(result, current):
        for module in present.get('module', []):
            saved = next((m for m in p['module'] if m['serialNo'] == module['serialNo']), None)
            if saved is None:
                p['module'].append(emptied(module))
            elif isinstance(module['config'], list) and isinstance(saved['config'], list):
                key = 'mode' if module['productId'] == 'SENSE_CUBE' else 'keyCode'
                for slot in module['config']:
                    if not any(s.get(key) == slot.get(key) for s in saved['config']):
                        saved['config'].append(emptied(slot))
    return result


def to_wire(profiles):
    result = []
    for p in profiles:
        # ProfileDTO cannot carry these fields: fail before writing if they would change.
        if p.get('albumId', 'time_image_10') != 'time_image_10' or p.get('player', 'SONOS') != 'SONOS':
            raise EditError('This profile has custom album/player settings that the deploy protocol cannot preserve.')
        supported = {'id', 'name', 'icon', 'bgColor', 'iconScale', 'default', 'showName', 'homeData', 'module', 'albumId', 'player', '@type'}
        if set(p)-supported:
            raise EditError('This profile contains additional settings the deploy protocol cannot preserve.')
        row = clean({k: v for k, v in p.items() if k not in ('homeData', 'albumId', 'player')})
        row['widget'] = clean(p['homeData'])
        result.append(row)
    return result


def matches(expected, actual):
    """All submitted fields must survive; tolerate runtime defaults and generated Sense IDs."""
    if isinstance(expected, dict):
        if not isinstance(actual, dict):
            return False
        return all(k in ('@type', 'isExecuting') or
                   (k == 'id' and 'mode' in expected and 'actions' in expected) or
                   (k in actual and matches(v, actual[k])) for k, v in expected.items())
    if isinstance(expected, list):
        return isinstance(actual, list) and len(expected) == len(actual) and all(matches(a, b) for a, b in zip(expected, actual))
    return expected == actual


def register_editor(server):
    core_icons = CoreIcons()
    app = server.app

    @app.errorhandler(EditError)
    def edit_error(exc):
        return jsonify(error=str(exc)), 400

    def current():
        snapshot = server.connection['snapshot']
        if not snapshot:
            raise EditError('Connect to CoreBAR first.')
        return snapshot

    @app.get('/api/editor')
    def get_editor():
        with server.device_lock:
            snapshot = current()
            if not snapshot['profiles']:
                raise EditError('Create a profile on CoreBAR before using the editor.')
            draft = load_draft(server, snapshot)
            return jsonify(draft=draft, conflict=draft['base_hash'] != digest(snapshot['profiles']))

    @app.get('/api/editor/catalog')
    def catalog():
        with server.device_lock:
            current()
            try:
                apps = bridge.request(server.connection['target'], server.adb, server.ROOT, 1000, None)
                if not isinstance(apps, list):
                    raise ValueError()
                result=[]
                for app in apps:
                    if not isinstance(app,dict):continue
                    package=app.get('packageName') or app.get('application')
                    if not isinstance(package,str) or not re.fullmatch(r'[A-Za-z][A-Za-z0-9_]*(?:\.[A-Za-z][A-Za-z0-9_]*)+',package):continue
                    name=app.get('appName')
                    result.append(dict(id=package,name=name if isinstance(name,str) and name.strip() else package,type='APPS',iconScale=100))
                return jsonify(apps=result)
            except Exception as exc:
                raise server.DeviceError('Could not load installed apps. Existing widgets remain available.') from exc

    @app.get('/api/editor/icons/<kind>')
    @app.get('/api/editor/icons/<kind>/<ident>')
    def library_icon(kind,ident=''):
        with server.device_lock:
            snapshot=current()
            target=server.validate_target(server.connection['target'])
            device_id=snapshot['device_id']
        try:
            raw=core_icons.get(target,kind,ident,server.adb,device_id)
        except Exception as exc:
            raise server.DeviceError('The device icon is unavailable. Existing widgets remain usable.') from exc
        return Response(raw,mimetype='image/png',headers={'X-Content-Type-Options':'nosniff','Cache-Control':'private, no-store'})

    @app.post('/api/editor/draft')
    def save_draft():
        body = request.get_json(silent=True)
        if not isinstance(body, dict):
            raise EditError('Invalid draft request.')
        with server.device_lock:
            snapshot = current()
            draft = load_draft(server, snapshot)
            if body.get('device_id') != snapshot['device_id'] or body.get('revision') != draft['revision']:
                return jsonify(error='The device or draft changed. Reopen the editor before saving.'), 409
            profiles = body.get('profiles')
            validate(profiles, draft['base_profiles'])
            background=body.get('background_apps',draft.get('background_apps',[]))
            validate_background(background)
            draft.update(profiles=profiles, background_apps=background, revision=uuid.uuid4().hex, saved_at=datetime.now(timezone.utc).isoformat())
            atomic_json(draft_path(server, snapshot['device_id']), draft)
            return jsonify(draft=draft)

    @app.post('/api/editor/reset')
    def reset_draft():
        body = request.get_json(silent=True) or {}
        with server.device_lock:
            snapshot = current()
            draft = load_draft(server, snapshot)
            if body.get('device_id') != snapshot['device_id'] or body.get('revision') != draft['revision']:
                return jsonify(error='The device or draft changed. Reopen the editor.'), 409
            latest = server.read_snapshot(server.connection['target'])
            if latest['device_id'] != snapshot['device_id']:
                return jsonify(error='A different CoreBAR is now connected. Reconnect.'), 409
            server.connection['snapshot'] = latest
            draft = fresh_draft(latest)
            draft['background_apps']=saved_background(server,latest['device_id'])
            atomic_json(draft_path(server, latest['device_id']), draft)
            return jsonify(draft=draft, snapshot=latest)

    progress_lock = threading.Lock()
    progress = dict(request_id=None, state='idle', message='')
    def stage(message):
        with progress_lock: progress.update(message=message)
    @app.get('/api/editor/deploy-status')
    def deploy_status():
        with progress_lock:return jsonify(dict(progress))
    def tracked(fn):
        @wraps(fn)
        def wrapper():
            body=request.get_json(silent=True) or {}
            with progress_lock:
                if progress['state']=='running':return jsonify(error='A deployment is already running.'),409
                progress.update(request_id=body.get('request_id'),state='running',message='Checking the saved draft?')
            try:
                response=app.make_response(fn())
                data=response.get_json() or {}
                with progress_lock:progress.update(state='done' if response.status_code<400 else 'error',message=data.get('message') or data.get('error','Deployment finished.'))
                return response
            except Exception as exc:
                with progress_lock:progress.update(state='error',message='Deployment stopped. Check the connection and the saved draft.')
                raise
        return wrapper

    @app.post('/api/editor/deploy')
    @tracked
    def deploy():
        body = request.get_json(silent=True) or {}
        with server.device_lock:
            snapshot = current()
            draft = load_draft(server, snapshot)
            if body.get('device_id') != snapshot['device_id'] or body.get('revision') != draft['revision']:
                return jsonify(error='The device or draft changed. Save the current draft before deploying.'), 409
            validate(draft['profiles'], draft['base_profiles'])
            validate_background(draft.get('background_apps',[]))
            payload = to_wire(draft['profiles'])
            stage('Reading Core settings and creating a backup…')
            latest = server.read_snapshot(server.connection['target'])  # Also saves original XML before any write.
            if latest['device_id'] != draft['device_id'] or digest(latest['profiles']) != draft['base_hash']:
                return jsonify(error='Settings changed on CoreBAR since this draft was started. Download your draft, then reload from Core before editing again.'), 409
            rollback = dict(device_id=latest['device_id'], profiles=latest['profiles'], backup=latest['backup'])
            rollback['background_apps']=saved_background(server,latest['device_id'])
            rollback_path = draft_path(server, latest['device_id']).with_suffix('.rollback.json')
            atomic_json(rollback_path, rollback)
            stage('Waking Core and waiting for the screen…')
            wake_for_deploy(server, server.connection['target'])
            server.store.deploy_dependencies(draft['profiles'],draft['device_id'],stage,draft.get('background_apps',[]))
            server.store.stop_removed_background(rollback['background_apps'],draft.get('background_apps',[]),draft['profiles'])
            stage('Preparing the widget runtime on Core…')
            server.native_widgets.prepare(draft['profiles'], server.connection['target'])
            # A timeout is ambiguous: always read back, and never blindly resend a write.
            stage('Sending the layout and settings to Core…')
            acknowledged = True
            try:
                bridge.request(server.connection['target'], server.adb, server.ROOT, 1108, payload)
            except Exception:
                acknowledged = False
            stage('Reading back and verifying the saved settings…')
            verified = None
            for attempt in range(4):
                if attempt:
                    time.sleep(.4)
                try:
                    raw = server.adb('-s', server.connection['target'], 'exec-out', 'cat', server.PREFERENCES, binary=True)
                    actual = server.parse_profiles(raw)['profiles']
                    if matches(draft['profiles'], actual):
                        verified = actual
                        break
                except server.DeviceError:
                    pass
            if verified is None:
                return jsonify(error='Deployment could not be verified. Core may have changed. Your draft and pre-deploy backup are preserved; reload device settings before retrying.',
                               backup=latest['backup'], acknowledged=acknowledged), 502
            atomic_json(background_path(server,latest['device_id']),draft.get('background_apps',[]))
            snapshot = dict(latest, profiles=verified, read_at=datetime.now(timezone.utc).isoformat())
            server.connection['snapshot'] = snapshot
            new_draft = fresh_draft(snapshot)
            new_draft['background_apps']=deepcopy(draft.get('background_apps',[]))
            atomic_json(draft_path(server, snapshot['device_id']), new_draft)
            # BatchProfileMessage saves/reloads modules but does not publish the home refresh event.
            # Restart only LineOS (not CoreBridge, Android, or our screen-sync service).
            stage('Restarting the Core home screen…')
            activated = False
            try:
                result = server.adb('-s', server.connection['target'], 'shell', 'am', 'start', '-W', '-S', '-n',
                                    'com.ultrabar.launch/.ui.activity.MainActivity')
                activated = isinstance(result, str) and 'Status: ok' in result
            except server.DeviceError:
                pass
            stage('Waiting for widgets to become ready…')
            server.native_widgets.configure(verified, server.connection['target'])
            if server.native_widgets.specs:
                server.native_widgets.ready.wait(8)
            native_note = '' if not server.native_widgets.specs or server.native_widgets.ready.is_set() else ' Studio widgets are waiting for Core home; keep Studio connected.'
            return jsonify(draft=new_draft, snapshot=snapshot, backup=latest['backup'], acknowledged=acknowledged,
                           activated=activated, message='Settings saved and verified. '+
                           ('Core home restarted to load the new layout. Test changed module inputs on your hardware.' if activated else
                            'Core home could not be restarted. Restart LineOS to activate the new layout.')+native_note)

    @app.post('/api/editor/restore-draft')
    def restore_draft():
        body = request.get_json(silent=True) or {}
        with server.device_lock:
            snapshot = current()
            draft = load_draft(server, snapshot)
            if body.get('device_id') != snapshot['device_id'] or body.get('revision') != draft['revision']:
                return jsonify(error='The draft changed. Reopen the editor.'), 409
            path = draft_path(server, snapshot['device_id']).with_suffix('.rollback.json')
            if not path.exists():
                raise EditError('No pre-deploy settings are available yet.')
            previous = json.loads(path.read_text(encoding='utf-8'))
            latest = server.read_snapshot(server.connection['target'])
            if latest['device_id'] != snapshot['device_id']:
                return jsonify(error='The connected CoreBAR changed.'), 409
            restored = fresh_draft(latest)
            restored['profiles'] = retain_cleared_slots(previous['profiles'], latest['profiles'])
            restored['background_apps']=previous.get('background_apps',[])
            validate_background(restored['background_apps'])
            validate(restored['profiles'], restored['base_profiles'])
            atomic_json(draft_path(server, snapshot['device_id']), restored)
            server.connection['snapshot'] = latest
            return jsonify(draft=restored, snapshot=latest)
