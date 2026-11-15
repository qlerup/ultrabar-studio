"""Fixed, verified private-file settings transport for registered Android apps."""
import hashlib
import json
import re
import time
import uuid
from flask import jsonify,request
from app_settings_contract import validate_values,validate_schema


def definitions(server):
    return {p['android']['packageId']:dict(name=p['name'],schema=p['settings']) for p in server.store.records().values() if p.get('type')=='corebar-app' and p.get('settings')}


def validate_all(server,values):
    from editor import EditError
    if not isinstance(values,dict) or len(values)>64:raise EditError('Invalid app settings collection.')
    schemas=definitions(server);result={}
    for package,settings in values.items():
        if package not in schemas:raise EditError('App settings package is no longer in the library. Reinstall it, or use Draft & recovery tools to forget its draft settings before saving or deploying.')
        try:result[package]=validate_values(schemas[package]['schema'],settings)
        except ValueError as exc:raise EditError(schemas[package]['name']+': '+str(exc)) from exc
    return result


def exchange(server,package,schema,values=None):
    from editor import EditError
    from store import ANDROID_ID
    if not ANDROID_ID.fullmatch(package) or package.startswith(('android.','com.android.','com.ultrabar.')):raise EditError('Invalid settings package.')
    validate_schema(schema)
    target=server.connection['target']
    if server.adb('-s',target,'shell','id','-u')!='0':raise EditError('App settings require root-enabled ADB on Core.')
    dump=server.adb('-s',target,'shell','dumpsys','package',package).split('Hidden system packages:',1)[0]
    uid=re.search(r'^\s*userId=(\d+)\s*$',dump,re.M)
    if not uid:raise EditError('Install the app on Core with Deploy before reading its settings.')
    if not 10000<=int(uid[1])<20000:raise EditError('Settings API 1 supports ordinary user-0 apps, not system or shared privileged UIDs.')
    base='/data/user/0/'+package+'/files/ultrabar-studio'
    revision=uuid.uuid4().hex
    envelope=dict(api=1,revision=revision,operation='read' if values is None else 'apply')
    if values is not None:envelope['values']=validate_values(schema,values)
    raw=json.dumps(envelope,ensure_ascii=False,separators=(',',':'),allow_nan=False).encode()
    owner=uid[1]
    # Never write as root inside a contributor app's mutable directory: a symlink
    # there must have only that app's access rights, even during a rename race.
    if server.adb('-s',target,'shell','su',owner,'id','-u')!=owner:raise EditError('Core cannot isolate the settings transfer to the app UID.')
    server.adb('-s',target,'shell',f"su {owner} sh -c 'mkdir -p {base} && chmod 700 {base}'")
    temporary=base+'/request.'+revision+'.tmp'
    server.adb('-s',target,'exec-in',f"su {owner} sh -c 'umask 077; cat > {temporary}'",input_data=raw)
    server.adb('-s',target,'shell',f"su {owner} sh -c 'chmod 600 {temporary} && mv {temporary} {base}/request.json'")
    if server.adb('-s',target,'exec-out','su',owner,'cat',base+'/request.json',binary=True)!=raw:raise EditError('App settings transfer could not be verified. No settings notification was sent.')
    server.adb('-s',target,'shell','am','broadcast','--include-stopped-packages','-n',package+'/.StudioSettingsReceiver','-a',package+'.STUDIO_SETTINGS')
    for attempt in range(20):
        response=server.adb('-s',target,'shell',f"su {owner} sh -c 'if [ -f {base}/response.json ]; then head -c 32769 {base}/response.json; else echo {{}}; fi'",binary=True)
        try:
            data=json.loads(response) if len(response)<=32768 else {}
            if isinstance(data,dict) and data.get('revision')==revision and type(data.get('api')) is int and data['api']==1:
                if data.get('status')!='ok':raise EditError('The app rejected its settings. Check the app on Core; its previous settings may still be active.')
                actual=validate_values(schema,data.get('values'),fill_defaults=False)
                if values is not None and actual!=envelope['values']:raise EditError('The app did not confirm the requested settings. Your draft is preserved; read settings from Core before retrying.')
                return actual
        except (ValueError,TypeError) as exc:
            if isinstance(exc,EditError):raise
        if attempt<19:time.sleep(.25)
    raise EditError('The app did not confirm its settings. Update it to a settings API 1 release and retry. Core may have changed; your draft is preserved.')


def deploy(server,values):
    schemas=definitions(server)
    for package,settings in validate_all(server,values).items():exchange(server,package,schemas[package]['schema'],settings)


def register(server):
    @server.app.get('/api/editor/app-settings')
    def available():return jsonify(apps=definitions(server))

    @server.app.post('/api/editor/app-settings/read')
    def read():
        from editor import EditError
        body=request.get_json(silent=True) or {}
        if not isinstance(body,dict):raise EditError('Choose an app to read settings from.')
        with server.device_lock:
            snapshot=server.connection.get('snapshot') or {}
            if not snapshot.get('device_id') or body.get('device_id')!=snapshot['device_id']:raise EditError('Reconnect to the same Core before reading app settings.')
            if server.adb('-s',server.connection['target'],'shell','getprop','ro.serialno')!=snapshot['device_id']:raise EditError('The connected Core changed. Reconnect before reading app settings.')
            schemas=definitions(server);package=body.get('package')
            if not isinstance(package,str) or package not in schemas:raise EditError('Choose an installed app with supported Studio settings.')
            values=exchange(server,package,schemas[package]['schema'])
            return jsonify(values=values)
