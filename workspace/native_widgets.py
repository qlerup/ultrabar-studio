"""Native LineOS card integration for the tested root-enabled CB01 build.

Only explicitly tagged Studio cards are rendered. The vendor APK stays intact.
Frida is pinned to the matching device runtime and listens on device loopback.
"""
import base64
import hashlib
import json
import math
import re
import secrets
import struct
import threading
import time
import uuid
from editor import EditError

PACKAGE = 'com.ultrabar.launch'
RUNTIME = '/data/local/tmp/studio-runtime-16.7.19'
RUNTIME_SHA = 'fc60c38a6acb42d9eb2d5c0474bf84fd671c14870b9cab43129b38c5e364bb13'
SUPPORTED_LINEOS = {'1.0.8', '1.0.9'}


def install_runtime(server, target, source):
    def checksum(path):
        result = server.adb('-s', target, 'shell', f'if [ -f {path} ]; then sha256sum {path}; fi')
        return result.split()[:1] == [RUNTIME_SHA]

    if checksum(RUNTIME):
        return
    staged = RUNTIME + '-' + uuid.uuid4().hex + '.tmp'
    try:
        server.adb('-s', target, 'push', str(source), staged, timeout=180)
        if not checksum(staged):
            raise EditError('Widget runtime transfer failed its checksum. Retry Deploy.')
        server.adb('-s', target, 'shell', 'mv', staged, RUNTIME)
    except server.DeviceError as exc:
        raise EditError('Widget runtime transfer could not be completed. Your Core layout has not been sent. Retry Deploy.') from exc
    finally:
        try:
            server.adb('-s', target, 'shell', 'rm', '-f', staged)
        except server.DeviceError:
            pass


def alert_pcm(kind, sequence=None):
    """Build the short alert on the PC as 16 kHz, mono signed PCM."""
    if sequence is None:
        notes = {'success': (523.25, 659.25, 783.99), 'error': (740, 440, 440)}[kind]
        sequence = [note for hz in notes for note in ((hz,160),(0,30))]
    samples = bytearray()
    for note in sequence:
        frequency, milliseconds = note[:2]
        frames = 16 * milliseconds
        bell = len(note) == 3
        partials = [
            (ratio, amplitude, decay)
            for ratio, amplitude, decay in ((2.76, .32, 10), (4.07, .16, 16))
            if bell and frequency * ratio < 8000
        ]
        for index in range(frames):
            gain = min(1, index / 180, (frames - index - 1) / 380)
            phase = 2 * math.pi * frequency * index / 16000
            wave = math.sin(phase)
            if bell:
                progress = index / frames
                wave *= math.exp(-4 * progress)
                for ratio, amplitude, decay in partials:
                    wave += amplitude * math.sin(phase * ratio) * math.exp(-decay * progress)
            sample = round(8100 * gain * wave)
            samples.extend(struct.pack('<h', sample))
    return base64.b64encode(samples).decode('ascii')


def alert_options(specs):
    options = {}
    for spec in specs.values():
        if spec.get('kind') == 'bambu' and spec.get('printAlerts', False):
            key = spec.get('printerId')
            options[key] = options.get(key, False) or spec.get('wakeOnAlert', True)
    return options


def widget_alert(specs, panels, printer_id, kind, printer):
    sequence = notification = None
    for spec in specs.values():
        if spec.get('kind') != 'bambu' or spec.get('printerId') != printer_id or not spec.get('printAlerts'):
            continue
        panel = panels.get((spec.get('packageId'), spec.get('widgetKey')), {})
        if notification is None:
            template = panel.get('notifications', {}).get(kind)
            if template:
                source = printer.get('name') or spec.get('_cardTitle') or template['title']
                message = template['message'].replace('{source}', ' '.join(source.split()))
                notification = dict(template, message=message[:200].strip() or template['title'])
        if sequence is None:
            sequence = panel.get('sounds', {}).get(kind)
        if notification is not None and sequence is not None:
            break
    return notification, alert_pcm(kind, sequence)


