"""Reviewed catalog and bounded, explicit package installation. No remote scripts."""
import copy
import hashlib
import json
import re
import struct
import subprocess
import tempfile
import threading
import time
from pathlib import Path
from urllib.parse import urlsplit
from urllib.request import Request, build_opener, HTTPRedirectHandler
from flask import jsonify, request
import updates

CATALOG_URL = 'https://raw.githubusercontent.com/qlerup/ultrabar-store/main/catalog.json'
ASSET_PREFIX = 'https://github.com/qlerup/ultrabar-store/releases/download/'
MAX_SIZE = 256 * 1024 * 1024
ID = re.compile(r'[a-z][a-z0-9]*(?:\.[a-z][a-z0-9-]*)+')
ANDROID_ID = re.compile(r'[A-Za-z][A-Za-z0-9_]*(?:\.[A-Za-z][A-Za-z0-9_]*)+')
HEX = re.compile(r'[a-f0-9]{64}')

class StoreError(ValueError):
    pass

class SafeRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        parsed = urlsplit(newurl)
        if parsed.scheme != 'https' or parsed.hostname not in ('github.com','release-assets.githubusercontent.com','objects.githubusercontent.com','raw.githubusercontent.com') or parsed.username or parsed.password:
            raise StoreError('The package redirected outside the approved download hosts.')
        return super().redirect_request(req, fp, code, msg, headers, newurl)

def fetch(url, limit, destination=None):
    try:
        req = Request(url, headers={'User-Agent':'UltraBar-Studio/'+updates.VERSION})
        with build_opener(SafeRedirect).open(req, timeout=15) as response:
            started = time.monotonic()
            total = 0
            data = bytearray()
            while True:
                chunk = response.read(65536)
                if not chunk: break
                total += len(chunk)
                if total > limit or time.monotonic()-started > 120:
                    raise StoreError('Download exceeded its size or time limit.')
                if destination is not None: destination.write(chunk)
                else: data.extend(chunk)
            return bytes(data) if destination is None else total
    except StoreError: raise
    except Exception as exc:
        raise StoreError('Could not reach the store. Check your connection and try again.') from exc

def valid_version(value):
    if not isinstance(value,str) or not re.fullmatch(r'(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)',value): raise StoreError('Invalid package version.')
    try: return updates.version_tuple(value)
    except updates.UpdateError as exc: raise StoreError('Invalid package version.') from exc

def validate_entry(entry):
    if not isinstance(entry, dict): raise StoreError('Invalid catalog entry.')
    p = copy.deepcopy(entry)
    if p.get('schemaVersion') != 1 or not ID.fullmatch(str(p.get('id',''))): raise StoreError('Unsupported package manifest.')
    for field, maximum in [('name',100),('description',1000),('license',200)]:
        if not isinstance(p.get(field),str) or not 1 <= len(p[field]) <= maximum: raise StoreError('Incomplete package information.')
    valid_version(p.get('version'))
    if p.get('type') not in ('corebar-app','studio-plugin','corebar-widget'): raise StoreError('Unknown package type.')
    compatibility=p.get('compatibility',{})
    valid_version(compatibility.get('minStudioVersion'))
    if type(compatibility.get('hostApi')) is not int: raise StoreError('Invalid host API.')
    for key in ('models','lineosVersions','abis'):
        values=compatibility.get(key,[])
        if not isinstance(values,list) or len(values)>32 or any(not isinstance(v,str) or not re.fullmatch(r'[A-Za-z0-9_.-]{1,60}',v) for v in values): raise StoreError('Invalid compatibility declaration.')
    permissions=p.get('permissions')
    if not isinstance(permissions,list) or len(permissions)>100 or any(not isinstance(v,str) or not re.fullmatch(r'[A-Za-z][A-Za-z0-9_.]{0,150}',v) for v in permissions): raise StoreError('Invalid permissions.')
    artifact=p.get('artifact',{})
    url=artifact.get('url','')
    if not isinstance(url,str) or not url.startswith(ASSET_PREFIX) or not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.-]*/[A-Za-z0-9][A-Za-z0-9_.-]*',url[len(ASSET_PREFIX):]): raise StoreError('Package must be a versioned asset in the official store repository.')
    if type(artifact.get('size')) is not int or not 0 < artifact['size'] <= MAX_SIZE or not HEX.fullmatch(str(artifact.get('sha256',''))): raise StoreError('Invalid artifact checksum or size.')
    if p['type']=='corebar-app':
        android=p.get('android',{})
        if not ANDROID_ID.fullmatch(str(android.get('packageId',''))) or android['packageId'].startswith(('android.','com.android.','com.ultrabar.')): raise StoreError('Invalid or reserved Android package ID.')
        if type(android.get('versionCode')) is not int or android['versionCode']<1 or type(android.get('minSdk')) is not int or android['minSdk']<26 or not HEX.fullmatch(str(android.get('signerSha256',''))): raise StoreError('Invalid Android package metadata.')
    elif p['type']=='studio-plugin' and permissions:
        raise StoreError('Declarative Studio plugins cannot request permissions.')
    return p

