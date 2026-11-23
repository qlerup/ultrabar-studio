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
import widget_images
import app_settings
import core_screensaver
import core_notifications
from pc_standby import placed as standby_placed


class EditError(ValueError):
    pass


STUDIO_PROFILE_ID = re.compile(r'studio_profile_[0-9a-f]{32}')


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


def home_visible(server, target):
    try:
        window = server.adb('-s', target, 'shell', 'dumpsys', 'window')
        focus = r'^\s*mCurrentFocus=Window\{[^\n}]* com\.ultrabar\.launch/(?:com\.ultrabar\.launch)?\.ui\.activity\.HomeActivity[ }]'
        return isinstance(window, str) and re.search(focus, window, re.MULTILINE) is not None
    except server.DeviceError:
        return False


def open_home(server, target, restart):
    # am start can time out after Android accepts the intent. Inspect the foreground
    # window before retrying. Only the initial launch should stop the old process.
    flags = ['-S'] if restart else []
    try:
        server.adb('-s', target, 'shell', 'am', 'start', '-W', *flags, '-n',
                   'com.ultrabar.launch/.ui.activity.MainActivity')
    except server.DeviceError:
        pass
    for attempt in range(12):
        if home_visible(server, target):
            return True
        if attempt < 11:
            time.sleep(.5)
    return False


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
                revision=uuid.uuid4().hex, saved_at=datetime.now(timezone.utc).isoformat(), background_apps=[],app_settings={},vivo_screens={})


def settings_path(server,device):return draft_path(server,device).with_suffix('.settings.json')
def vivo_path(server,device):return draft_path(server,device).with_suffix('.vivo.json')
def compact_profiles_path(server, device):
    return draft_path(server, device).with_suffix('.compact-profiles.json')


def widget_layout_parts(layout):
    if isinstance(layout, dict) and {'small', 'positions'} <= set(layout) <= {'small', 'positions', 'splits'}:
        return layout['small'], layout['positions'], layout.get('splits', [])
    return layout, {}, []


def core_widget_layouts(layouts):
    result = {}
    for profile, layout in layouts.items():
        small, positions, _ = widget_layout_parts(layout)
        if positions:
            result[profile] = dict(small=small, positions=positions)
        elif small:
            result[profile] = small
    return result


def validate_compact_profiles(value, profiles, records=None):
    from store import widget_sizes

    by_id = {profile['id']: profile for profile in profiles}
    if not isinstance(value, dict) or set(value) - set(by_id):
        raise EditError('Choose widget sizes for an existing profile.')
    result = {}
    for key, profile in by_id.items():
        layout = value.get(key, [])
        ids, positions, splits = widget_layout_parts(layout)
        if (not isinstance(splits, list) or len(splits) > 256
                or any(type(column) is not int or not 0 <= column < 511 for column in splits)
                or any(right - left < 2 for left, right in zip(splits, splits[1:]))):
            raise EditError('Choose separate positions for each 2×2 group.')
        if not isinstance(ids, list) or len(ids) > 128 or any(not isinstance(i, str) for i in ids) or len(ids) != len(set(ids)):
            raise EditError('Invalid small widget selection.')
        widgets = {widget['id']: widget for widget in profile['homeData']}
        selected = set(ids)
        if selected - set(widgets):
            raise EditError('Small widgets must be on the Core layout.')
        if not isinstance(positions, dict) or (positions and set(positions) != set(widgets)):
            raise EditError('Assign a position to each placed widget.')
        occupied = set()
        for ident, widget in widgets.items():
            small = ident in selected
            size = 'small' if small else 'large'
            if records is not None and size not in widget_sizes(widget, records):
                raise EditError(f"{widget.get('name') or ident} does not support the {size} size.")
            if not positions:
                continue
            cell = positions[ident]
            if (not isinstance(cell, list) or len(cell) != 2 or any(type(n) is not int for n in cell)
                    or not 0 <= cell[0] < 512 or cell[1] not in ((0, 1) if small else (0,))):
                raise EditError('Invalid widget grid position.')
            col, row = cell
            width = 1 if small else 4 if widget['type'] == 'TIME' else 2
            if not small and any(col < split + 2 and split < col + width for split in splits):
                raise EditError('Large widgets need a slot outside a 2×2 group.')
            footprint = {(x, y) for x in range(col, col + width) for y in ((row,) if small else (0, 1))}
            if occupied & footprint:
                raise EditError('Widget positions overlap.')
            occupied.update(footprint)
        if positions and list(widgets) != sorted(widgets, key=positions.get):
            raise EditError('Widget positions must follow the Core layout order.')
        if splits:
            result[key] = dict(small=ids, positions=positions, splits=splits)
        elif positions:
            result[key] = dict(small=ids, positions=positions)
        elif ids:
            result[key] = ids
    return result