def check_lineos(package_dump):
    # dumpsys also lists the old, hidden system APK. Only inspect the active package.
    active = package_dump.split('Packages:', 1)[-1].split('Hidden system packages:', 1)[0]
    match = re.search(r'^\s*versionName=([^\s]+)', active, re.MULTILINE)
    version = match.group(1) if match else 'unknown'
    if version not in SUPPORTED_LINEOS:
        raise EditError(f'Native widgets support LineOS 1.0.8 and 1.0.9. Connected version: {version}.')
    return version



def specifications(profiles):
    result = {}
    for profile in profiles:
        for widget in profile.get('homeData', []):
            param = widget.get('param')
            payload = param.get('payload') if isinstance(param, dict) else None
            if not isinstance(payload, dict) or payload.get('action') != 'studioNative':
                continue
            key = widget.get('id', '')
            spec = payload.get('params')
            if widget.get('type') != 'PC_CONTROL' or not re.fullmatch(r'studio_native_[a-f0-9]{32}', key):
                raise EditError('Invalid native widget ID or type.')
            if not isinstance(spec, dict) or spec.get('kind') not in ('cpu', 'memory', 'gpu', 'disk', 'clock', 'bambu','scene'):
                raise EditError('Choose a supported Studio widget.')
            from bambu_contract import validate as validate_bambu
            try:validate_bambu(spec)
            except ValueError as exc:raise EditError(str(exc)) from exc
            if 'kindOptions' in spec:
                options=spec['kindOptions']
                if not isinstance(options,list) or not 2<=len(options)<=3 or any(k not in ('cpu','memory','gpu') for k in options) or len(set(options))!=len(options) or spec['kind'] not in options:
                    raise EditError('Invalid widget measurement options.')
            if spec['kind'] == 'clock':
                if spec.get('hourFormat','24') not in ('12','24') or any(type(spec[k]) is not bool for k in ('showSeconds','showDate') if k in spec):
                    raise EditError('Invalid clock display settings.')
            if spec['kind'] == 'clock':
                if spec.get('hourFormat','24') not in ('12','24') or any(type(spec[k]) is not bool for k in ('showSeconds','showDate') if k in spec):
                    raise EditError('Invalid clock display settings.')
            if spec['kind'] == 'disk' and (not isinstance(spec.get('drive'), str) or not (spec['drive'] == 'all' or re.fullmatch(r'[A-Z]:\\', spec['drive']))):
                raise EditError('Choose a drive or All drives for this widget.')
            if not isinstance(spec.get('accent'), str) or not re.fullmatch(r'#[0-9a-fA-F]{6}', spec['accent']):
                raise EditError('Choose a valid widget accent color.')
            if not isinstance(spec.get('textColor', '#eef6f2'), str) or not re.fullmatch(r'#[0-9a-fA-F]{6}', spec.get('textColor', '#eef6f2')):
                raise EditError('Choose a valid widget text color.')
            if 'drives' in spec:
                drives = spec['drives']
                if not isinstance(drives, list) or not 1 <= len(drives) <= 2 or any(not isinstance(d, str) or not re.fullmatch(r'[A-Z]:\\', d) for d in drives) or len(set(drives)) != len(drives):
                    raise EditError('Each disk widget can show at most two distinct drives.')
            effective = dict(spec, background=widget.get('bgColor') or '#192325')
            effective.pop('_scene', None)
            effective['_cardTitle'] = widget.get('name', '')
            if key in result and result[key] != effective:
                raise EditError('Widgets with the same ID must use the same hardware source across profiles.')
            result[key] = effective
    return result