def catalog():
    try: data=json.loads(fetch(CATALOG_URL+'?refresh='+str(int(time.time())//60),1024*1024))
    except (ValueError,UnicodeError) as exc: raise StoreError('The catalog is not valid JSON.') from exc
    if not isinstance(data,dict) or data.get('schemaVersion')!=1 or not isinstance(data.get('packages'),list) or len(data['packages'])>500: raise StoreError('Unsupported store catalog.')
    entries=[validate_entry(p) for p in data['packages']]
    if len({p['id'] for p in entries})!=len(entries): raise StoreError('Duplicate package IDs in catalog.')
    return entries

def plugin_templates(raw):
    try: data=json.loads(raw)
    except (ValueError,UnicodeError) as exc: raise StoreError('Invalid plugin JSON.') from exc
    if not isinstance(data,dict) or set(data)!={'pluginApi','widgets'} or data['pluginApi']!=1 or not isinstance(data['widgets'],list) or not 1<=len(data['widgets'])<=32: raise StoreError('Unsupported declarative plugin format.')
    result=[]
    for w in data['widgets']:
        if not isinstance(w,dict) or set(w)-{'name','kind','background','textColor','accent'}: raise StoreError('Plugins may contain widget presets only, not code or commands.')
        if not isinstance(w.get('name'),str) or not 1<=len(w['name'])<=100 or w.get('kind') not in ('clock','cpu','memory','gpu','disk'): raise StoreError('Invalid plugin widget.')
        for field in ('background','textColor','accent'):
            if field in w and not re.fullmatch(r'#[a-fA-F0-9]{6}',str(w[field])): raise StoreError('Invalid widget color.')
        result.append(dict(w))
    return result

def v2_signers(path):
    # Read signer identities from the APK v2 block. The approved SHA-256 pins the
    # entire artifact; Android's Package Manager verifies signatures at install.
    data=path.read_bytes()
    eocd=data.rfind(b'PK\x05\x06',max(0,len(data)-65557))
    if eocd<0 or eocd+22>len(data): raise StoreError('Invalid APK ZIP structure.')
    central=struct.unpack_from('<I',data,eocd+16)[0]
    if central<24 or central>len(data) or data[central-16:central]!=b'APK Sig Block 42': raise StoreError('The APK must have a v2 signing block.')
    length=struct.unpack_from('<Q',data,central-24)[0]
    start=central-length-8
    if start<0 or start+8>central-24 or struct.unpack_from('<Q',data,start)[0]!=length: raise StoreError('Invalid APK signature block.')
    def lp(buf,at=0):
        if at+4>len(buf): raise StoreError('Invalid APK signer record.')
        size=struct.unpack_from('<I',buf,at)[0];end=at+4+size
        if end>len(buf): raise StoreError('Invalid APK signer record.')
        return buf[at+4:end],end
    pos=start+8
    while pos<central-24:
        if pos+12>central-24: raise StoreError('Invalid APK signature pair.')
        size=struct.unpack_from('<Q',data,pos)[0];kind=struct.unpack_from('<I',data,pos+8)[0]
        end=pos+8+size
        if size<4 or end>central-24: raise StoreError('Invalid APK signature pair.')
        if kind==0x7109871a:
            signers,_=lp(data[pos+12:end]);certs=[];offset=0
            while offset<len(signers):
                signer,offset=lp(signers,offset);signed,_=lp(signer);_,after_digest=lp(signed)
                certificates,_=lp(signed,after_digest);cert,_=lp(certificates)
                certs.append(hashlib.sha256(cert).hexdigest())
            return certs
        pos=end
    raise StoreError('APK v2 signature is required.')

def inspect_apk(server,path,entry):
    try:
        r=subprocess.run([str(server.ROOT/'assets/android/aapt.exe'),'dump','badging',str(path)],capture_output=True,timeout=15,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
        info=r.stdout.decode('utf-8',errors='replace')
        if r.returncode: raise StoreError('Could not inspect APK metadata.')
        package=re.search(r"^package: name='([^']+)' versionCode='([0-9]+)'",info,re.M)
        sdk=re.search(r"^sdkVersion:'([0-9]+)'",info,re.M)
        permissions=set(re.findall(r"^uses-permission(?:-sdk-[0-9]+)?: name='([^']+)'",info,re.M))
        android=entry['android']
        if not package or package.group(1)!=android['packageId'] or int(package.group(2))!=android['versionCode'] or not sdk or int(sdk.group(1))!=android['minSdk']: raise StoreError('APK metadata does not match the approved catalog.')
        if 'application-debuggable' in info: raise StoreError('Debug APKs cannot be installed from the store.')
        if permissions!=set(entry['permissions']): raise StoreError('APK permissions do not match the approved catalog.')
        if v2_signers(path)!=[android['signerSha256']]: raise StoreError('APK signing identity does not match the approved catalog.')
    except StoreError: raise
    except Exception as exc: raise StoreError('The APK could not be verified.') from exc

class Store:
    def __init__(self,server):
        self.server=server;self.lock=threading.RLock();self.job=None
    def records(self):
        try:
            data=json.loads((self.server.DATA_DIR/'store/installed.json').read_text())
            if not isinstance(data,dict): raise ValueError()
            return data
        except FileNotFoundError:return {}
        except (OSError,ValueError) as exc:raise StoreError('Could not read installed packages. Existing records were preserved.') from exc
    def save(self,data):
        from editor import atomic_json
        atomic_json(self.server.DATA_DIR/'store/installed.json',data)
    def key(self,p,device): return p['id']+(':'+device if p['type']=='corebar-app' else ':pc')
    def templates(self):
        with self.lock:
            return [dict(widget,_storePackage=p['id']) for p in self.records().values() if p['type']=='studio-plugin' for widget in p.get('widgets',[])]
    def status(self):
        with self.lock:return copy.deepcopy(self.job)
    def update_job(self,**values):
        with self.lock:self.job.update(values)
    def start(self,body):
        if not isinstance(body,dict) or not ID.fullmatch(str(body.get('id',''))):raise StoreError('Choose a package from the store.')
        with self.lock:
            if self.job and self.job['state']=='running':raise StoreError('Another installation is already running.')
            self.job=dict(state='running',message='Checking approved package...',id=body['id'])
        threading.Thread(target=self.install,args=(dict(body),),daemon=True,name='StudioStoreInstall').start()
        return self.status()
    def install(self,body):
        server=self.server
        try:
            p=next((p for p in catalog() if p['id']==body['id']),None)
            if not p or p['version']!=body.get('version') or p['artifact']['sha256']!=body.get('sha256'):raise StoreError('The catalog changed. Refresh the store and review the package again.')
            if valid_version(p['compatibility']['minStudioVersion'])>valid_version(updates.VERSION) or p['compatibility']['hostApi']!=1:raise StoreError('Update Studio before installing this package.')
            if p['type']=='corebar-widget':raise StoreError('Native renderer packages are not supported by this store version.')
            device=body.get('device_id') or ''
            if p['type']=='corebar-app' and not device:raise StoreError('Connect to CoreBAR before installing this app.')
            with self.lock:
                old=self.records().get(self.key(p,device))
            if old and valid_version(old['version'])>valid_version(p['version']):raise StoreError('Package downgrades are not supported.')
            self.update_job(message='Downloading and verifying package...')
            with tempfile.TemporaryDirectory(prefix='ultrabar-store-') as folder:
                path=Path(folder)/('package.apk' if p['type']=='corebar-app' else 'plugin.json')
                with path.open('wb') as out: size=fetch(p['artifact']['url'],min(p['artifact']['size'],MAX_SIZE),out)
                if size!=p['artifact']['size'] or hashlib.sha256(path.read_bytes()).hexdigest()!=p['artifact']['sha256']:raise StoreError('Package integrity check failed. Nothing was installed.')
                record=dict(id=p['id'],name=p['name'],version=p['version'],type=p['type'],artifact=p['artifact'],device_id=device if p['type']=='corebar-app' else None)
                if p['type']=='studio-plugin':
                    if size>65536:raise StoreError('Plugin preset file is too large.')
                    record['widgets']=plugin_templates(path.read_bytes())
                else:
                    inspect_apk(server,path,p)
                    with server.device_lock:
                        current=server.connection['snapshot'] or {}
                        target=server.connection['target']
                        if current.get('device_id')!=device or not target:raise StoreError('The connected Core changed. Reconnect and try again.')
                        if server.adb('-s',target,'shell','getprop','ro.serialno')!=device:raise StoreError('The connected Core identity changed.')
                        c=p['compatibility']
                        if c.get('models') and current.get('model') not in c['models']:raise StoreError('This app does not support the connected model.')
                        abi=server.adb('-s',target,'shell','getprop','ro.product.cpu.abi')
                        if c.get('abis') and abi not in c['abis']:raise StoreError('This app does not support the connected CPU.')
                        if int(server.adb('-s',target,'shell','getprop','ro.build.version.sdk'))<p['android']['minSdk']:raise StoreError('This app requires a newer Android version.')
                        if c.get('lineosVersions'):
                            dump=server.adb('-s',target,'shell','dumpsys','package','com.ultrabar.launch').split('Hidden system packages:',1)[0]
                            version=re.search(r'^\s*versionName=(\S+)',dump,re.M)
                            if not version or version.group(1) not in c['lineosVersions']:raise StoreError('This app does not support the connected LineOS version.')
                        self.update_job(message='Installing on CoreBAR. Keep the connection open...')
                        result=subprocess.run([str(server.ADB),'-s',target,'install','-r',str(path)],capture_output=True,timeout=120,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
                        if result.returncode or 'Success' not in result.stdout.decode(errors='replace'):raise StoreError('Android rejected the installation. The existing app was not uninstalled. Check its signing identity, version and available storage.')
                        dump=server.adb('-s',target,'shell','dumpsys','package',p['android']['packageId']).split('Hidden system packages:',1)[0]
                        if not re.search(r'\bversionCode='+str(p['android']['versionCode'])+r'\b',dump):raise StoreError('Installation completed but its version could not be verified. Check Core before retrying.')
                        record['android']=p['android']
                with self.lock:
                    records=self.records();records[self.key(p,device)]=record;self.save(records)
            self.update_job(state='complete',message='Installed. '+('Find the presets in Widget library > Studio & App Store.' if p['type']=='studio-plugin' else 'Find the app in the CoreBAR app list.'))
        except Exception as exc:
            text=str(exc) if isinstance(exc,(StoreError,server.DeviceError)) else 'Installation could not be completed. Check the connection and retry; Core may already have installed the package.'
            self.update_job(state='error',message=text)
    def remove_plugin(self,package_id):
        with self.lock:
            if self.job and self.job['state']=='running':raise StoreError('Wait for the current installation to finish.')
            records=self.records();key=package_id+':pc'
            if key not in records or records[key]['type']!='studio-plugin':raise StoreError('Installed plugin not found.')
            del records[key];self.save(records)
        return dict(ok=True)

def register_store(server):
    store=Store(server);server.store=store
    @server.app.errorhandler(StoreError)
    def error(exc):return jsonify(error=str(exc)),400
    @server.app.get('/api/store')
    def get_store():
        with store.lock:installed=list(store.records().values())
        return jsonify(packages=catalog(),installed=installed,job=store.status())
    @server.app.get('/api/store/installed')
    def installed():
        with store.lock:return jsonify(installed=list(store.records().values()),widgets=store.templates(),job=store.status())
    @server.app.post('/api/store/install')
    def install():return jsonify(store.start(request.get_json(silent=True))),202
    @server.app.get('/api/store/job')
    def job():return jsonify(job=store.status())
    @server.app.post('/api/store/remove-plugin')
    def remove():
        body=request.get_json(silent=True) or {}
        if not ID.fullmatch(str(body.get('id',''))):raise StoreError('Invalid plugin ID.')
        return jsonify(store.remove_plugin(body['id']))