def saved_compact_profiles(server, snapshot):
    try:
        value = json.loads(compact_profiles_path(server, snapshot['device_id']).read_text(encoding='utf-8'))
        if not isinstance(value, dict):
            raise ValueError()
        result = {}
        for profile in snapshot['profiles']:
            keys = [widget['id'] for widget in profile['homeData']]
            selected, positions, splits = widget_layout_parts(value.get(profile['id'], []))
            if not isinstance(selected, list) or any(not isinstance(i, str) for i in selected) or not isinstance(positions, dict):
                raise ValueError()
            selected = [key for key in selected if key in keys]
            if positions and all(key in positions for key in keys):
                cells = {key: positions[key] for key in keys}
                if keys == sorted(keys, key=cells.get):
                    result[profile['id']] = dict(small=selected, positions=cells)
                    if splits:
                        result[profile['id']]['splits'] = splits
                    continue
            if splits:
                result[profile['id']] = dict(small=selected, positions={}, splits=splits)
            elif selected:
                result[profile['id']] = selected
        return validate_compact_profiles(result, snapshot['profiles'])
    except FileNotFoundError:
        return {}
    except (OSError, TypeError, ValueError) as exc:
        raise EditError('Could not read saved widget layouts. Existing settings were preserved.') from exc


def saved_vivo(server,device):
    try:return json.loads(vivo_path(server,device).read_text(encoding='utf-8'))
    except FileNotFoundError:return {}
    except (OSError,ValueError) as exc:raise EditError('Could not read saved Vivo screens. Existing data was preserved.') from exc


def saved_app_settings(server,device):
    try:return json.loads(settings_path(server,device).read_text(encoding='utf-8'))
    except FileNotFoundError:return {}
    except (OSError,ValueError) as exc:raise EditError('Saved app settings could not be read. Existing data was preserved.') from exc


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
        if key == core_notifications.PACKAGE:raise EditError('Core Notifications is managed by Studio.')
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
        if 'app_settings' not in draft:draft['app_settings']=saved_app_settings(server,snapshot['device_id'])
        if 'vivo_screens' not in draft:draft['vivo_screens']=saved_vivo(server,snapshot['device_id'])
        if 'compact_profiles' not in draft:
            draft['compact_profiles'] = saved_compact_profiles(server, snapshot)
        server.store.migrate_bambu_draft(draft)
        return draft
    draft = fresh_draft(snapshot)
    draft['background_apps']=saved_background(server,snapshot['device_id'])
    draft['app_settings']=saved_app_settings(server,snapshot['device_id'])
    draft['vivo_screens']=saved_vivo(server,snapshot['device_id'])
    draft['compact_profiles']=saved_compact_profiles(server, snapshot)
    server.store.migrate_bambu_draft(draft)
    atomic_json(path, draft)
    return draft