class NativeWidgets:
    def __init__(self, server):
        self.server = server
        self.lock = threading.RLock()
        self.stop = threading.Event()
        self.ready = threading.Event()
        self.thread = None
        self.target = None
        self.specs = {}
        self.compact_profiles = {}
        self.status = 'No Studio native widgets deployed'
        self.last_error = None
        self.token = None
        self.printer_actions = {}
        self.presentations = {}
        self.layouts = {}
        self.alert_panels = {}

    def printer_action(self, event):
        # Transient events only: no file queue, retry or command replay on reconnect.
        if not isinstance(event, dict) or set(event) != {'id', 'widgetId', 'printerId', 'action', 'createdAt'}:
            return
        key = event.get('id')
        if not isinstance(key, str) or not re.fullmatch('[a-f0-9]{32}', key) or key in self.printer_actions:
            return
        spec = self.specs.get(event.get('widgetId')) if isinstance(event.get('widgetId'), str) else None
        if not spec or spec.get('kind') != 'bambu' or not spec.get('showControls', True) or spec.get('printerId') != event.get('printerId'):
            return
        # Device wall clock is also used by the existing metrics freshness guard.
        stamp = event.get('createdAt')
        if type(stamp) not in (int, float) or not math.isfinite(stamp) or abs(time.time()*1000-stamp) > 5000 or event.get('action') not in ('pause','resume','stop','light_on','light_off'):
            return
        now = time.monotonic()
        self.printer_actions = {k: t for k, t in self.printer_actions.items() if now-t < 10}
        if len(self.printer_actions) >= 4096:
            return
        self.printer_actions[key] = now
        with self.server.bambu.lock:
            link = self.server.bambu.links.get(event['printerId'])
            if link:
                link.request(event['action'])

    def start_runtime(self, target):
        self.server.adb('-s', target, 'shell', 'pidof studio-runtime-16.7.19 >/dev/null || '+RUNTIME+
                        ' -D -l 127.0.0.1:27042 --token='+self.token+
                        ' </dev/null >/data/local/tmp/studio-runtime.log 2>&1 &')

    def prepare(self, profiles, target, compact_profiles=None):
        specs = specifications(profiles)
        if not specs and not compact_profiles:
            return
        adb = self.server.adb
        if 'uid=0(' not in adb('-s', target, 'shell', 'id'):
            raise EditError('Native widgets currently require the root-enabled CB01 firmware tested with Studio.')
        if adb('-s', target, 'shell', 'getprop', 'ro.product.cpu.abi') != 'armeabi-v7a':
            raise EditError('This native widget build supports ARM32 CoreBAR only.')
        package = adb('-s', target, 'shell', 'dumpsys', 'package', PACKAGE)
        if check_lineos(package) != '1.0.9' and compact_profiles:
            raise EditError('Two widget rows require LineOS 1.0.9 on CoreBAR.')
        self.server.bambu.validate(specs)
        assets = self.server.ROOT / 'assets/native'
        if hashlib.sha256((assets/'studio-runtime').read_bytes()).hexdigest() != RUNTIME_SHA:
            raise EditError('Native runtime integrity check failed. Reinstall Studio.')
        # An open launcher can still have the old file mapped during deployment.
        # Publish the new file by rename so readers retain a complete old image.
        staged = '/data/local/tmp/studio-widgets-' + uuid.uuid4().hex + '.tmp'
        try:
            adb('-s', target, 'push', str(assets/'studio-widgets.dex'), staged)
            adb('-s', target, 'shell', 'chmod', '644', staged)
            adb('-s', target, 'shell', 'mv', staged, '/data/local/tmp/studio-widgets.dex')
        finally:
            try:
                adb('-s', target, 'shell', 'rm', '-f', staged)
            except self.server.DeviceError:
                pass
        install_runtime(self.server, target, assets/'studio-runtime')
        adb('-s', target, 'shell', 'chmod', '700', RUNTIME)
        self.token = adb('-s', target, 'shell', 'cat /data/local/tmp/studio-runtime-token 2>/dev/null || true')
        if not re.fullmatch(r'[a-f0-9]{64}', self.token):
            self.token = secrets.token_hex(32)
            adb('-s', target, 'shell', 'umask 077; cat > /data/local/tmp/studio-runtime-token', input_data=self.token.encode())
        self.start_runtime(target)

    def configure(self, profiles, target, compact_profiles=None):
        specs = specifications(profiles)
        import widget_presentation
        import studio_contract
        records = self.server.store.records() if specs else {}
        import widget_scene
        layouts = {key:layout for key,spec in specs.items() if (layout:=widget_scene.installed(spec,records))}
        alert_panels = {(record.get('id'), widget.get('id')): widget.get('studio', {})
                        for record in records.values() for widget in record.get('widgets', [])}
        studio_contract.apply_installed_settings(specs, records)
        presentations = widget_presentation.bindings(specs, records) if specs else {}
        with self.lock:
            if self.thread and self.thread.is_alive() and (target != self.target or self.stop.is_set()):
                self.stop.set()
                self.thread.join(20)
                if self.thread.is_alive():
                    raise EditError('Previous native widget connection is still closing.')
            self.specs = specs
            self.compact_profiles = compact_profiles or {}
            self.presentations = presentations
            self.layouts = layouts
            self.alert_panels = alert_panels
            self.server.bambu.configure(specs)
            if not specs and not compact_profiles:
                self.stop.set()
                self.status = 'No Studio native widgets deployed'
                return
            self.target = target
            self.device_id = (self.server.connection['snapshot'] or {}).get('device_id')
            if not self.thread or not self.thread.is_alive():
                self.stop = threading.Event()
                self.ready.clear()
                self.thread = threading.Thread(target=self.run, daemon=True, name='StudioNativeWidgets')
                self.thread.start()

    def run(self):
        import frida
        adb = self.server.adb
        target = self.target
        port = None
        remote = None
        session = None
        script = None
        pid = None
        applied_compact_profiles = None
        pending_alerts = []
        wake_sent = set()

        def wake_core():
            try:
                adb('-s', target, 'shell', 'input', 'keyevent', '224')
                return True
            except self.server.DeviceError:
                return False

        def call_runtime(method, *args):
            cancel = frida.Cancellable()
            timeout = threading.Timer(5, cancel.cancel)
            timeout.daemon = True
            timeout.start()
            try:
                return getattr(script.exports_sync, method)(*args, cancellable=cancel)
            finally:
                timeout.cancel()
        try:
            while not self.stop.is_set():
                try:
                    with self.lock:
                        specs, presentations, layouts, alert_panels = self.specs, self.presentations, self.layouts, self.alert_panels
                    options = alert_options(specs)
                    pending_alerts.extend(self.server.bambu.take_alerts(options))
                    now = time.monotonic()
                    pending_alerts = [a for a in pending_alerts if now - a[1] < 8 and a[2] in options]
                    wake_sent.intersection_update(pending_alerts)
                    new_pid = int(adb('-s', target, 'shell', 'pidof', PACKAGE).split()[0])
                    if session is None or session.is_detached or pid != new_pid:
                        self.ready.clear()
                        if adb('-s', target, 'shell', 'getprop', 'ro.serialno') != self.device_id:
                            self.status = 'Core identity changed; reconnect in Studio'
                            return
                        need_wake = {alert for alert in pending_alerts if options[alert[2]]} - wake_sent
                        if need_wake and wake_core():
                            wake_sent.update(need_wake)
                        # Attaching to an ART process while Zygote is still starting it
                        # can abort startup on this ARM32 firmware. Wait for a real window.
                        window = adb('-s', target, 'shell', 'dumpsys', 'window')
                        if not any('mCurrentFocus=' in line and 'com.ultrabar.launch.ui.activity.HomeActivity' in line for line in window.splitlines()):
                            self.status = 'Waiting for Core home to finish opening'
                            self.stop.wait(1)
                            continue
                        self.start_runtime(target)
                        if session and not session.is_detached:
                            session.detach()
                        if port is None:
                            port = adb('-s', target, 'forward', 'tcp:0', 'tcp:27042')
                            remote = frida.get_device_manager().add_remote_device('127.0.0.1:'+port, token=self.token)
                        self.status = 'Loading native widgets into Core home'
                        session = remote.attach(new_pid)
                        source = (self.server.ROOT/'assets/native/widgets.js').read_text(encoding='utf-8')
                        applied_compact_profiles = self.compact_profiles
                        script = session.create_script(f'const studioCompactProfiles = {json.dumps(applied_compact_profiles)};\n'+source)
                        def message(msg, data):
                            if msg.get('type') == 'send' and msg['payload'].get('ready'):
                                self.status = 'Native widgets connected'
                                self.last_error = None
                                self.ready.set()
                            elif msg.get('type') == 'send' and isinstance(msg.get('payload'), dict) and 'bambuAction' in msg['payload']:
                                self.printer_action(msg['payload']['bambuAction'])
                            elif msg.get('type') == 'error' or msg.get('payload', {}).get('error'):
                                self.last_error = str(msg)
                                self.status = 'Native widget rendering error'
                        script.on('message', message)
                        script.load()
                        pid = new_pid
                    compact_profiles = self.compact_profiles
                    if applied_compact_profiles != compact_profiles:
                        call_runtime('set_compact_profiles', compact_profiles)
                        applied_compact_profiles = compact_profiles
                    import widget_presentation
                    from bambu_artwork import thumbnail
                    printers = self.server.bambu.sample()
                    if self.ready.is_set():
                        while pending_alerts and not self.stop.is_set():
                            kind, created, key = alert = pending_alerts.pop(0)
                            if time.monotonic() - created < 8:
                                if options[key] and alert not in wake_sent:
                                    wake_core()
                                notification, pcm = widget_alert(specs, alert_panels, key, kind, printers.get(key, {}))
                                if notification:
                                    status = call_runtime('post_core_notification', notification)
                                    if status == 'screen_off' and options[key] and not self.stop.wait(.25):
                                        call_runtime('post_core_notification', notification)
                                if not self.stop.is_set():
                                    call_runtime('play_print_alert', pcm)
                    widgets = widget_presentation.apply(specs, presentations, {'bambu-lan': printers})
                    models = {printer.get('model') for printer in printers.values()}
                    images = {model: image for model in models if (image := thumbnail(model))}
                    metrics = self.server.companion.metrics.sample()
                    import widget_scene
                    for key,layout in layouts.items():
                        spec=widgets[key]
                        title=spec.get('_cardTitle','')
                        stamp=time.time()
                        spec['_scene']=widget_scene.frames(spec,layout,metrics,printers,title,stamp)
                        if spec.get('kind')!='clock':
                            offline={'name':printers.get(spec.get('printerId'),{}).get('name') or title,'connection':'Offline'}
                            offline['model']=printers.get(spec.get('printerId'),{}).get('model','')
                            for size in layout:
                                spec['_scene'][size+'Offline']=widget_scene.make(layout,size,spec,{},offline,title,stamp)
                    scene_images=widget_scene.compact_frames(widgets)
                    state = dict(sequence=uuid.uuid4().hex, widgets=widgets, metrics=metrics,
                                 printers=printers, printerImages=images, sceneImages=scene_images)
                    payload = json.dumps(state,allow_nan=False).encode()
                    if len(payload) >= (4194304 if scene_images else 262144):
                        raise EditError('Widget data exceeds the Core runtime limit. Reduce the number or size of package artwork presets.')
                    adb('-s', target, 'shell',
                        "cat > /data/local/tmp/ultrabar-studio-metrics.tmp && chmod 644 /data/local/tmp/ultrabar-studio-metrics.tmp && mv /data/local/tmp/ultrabar-studio-metrics.tmp /data/local/tmp/ultrabar-studio-metrics.json",
                        input_data=payload)
                    self.stop.wait(2)
                except Exception as exc:
                    self.ready.clear()
                    self.last_error = type(exc).__name__+': '+str(exc)
                    self.status = 'Native widget connection interrupted; retrying'
                    self.stop.wait(4)
        finally:
            if session and not session.is_detached:
                if script is not None and applied_compact_profiles:
                    try: call_runtime('set_compact_profiles', {})
                    except Exception: pass
                session.detach()
            if port:
                try: adb('-s', target, 'forward', '--remove', 'tcp:'+port)
                except Exception: pass
            self.ready.clear()