def validate(profiles, base, restored_removals=()):
    if not isinstance(profiles, list) or not 1 <= len(profiles) <= 64 or any(not isinstance(p, dict) for p in profiles):
        raise EditError('A draft must contain between 1 and 64 profiles.')
    ids = [p.get('id') for p in profiles]
    if any(not isinstance(ident, str) or not ident for ident in ids) or len(set(ids)) != len(ids):
        raise EditError('Each profile needs a unique ID.')
    originals = {p['id']: p for p in base}
    retained = [ident for ident in originals if ident not in restored_removals or ident in ids]
    if ids[:len(retained)] != retained:
        raise EditError('Keep the existing profiles and their IDs.')
    if any(not STUDIO_PROFILE_ID.fullmatch(ident) for ident in ids[len(retained):]):
        raise EditError('Create new profiles from the Studio profile menu.')
    if sum(p.get('default') is True for p in profiles) != 1:
        raise EditError('Exactly one profile must be the default.')
    for p in profiles:
        original = originals.get(p['id'], {})
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
            if '_pcPending' in w:
                param=w.get('param');payload=param.get('payload') if isinstance(param,dict) else {}
                payload=payload if isinstance(payload,dict) else {}
                params=payload.get('params') if isinstance(payload.get('params'),dict) else {}
                if w['_pcPending'] is not True or w['type']!='PC_CONTROL' or payload.get('action')!='studioAction' or params.get('kind') not in ('url','program'):
                    raise EditError('Invalid unfinished Studio shortcut.')
            try:widget_images.picture_hash(w.get('icon'))
            except ValueError as exc:raise EditError(str(exc)) from exc
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
    current_by_id = {p['id']: p for p in current}
    for p in result:
        present = current_by_id.get(p['id'], {})
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
        for w in p['homeData']:
            param=w.get('param');payload=param.get('payload') if isinstance(param,dict) else {}
            payload=payload if isinstance(payload,dict) else {}
            params=payload.get('params') if isinstance(payload.get('params'),dict) else {}
            if w.get('_pcPending') or (payload.get('action')=='studioAction' and not params.get('id')):
                raise EditError('Finish the website or PC app settings and choose Apply settings before Deploy.')
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
    import vivo
    @server.app.get('/api/editor/vivo-picture/<digest>')
    def vivo_picture(digest):
        try:raw=widget_images.read_picture(server,digest)
        except (OSError,ValueError) as exc:raise EditError('This Vivo picture is unavailable. Upload it again.') from exc
        return Response(vivo.picture_png(raw),mimetype='image/png',headers={'X-Content-Type-Options':'nosniff','Cache-Control':'private, max-age=3600'})
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

    @app.post('/api/editor/core-notifications/test')
    def test_core_notifications():
        body = request.get_json(silent=True)
        with server.device_lock:
            snapshot = current()
            if not isinstance(body, dict) or body.get('device_id') != snapshot['device_id']:
                raise EditError('The selected Core changed. Reopen the editor and try again.')
            sound = body.get('sound', 'silent')
            if sound not in core_notifications.TEST_SOUNDS:
                raise EditError('Choose a test notification sound.')
            volume = body.get('volume')
            if volume is not None and (type(volume) is not int or not 0 <= volume <= 100):
                raise EditError('Choose a test volume between 0 and 100 percent.')
            status = core_notifications.test_banner(server, server.connection['target'], sound, volume)
            message = 'Test notification queued on Core.' if status == 'queued' else 'Test notification sent to Core.'
            return jsonify(message=message)

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
            validate(profiles, draft['base_profiles'], draft.get('restored_profile_removals', ()))
            compact_profiles = validate_compact_profiles(body.get('compact_profiles', draft['compact_profiles']), profiles, server.store.records())
            candidate=dict(profiles=profiles,background_apps=body.get('background_apps',draft.get('background_apps',[])),app_settings=body.get('app_settings',draft.get('app_settings',{})))
            validate_background(candidate['background_apps'])
            server.store.migrate_bambu_draft(candidate)
            background=candidate['background_apps']
            validate_background(background)
            settings=app_settings.validate_all(server,candidate['app_settings'])
            screens=body.get('vivo_screens',draft.get('vivo_screens',{}));vivo.validate(screens,profiles)
            draft.update(profiles=profiles, background_apps=background,app_settings=settings,vivo_screens=screens, revision=uuid.uuid4().hex, saved_at=datetime.now(timezone.utc).isoformat())
            draft['compact_profiles'] = compact_profiles
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
            draft['app_settings']=saved_app_settings(server,latest['device_id'])
            draft['vivo_screens']=saved_vivo(server,latest['device_id'])
            draft['compact_profiles']=saved_compact_profiles(server, latest)
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
            validate(draft['profiles'], draft['base_profiles'], draft.get('restored_profile_removals', ()))
            compact_profiles = validate_compact_profiles(draft['compact_profiles'], draft['profiles'], server.store.records())
            core_layouts = core_widget_layouts(compact_profiles)
            from native_widgets import specifications
            server.bambu.validate(specifications(draft['profiles']))
            validate_background(draft.get('background_apps',[]))
            app_settings.validate_all(server,draft.get('app_settings',{}))
            vivo.validate(draft.get('vivo_screens',{}),draft['profiles'])
            package_plan=server.store.deployment_plan(draft['profiles'],draft.get('background_apps',[]))
            server.store.update_widget_versions(draft['profiles'],package_plan)
            payload = to_wire(draft['profiles'])
            stage('Reading Core settings and creating a backup…')
            latest = server.read_snapshot(server.connection['target'])  # Also saves original XML before any write.
            if latest['device_id'] != draft['device_id'] or digest(latest['profiles']) != draft['base_hash']:
                return jsonify(error='Settings changed on CoreBAR since this draft was started. Download your draft, then reload from Core before editing again.'), 409
            rollback = dict(device_id=latest['device_id'], profiles=latest['profiles'], backup=latest['backup'])
            rollback['background_apps']=saved_background(server,latest['device_id'])
            rollback['app_settings']=saved_app_settings(server,latest['device_id'])
            rollback['vivo_screens']=saved_vivo(server,latest['device_id'])
            rollback['compact_profiles']=saved_compact_profiles(server, latest)
            rollback_path = draft_path(server, latest['device_id']).with_suffix('.rollback.json')
            atomic_json(rollback_path, rollback)
            stage('Waking Core and waiting for the screen…')
            wake_for_deploy(server, server.connection['target'])
            stage('Preparing Core Notifications...')
            core_notifications.provision(server, server.connection['target'])
            stage('Preparing widget pictures on Core...')
            widget_images.deploy_pictures(server,draft['profiles'],server.connection['target'])
            screensaver = server.store.deploy_dependencies(draft['profiles'],draft['device_id'],stage,draft.get('background_apps',[]))
            server.store.stop_removed_background(rollback['background_apps'],draft.get('background_apps',[]),draft['profiles'])
            stage('Applying app settings and waiting for confirmation...')
            app_settings.deploy(server, app_settings.deployment_values(server, draft))
            vivo.deploy(server,draft['profiles'],draft.setdefault('vivo_screens',{}),server.connection['target'],stage,lambda:atomic_json(draft_path(server,draft['device_id']),draft),previous_screens=rollback['vivo_screens'])
            stage('Preparing the widget runtime on Core…')
            server.native_widgets.prepare(draft['profiles'], server.connection['target'], core_layouts)
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
            atomic_json(settings_path(server,latest['device_id']),draft.get('app_settings',{}))
            atomic_json(vivo_path(server,latest['device_id']),draft.get('vivo_screens',{}))
            atomic_json(compact_profiles_path(server, latest['device_id']), compact_profiles)
            snapshot = dict(latest, profiles=verified, read_at=datetime.now(timezone.utc).isoformat())
            server.connection['snapshot'] = snapshot
            new_draft = fresh_draft(snapshot)
            new_draft['background_apps']=deepcopy(draft.get('background_apps',[]))
            new_draft['app_settings']=deepcopy(draft.get('app_settings',{}))
            new_draft['vivo_screens']=deepcopy(draft.get('vivo_screens',{}))
            new_draft['compact_profiles']=compact_profiles
            atomic_json(draft_path(server, snapshot['device_id']), new_draft)
            # BatchProfileMessage saves/reloads modules but does not publish the home refresh event.
            # Restart only LineOS (not CoreBridge, Android, or our screen-sync service).
            target = server.connection['target']
            if screensaver:
                stage('Configuring the Core screensaver...')
            core_screensaver.reconcile(server, target, latest['device_id'], screensaver)
            stage('Restarting the Core home screen…')
            target = server.connection['target']
            activated = open_home(server, target, restart=True)
            stage('Waiting for widgets to become ready...')
            server.native_widgets.configure(verified, target, core_layouts)
            needs_runtime = bool(server.native_widgets.specs or core_layouts)
            if activated and needs_runtime:
                server.native_widgets.ready.wait(8)
            # Home can crash after the initial launch, while restoring its widgets.
            if not home_visible(server, target):
                stage('Opening the Core home screen again...')
                activated = open_home(server, target, restart=False)
                if activated and needs_runtime:
                    server.native_widgets.ready.wait(8)
            activated = home_visible(server, target)
            widgets_ready = not needs_runtime or server.native_widgets.ready.is_set()
            if screensaver:
                core_screensaver.activate(server, target, latest['device_id'], screensaver)
            if not activated:
                note = 'Studio could not confirm the Core home screen after reopening it. Your layout is already saved.'
            elif not widgets_ready:
                note = 'Core home is open. Studio is still waiting for the widgets. Keep Studio connected.'
            else:
                note = 'Core home is open with the updated layout.'
            standby_enabled = standby_placed(draft['profiles'], draft.get('background_apps', []))
            if standby_enabled or standby_placed(rollback['profiles'], rollback['background_apps']):
                stage('Confirming PC Standby with Studio…')
            server.pc_standby.reconcile(target, latest['device_id'], standby_enabled)
            server.store.mark_deployed(latest['device_id'],package_plan)
            return jsonify(draft=new_draft, snapshot=snapshot, backup=latest['backup'], acknowledged=acknowledged,
                           activated=activated, widgets_ready=widgets_ready, message='Settings saved and verified. '+note)

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
            saved_ids = {p['id'] for p in restored['profiles']}
            restored['restored_profile_removals'] = [
                p['id'] for p in latest['profiles']
                if p['id'] not in saved_ids and STUDIO_PROFILE_ID.fullmatch(p['id'])
            ]
            restored['background_apps']=previous.get('background_apps',[])
            restored['app_settings']=previous.get('app_settings',{})
            restored['vivo_screens']=previous.get('vivo_screens',{})
            restored['compact_profiles']=validate_compact_profiles(previous.get('compact_profiles', {}), restored['profiles'])
            validate_background(restored['background_apps'])
            validate(restored['profiles'], restored['base_profiles'], restored['restored_profile_removals'])
            atomic_json(draft_path(server, snapshot['device_id']), restored)
            server.connection['snapshot'] = latest
            return jsonify(draft=restored, snapshot=latest)
