"""Reviewed catalog and bounded, explicit package installation. No remote scripts."""
import io
import copy
import hashlib
import json
import re
import struct
import subprocess
import tempfile
import threading
import time
import secrets
import webbrowser
from pathlib import Path
from urllib.parse import urlsplit
from urllib.request import Request, build_opener, HTTPRedirectHandler
from flask import jsonify, request
import updates
import screen_sync
import app_settings_contract
import bundle_contract
import studio_contract
import uuid

CATALOG_URL = 'https://raw.githubusercontent.com/qlerup/ultrabar-store/catalog/catalog.json'
ASSET_PREFIX = 'https://github.com/qlerup/ultrabar-store/releases/download/'
MAX_SIZE = 256 * 1024 * 1024
ID = re.compile(r'[a-z][a-z0-9]*(?:\.[a-z][a-z0-9-]*)+')
ANDROID_ID = re.compile(r'[A-Za-z][A-Za-z0-9_]*(?:\.[A-Za-z][A-Za-z0-9_]*)+')
HEX = re.compile(r'[a-f0-9]{64}')

class StoreError(ValueError):
    pass


class StoreCancelled(StoreError):
    pass


def check_cancel(cancel):
    if cancel is not None and cancel.is_set():
        raise StoreCancelled('Update cancelled. Your existing library and Core setup are unchanged.')


class CancellableWriter:
    def __init__(self,output,cancel):self.output=output;self.cancel=cancel
    def write(self,data):
        check_cancel(self.cancel)
        return self.output.write(data)


def package_links(package):
    if package.get('origin')=='local':return {}
    value=package.get('source','')
    if not isinstance(value,str):return {}
    try:source=urlsplit(value)
    except (ValueError,TypeError):return {}
    parts=source.path.strip('/').split('/')
    if source.scheme!='https' or source.netloc!='github.com' or source.query or source.fragment or len(parts)<2:return {}
    owner,repo=parts[:2]
    if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9-]{0,38}',owner) or not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.-]{0,99}',repo):return {}
    if len(parts)>2 and parts[2] not in ('blob','tree'):return {}
    base='https://github.com/'+owner+'/'+repo
    return dict(repository=base,issues=base+'/issues',pulls=base+'/pulls')

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

def validate_icon_metadata(icon):
    if not isinstance(icon,dict) or set(icon)!={'url','size','sha256'}:raise StoreError('An icon needs url, size and sha256.')
    url=icon['url']
    if not isinstance(url,str) or not url.startswith(ASSET_PREFIX) or not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.-]*/[A-Za-z0-9][A-Za-z0-9_.-]*\.png',url[len(ASSET_PREFIX):]):raise StoreError('Icon must be a PNG asset in the official store repository.')
    if type(icon['size']) is not int or not 0<icon['size']<=262144 or not HEX.fullmatch(str(icon['sha256'])):raise StoreError('Invalid icon size or checksum.')

def validate_icon_bytes(raw,icon):
    from PIL import Image
    if len(raw)!=icon['size'] or hashlib.sha256(raw).hexdigest()!=icon['sha256']:raise StoreError('Icon checksum or size mismatch.')
    try:
        with Image.open(io.BytesIO(raw)) as im:
            if im.format!='PNG' or im.size not in ((256,256),(512,512)) or getattr(im,'n_frames',1)!=1:raise StoreError('Icon must be a static 256x256 or 512x512 PNG.')
            im.verify()
        with Image.open(io.BytesIO(raw)) as im:im.load()
    except StoreError:raise
    except Exception as exc:raise StoreError('Invalid PNG icon.') from exc
    return raw

def validate_entry(entry):
    if not isinstance(entry, dict): raise StoreError('Invalid catalog entry.')
    p = copy.deepcopy(entry)
    try:bundle_contract.validate(p,widget_package)
    except ValueError as exc:raise StoreError(str(exc)) from exc
    if 'settings' in p:
        if p.get('type')!='corebar-app':raise StoreError('App settings require a corebar-app package.')
        try:app_settings_contract.validate_schema(p['settings'])
        except ValueError as exc:raise StoreError(str(exc)) from exc
        if valid_version(p.get('compatibility',{}).get('minStudioVersion'))<(0,45,0):raise StoreError('Settings API 1 requires Studio 0.45.0 or newer.')
    if p.get('schemaVersion') != 1 or not ID.fullmatch(str(p.get('id',''))): raise StoreError('Unsupported package manifest.')
    for field, maximum in [('name',100),('description',1000),('license',200)]:
        if not isinstance(p.get(field),str) or not 1 <= len(p[field]) <= maximum: raise StoreError('Incomplete package information.')
    valid_version(p.get('version'))
    source=urlsplit(p.get('source',''))
    owner=source.path.strip('/').split('/')[0] if source.scheme=='https' and source.netloc=='github.com' else ''
    if 'publisher' in p and (not isinstance(p['publisher'],str) or not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9-]{0,38}',p['publisher']) or p['publisher'].lower()!=owner.lower()):
        raise StoreError('Package uploader must match the source repository owner.')
    if 'publisher' not in p and re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9-]{0,38}',owner):p['publisher']=owner
    if 'icon' in p:validate_icon_metadata(p['icon'])
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
    elif p['type'] in ('studio-plugin','corebar-widget') and permissions:
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
    if not isinstance(data,dict) or set(data)!={'pluginApi','widgets'} or type(data['pluginApi']) is not int or data['pluginApi']!=1 or not isinstance(data['widgets'],list) or not 1<=len(data['widgets'])<=32: raise StoreError('Unsupported declarative plugin format.')
    result=[]
    for w in data['widgets']:
        if not isinstance(w,dict) or set(w)-{'name','kind','background','textColor','accent'}: raise StoreError('Plugins may contain widget presets only, not code or commands.')
        if not isinstance(w.get('name'),str) or not 1<=len(w['name'])<=100 or w.get('kind') not in ('clock','cpu','memory','gpu','disk'): raise StoreError('Invalid plugin widget.')
        for field in ('background','textColor','accent'):
            if field in w and not re.fullmatch(r'#[a-fA-F0-9]{6}',str(w[field])): raise StoreError('Invalid widget color.')
        result.append(dict(w))
    return result

def widget_package(raw):
    from bambu_contract import FIELDS as BAMBU_FIELDS,validate as validate_bambu
    try:data=json.loads(raw)
    except (ValueError,UnicodeError) as exc:raise StoreError('Invalid widget package JSON.') from exc
    if not isinstance(data,dict) or set(data)!={'widgetApi','runtime','widgets'} or type(data['widgetApi']) is not int or data['widgetApi']!=1 or data['runtime']!='studio-native-v1':
        raise StoreError('Unsupported widget package runtime.')
    widgets=data['widgets']
    if not isinstance(widgets,list) or not 1<=len(widgets)<=32:raise StoreError('A package must contain 1-32 widgets.')
    result=[];ids=set()
    for w in widgets:
        if not isinstance(w,dict) or set(w)-({'id','name','kind','background','textColor','accent','hourFormat','showSeconds','showDate','kindOptions','studio'}|BAMBU_FIELDS):raise StoreError('Unsupported widget field. Executable code is not supported.')
        key=w.get('id')
        if not isinstance(key,str) or not re.fullmatch(r'[a-z][a-z0-9-]{0,63}',key) or key in ids:raise StoreError('Widget IDs must be unique.')
        ids.add(key)
        base={k:v for k,v in w.items() if k in ('name','kind','background','textColor','accent')}
        if w.get('kind')=='bambu':
            if not isinstance(w.get('name'),str) or not 1<=len(w['name'])<=100:raise StoreError('Invalid printer widget name.')
            for color in ('background','textColor','accent'):
                if color in w and not re.fullmatch(r'#[a-fA-F0-9]{6}',str(w[color])):raise StoreError('Invalid widget color.')
        else:plugin_templates(json.dumps(dict(pluginApi=1,widgets=[base])).encode())
        try:validate_bambu(w)
        except ValueError as exc:raise StoreError(str(exc)) from exc
        if w.get('hourFormat','24') not in ('12','24') or any(type(w[k]) is not bool for k in ('showSeconds','showDate') if k in w):raise StoreError('Invalid clock settings.')
        if w['kind']!='clock' and any(k in w for k in ('hourFormat','showSeconds','showDate')):raise StoreError('Clock settings require a clock widget.')
        if 'kindOptions' in w:
            options=w['kindOptions']
            if not isinstance(options,list) or not 2<=len(options)<=3 or any(k not in ('cpu','memory','gpu') for k in options) or len(set(options))!=len(options) or w['kind'] not in options:
                raise StoreError('Choose 2-3 distinct CPU, RAM or GPU kinds including the default kind.')
        if 'studio' in w:
            try:studio_contract.validate(w['studio'],w['kind'])
            except ValueError as exc:raise StoreError(str(exc)) from exc
            if 'kindOptions' in w:
                for field in w['studio'].get('settings',{}).get('fields',[]):
                    if field['key']=='kind' and not {option['value'] for option in field['options']}<=set(w['kindOptions']):
                        raise StoreError('Studio kind choices must stay within the widget measurement options.')
        result.append(dict(w,_widgetPackage=True))
    return result


def require_widget_version(widgets,manifest):
    if any('studio' in w for w in widgets) and valid_version(manifest['compatibility']['minStudioVersion'])<studio_contract.MIN_VERSION:
        raise StoreError('App-owned Studio panels require Studio 0.49.0 or newer.')
    if manifest.get('type')=='corebar-widget' and any(w.get('kind')=='bambu' for w in widgets) and valid_version(manifest['compatibility']['minStudioVersion'])<(0,48,0):
        raise StoreError('Studio-managed Bambu widgets require Studio 0.48.0 or newer.')
    if any(w.get('kind')=='bambu' for w in widgets) and valid_version(manifest['compatibility']['minStudioVersion'])<(0,46,0):
        raise StoreError('Bambu liquid widgets must declare Studio 0.46.0 or newer.')


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
        embedded=bundle_contract.inspect_apk(path,entry)
        if embedded is not None:bundle_contract.validate(dict(entry,bundledWidgets=embedded),widget_package)
        if entry.get('settings'):app_settings_contract.inspect_apk(path,entry['settings'])
        r=subprocess.run([str(server.ROOT/'assets/android/aapt.exe'),'dump','badging',str(path)],capture_output=True,timeout=15,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
        info=r.stdout.decode('utf-8',errors='replace')
        if r.returncode: raise StoreError('Could not inspect APK metadata.')
        if entry.get('settings'):
            manifest=subprocess.run([str(server.ROOT/'assets/android/aapt.exe'),'dump','xmltree',str(path),'AndroidManifest.xml'],capture_output=True,timeout=15,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
            if manifest.returncode:raise StoreError('Could not inspect the app settings receiver.')
            app_settings_contract.validate_receiver(manifest.stdout.decode('utf-8',errors='replace'),entry['android']['packageId'])
        package=re.search(r"^package: name='([^']+)' versionCode='([0-9]+)'",info,re.M)
        sdk=re.search(r"^sdkVersion:'([0-9]+)'",info,re.M)
        permissions=set(re.findall(r"^uses-permission(?:-sdk-[0-9]+)?: name='([^']+)'",info,re.M))
        android=entry['android']
        if not package or package.group(1)!=android['packageId'] or int(package.group(2))!=android['versionCode'] or not sdk or int(sdk.group(1))!=android['minSdk']: raise StoreError('APK metadata does not match the approved catalog.')
        if 'application-debuggable' in info: raise StoreError('Debug APKs cannot be installed from the store.')
        if permissions!=set(entry['permissions']): raise StoreError('APK permissions do not match the approved catalog.')
        if v2_signers(path)!=[android['signerSha256']]: raise StoreError('APK signing identity does not match the approved catalog.')
        return embedded
    except StoreError: raise
    except Exception as exc: raise StoreError('The APK could not be verified.') from exc

class Store:
    def __init__(self,server):
        self.server=server;self.lock=threading.RLock();self.job=None;self.icon_sources={};self.local_pending=None;self.github_links={};self.local_preview_lock=threading.Lock()
        self.cancel_event=None
        from package_stats import PackageStats
        self.stats=PackageStats()
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
    def key(self,p,device): return p['id']+':pc'
    @staticmethod
    def previous_record(p,records):
        current=records.get(p['id']+':pc')
        if current:return current
        # Repair the short-lived duplicate registration without touching other packages.
        if p['id']=='studio.bambu' and p.get('type')=='corebar-widget' and p.get('source','').startswith('https://github.com/qlerup/ultrabar-bambu/blob/'):
            alias=records.get('studio.bambu.widget:pc')
            if alias and alias.get('type')=='corebar-widget' and alias.get('source','').startswith('https://github.com/qlerup/ultrabar-bambu/blob/'):return alias

    def migrate_bambu_draft(self,draft):
        record=self.records().get('studio.bambu:pc')
        if not record or record.get('type')!='corebar-widget' or not record.get('source','').startswith('https://github.com/qlerup/ultrabar-bambu/blob/'):return False
        changed=False;applicable=False
        for profile in draft.get('profiles',[]):
            for widget in profile.get('homeData',[]):
                param=widget.get('param');payload=param.get('payload') if isinstance(param,dict) else None
                params=payload.get('params') if isinstance(payload,dict) else None
                if not isinstance(params,dict):continue
                if params.get('kind')=='bambu' and params.get('packageId') in ('studio.bambu','studio.bambu.widget'):
                    applicable=True
                    before=dict(params)
                    params['packageId']='studio.bambu';params['packageVersion']=record['version']
                    if params.get('companionApp')=='dk.ultrabar.bambu':params.pop('companionApp')
                    changed=changed or before!=params
        if applicable:
            background=draft.get('background_apps',[])
            draft['background_apps']=[a for a in background if a['id']!='dk.ultrabar.bambu']
            changed=changed or background!=draft['background_apps']
            if isinstance(draft.get('app_settings'),dict) and 'dk.ultrabar.bambu' in draft['app_settings']:
                draft['app_settings'].pop('dk.ultrabar.bambu');changed=True
        return changed
    def remember_icons(self,packages):
        self.stats.remember(packages)
        with self.lock:
            for p in packages:
                links=package_links(p)
                if links:self.github_links[p['id']]=links
                if p.get('icon'):
                    validate_icon_metadata(p['icon']);self.icon_sources[p['icon']['sha256']]=p['icon']
    def icon(self,digest):
        with self.lock:metadata=self.icon_sources.get(digest)
        if not metadata:raise StoreError('Icon is not in the loaded catalog.')
        path=self.server.DATA_DIR/'store/icons'/(digest+'.png')
        try:return validate_icon_bytes(path.read_bytes(),metadata)
        except (OSError,StoreError):pass
        raw=validate_icon_bytes(fetch(metadata['url'],262144),metadata)
        path.parent.mkdir(parents=True,exist_ok=True)
        path.write_bytes(raw)
        return raw
    def templates(self):
        with self.lock:
            templates=[dict(widget,_storePackage=p['id'],_storeVersion=p['version'],_studio=studio_contract.resolve(widget),**({'_bundledApp':dict(id=p['android']['packageId'],name=p['name'])} if p.get('bundledWidgets') else {})) for p in self.records().values() if p['type'] in ('studio-plugin','corebar-widget') or p.get('bundledWidgets') for widget in p.get('widgets',[])]
            templates.extend(dict(id=p['android']['packageId'],name=p['name'],type='APPS',iconScale=100,_storePackage=p['id'],_storeVersion=p['version']) for p in self.records().values() if p.get('deferred') and p['type']=='corebar-app' and not p.get('bundledWidgets'))
            return templates
    def status(self):
        with self.lock:return copy.deepcopy(self.job)
    @staticmethod
    def fingerprint(record):return record['version']+'|'+record['artifact']['sha256']
    def deployed_path(self,device):return self.server.DATA_DIR/'store/deployed'/(hashlib.sha256(device.encode()).hexdigest()+'.json')
    def pending_deploy(self,device=None):
        deployed={}
        if device:
            try:deployed=json.loads(self.deployed_path(device).read_text(encoding='utf-8'))
            except FileNotFoundError:pass
            except (OSError,ValueError) as exc:raise StoreError('Could not read package activation status. Saved records were preserved.') from exc
            if not isinstance(deployed,dict):raise StoreError('Invalid package activation status.')
        with self.lock:return {p['id']:dict(name=p['name'],version=p['version']) for p in self.records().values() if p.get('requiresDeploy') and deployed.get(p['id'])!=self.fingerprint(p)}
    def deployment_plan(self,profiles,background):
        apps={w['id'] for p in profiles for w in p['homeData'] if w['type']=='APPS'}|{a['id'] for a in background}
        widgets=set()
        for profile in profiles:
            for widget in profile['homeData']:
                param=widget.get('param');payload=param.get('payload') if isinstance(param,dict) else None
                params=payload.get('params') if isinstance(payload,dict) else None
                if isinstance(params,dict) and isinstance(params.get('packageId'),str):widgets.add(params['packageId'])
        with self.lock:return {p['id']:self.fingerprint(p) for p in self.records().values() if p['id'] in widgets or p.get('android',{}).get('packageId') in apps}
    def mark_deployed(self,device,plan):
        if not plan:return
        from editor import atomic_json
        path=self.deployed_path(device)
        with self.lock:
            try:deployed=json.loads(path.read_text(encoding='utf-8'))
            except FileNotFoundError:deployed={}
            except (OSError,ValueError) as exc:raise StoreError('Could not save package activation status. Core may already have updated; your draft and backup are preserved.') from exc
            if not isinstance(deployed,dict):raise StoreError('Invalid package activation status. Core may already have updated.')
            current={p['id']:self.fingerprint(p) for p in self.records().values()}
            deployed.update({key:value for key,value in plan.items() if current.get(key)==value})
            atomic_json(path,deployed)
    @staticmethod
    def update_widget_versions(profiles,plan):
        for profile in profiles:
            for widget in profile['homeData']:
                param=widget.get('param');payload=param.get('payload') if isinstance(param,dict) else None
                params=payload.get('params') if isinstance(payload,dict) else None
                if isinstance(params,dict) and isinstance(params.get('packageId'),str) and params['packageId'] in plan and payload.get('action')=='studioNative':params['packageVersion']=plan[params['packageId']].split('|',1)[0]
    def update_job(self,**values):
        with self.lock:
            if self.job.get('cancel_requested') and not values.get('state'):return
            self.job.update(values)
    def cancel(self,body):
        with self.lock:
            if not isinstance(body,dict) or not self.job or body.get('request_id')!=self.job.get('request_id'):
                raise StoreError('This update changed. Refresh its status before cancelling.')
            if self.job['state']!='running':return copy.deepcopy(self.job)
            if not self.job.get('can_cancel') or self.cancel_event is None:
                raise StoreError('The verified package is being saved and can no longer be cancelled. You can close this window.')
            self.cancel_event.set()
            self.job.update(cancel_requested=True,message='Cancelling update. You can close this window while the current network request finishes.')
            return copy.deepcopy(self.job)
    def start(self,body):
        if not isinstance(body,dict) or not ID.fullmatch(str(body.get('id',''))):raise StoreError('Choose a package from the store.')
        with self.lock:
            if self.job and self.job['state']=='running':raise StoreError('Another installation is already running.')
            self.job=dict(state='running',message='Checking approved package...',id=body['id'],request_id=uuid.uuid4().hex,can_cancel=True)
            self.cancel_event=threading.Event();cancel=self.cancel_event
        threading.Thread(target=self.install,args=(dict(body),None,cancel),daemon=True,name='StudioStoreInstall').start()
        return self.status()
    def preview_local(self,body=None):
        if not self.local_preview_lock.acquire(blocking=False):raise StoreError('A folder check is already running.')
        try:return self._preview_local(body)
        finally:self.local_preview_lock.release()

    def _preview_local(self,body):
        with self.lock:self.local_pending=None
        if body is not None and (not isinstance(body,dict) or set(body)-{'folder'}):raise StoreError('Choose a package folder.')
        folder=body.get('folder') if body else None
        if folder is not None:
            if not isinstance(folder,str) or not 1<=len(folder.strip())<=4096 or not Path(folder.strip()).is_absolute():raise StoreError('Enter the full folder path, or use Browse.')
            folder=folder.strip()
        else:
            picker=getattr(self.server,'package_folder_picker',None)
            if picker is None:raise StoreError('Browse is available in the Studio desktop app. You can also paste a folder path.')
            try:selected=picker()
            except Exception as exc:raise StoreError('Could not open the folder chooser. Paste the folder path instead.') from exc
            if not selected:return dict(cancelled=True)
            folder=selected[0]
        from local_packages import read_folder
        try:p,raw,icon=read_folder(self.server,folder)
        except StoreError:raise
        except (ValueError,OSError,TypeError,KeyError,AttributeError):raise StoreError('The selected folder does not contain a valid package.') from None
        if valid_version(p['compatibility']['minStudioVersion'])>valid_version(updates.VERSION) or p['compatibility']['hostApi']!=1:raise StoreError('This package requires a newer or unsupported Studio version. Update Studio before adding it.')
        token=secrets.token_urlsafe(32)
        with self.lock:
            if self.job and self.job['state']=='running':raise StoreError('Wait for the current installation to finish.')
            self.local_pending=(token,time.monotonic()+600,p,raw)
            self.remember_icons([p])
            path=self.server.DATA_DIR/'store/icons'/(p['icon']['sha256']+'.png');path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(icon)
        files=['icon.png','app.apk' if p['type']=='corebar-app' else 'widget.json' if p['type']=='corebar-widget' else 'plugin.json']
        if p['type']=='corebar-app':files.insert(0,'manifest.json')
        checks=[dict(label='Required package files',detail=', '.join(files)),dict(label='Package format and integrity',detail='Manifest, settings, checksums and icon validated.'),dict(label='Studio compatibility',detail='Compatible with Studio '+updates.VERSION)]
        if p['type']=='corebar-app':checks.append(dict(label='Android identity and signature',detail='Release APK, package identity, permissions and signer validated.'))
        return dict(token=token,package=p,folder_name=Path(folder).name,checks=checks)

    def manual_packages(self):
        try:
            data=json.loads((self.server.DATA_DIR/'store/manual.json').read_text(encoding='utf-8'))
            if not isinstance(data,dict):raise ValueError()
            return data
        except FileNotFoundError:return {}
        except (OSError,ValueError) as exc:raise StoreError('Could not read manual apps. Existing data was preserved.') from exc

    def add_local(self,body):
        if not isinstance(body,dict):raise StoreError('Check a package folder first.')
        with self.lock:
            pending=self.local_pending
            if not pending or not isinstance(body.get('token'),str) or not secrets.compare_digest(pending[0],body['token']) or time.monotonic()>pending[1]:raise StoreError('Folder check expired. Check the folder again.')
            _,_,p,raw=pending
            path=self.server.DATA_DIR/'store/manual-packages'/p['artifact']['sha256']
            path.parent.mkdir(parents=True,exist_ok=True)
            path.with_suffix('.tmp').write_bytes(raw);path.with_suffix('.tmp').replace(path)
            from editor import atomic_json
            packages=self.manual_packages();packages[p['id']]=p
            atomic_json(self.server.DATA_DIR/'store/manual.json',packages)
            self.local_pending=None
            return dict(package=p)
    def start_local(self,body):
        if not isinstance(body,dict):raise StoreError('Select a local package folder first.')
        with self.lock:
            if self.job and self.job['state']=='running':raise StoreError('Another installation is already running.')
            if body.get('id'):
                if not isinstance(body['id'],str):raise StoreError('Choose a manual app from Store.')
                p=self.manual_packages().get(body['id'])
                if not p:raise StoreError('Manual app not found. Add its folder again.')
                p=validate_entry(p)
                if p.get('origin')!='local' or not p['id'].startswith('local.'):raise StoreError('Invalid manual app registration.')
                if p['version']!=body.get('version') or p['artifact']['sha256']!=body.get('sha256'):raise StoreError('The manual app changed. Refresh Store and review it again.')
                try:
                    path=self.server.DATA_DIR/'store/manual-packages'/p['artifact']['sha256']
                    if path.stat().st_size!=p['artifact']['size']:raise StoreError('Manual app files changed. Add its folder again.')
                    raw=path.read_bytes()
                except OSError as exc:raise StoreError('Manual app files are missing. Add its folder again.') from exc
                if len(raw)!=p['artifact']['size'] or hashlib.sha256(raw).hexdigest()!=p['artifact']['sha256']:raise StoreError('Manual app files changed. Add its folder again.')
            else:
                pending=self.local_pending
                if not pending or not isinstance(body.get('token'),str) or not secrets.compare_digest(pending[0],body['token']) or time.monotonic()>pending[1]:
                    raise StoreError('Local preview expired. Select the folder again.')
                self.local_pending=None
                _,_,p,raw=pending
            self.job=dict(state='running',message='Verifying local development package...',id=p['id'],request_id=uuid.uuid4().hex,can_cancel=True)
            self.cancel_event=threading.Event();cancel=self.cancel_event
        threading.Thread(target=self.install,args=(dict(body),(p,raw),cancel),daemon=True,name='StudioLocalInstall').start()
        return self.status()
    def install(self,body,local=None,cancel=None):
        server=self.server
        try:
            check_cancel(cancel)
            p=local[0] if local else next((p for p in catalog() if p['id']==body['id']),None)
            check_cancel(cancel)
            if not local and (not p or p['version']!=body.get('version') or p['artifact']['sha256']!=body.get('sha256')):raise StoreError('The catalog changed. Refresh the store and review the package again.')
            if valid_version(p['compatibility']['minStudioVersion'])>valid_version(updates.VERSION) or p['compatibility']['hostApi']!=1:
                raise StoreError('Update Studio before installing this package. '+p['name']+' '+p['version']+' requires Studio '+p['compatibility']['minStudioVersion']+' or newer; installed: '+updates.VERSION+'.')
            device=body.get('device_id') or ''
            deferred=p['type']=='corebar-app'
            if screen_sync.applies(p):screen_sync.validate_identity(p)
            with self.lock:
                old=self.previous_record(p,self.records())
            self.update_job(name=p['name'],version=p['version'],is_update=bool(old and valid_version(p['version'])>valid_version(old['version'])))
            if old and valid_version(old['version'])>valid_version(p['version']):raise StoreError('Package downgrades are not supported.')
            self.update_job(message='Downloading and verifying package...')
            with tempfile.TemporaryDirectory(prefix='ultrabar-store-') as folder:
                path=Path(folder)/('package.apk' if p['type']=='corebar-app' else 'plugin.json')
                if local:path.write_bytes(local[1]);size=len(local[1])
                else:
                    with path.open('wb') as out: size=fetch(p['artifact']['url'],min(p['artifact']['size'],MAX_SIZE),CancellableWriter(out,cancel))
                check_cancel(cancel)
                self.update_job(message='Checking package integrity and contents…')
                if size!=p['artifact']['size'] or hashlib.sha256(path.read_bytes()).hexdigest()!=p['artifact']['sha256']:raise StoreError('Package integrity check failed. Nothing was installed.')
                record=dict(id=p['id'],name=p['name'],version=p['version'],type=p['type'],artifact=p['artifact'],device_id=device if p['type']=='corebar-app' else None,requiresDeploy=True)
                if p.get('publisher'):record['publisher']=p['publisher']
                if p.get('source'):record['source']=p['source']
                if local:record.update(origin='local',original_id=p['original_id'],description=p['description'],license=p['license'],compatibility=p['compatibility'])
                if p.get('icon'):record['icon']=copy.deepcopy(p['icon'])
                if p.get('settings'):record['settings']=copy.deepcopy(p['settings'])
                if p.get('bundledWidgets'):
                    record['bundledWidgets']=copy.deepcopy(p['bundledWidgets'])
                    record['widgets']=bundle_contract.validate(p,widget_package)
                if p['type'] in ('studio-plugin','corebar-widget'):
                    if size>65536:raise StoreError('Plugin preset file is too large.')
                    record['widgets']=widget_package(path.read_bytes()) if p['type']=='corebar-widget' else plugin_templates(path.read_bytes())
                    require_widget_version(record['widgets'],p)
                elif deferred:
                    embedded=inspect_apk(server,path,p)
                    if isinstance(embedded,dict):
                        p=dict(p,bundledWidgets=embedded)
                        record.update(bundledWidgets=copy.deepcopy(embedded),widgets=bundle_contract.validate(p,widget_package))
                    record.update(deferred=True,device_id=None,android=copy.deepcopy(p['android']),compatibility=copy.deepcopy(p['compatibility']),permissions=list(p['permissions']))
                with self.lock:
                    check_cancel(cancel)
                    self.job['can_cancel']=False
                    self.update_job(message='Saving package to your PC library…')
                    if deferred:
                        cached=server.DATA_DIR/'store/app-packages'/(p['artifact']['sha256']+'.apk')
                        cached.parent.mkdir(parents=True,exist_ok=True)
                        cached.with_suffix('.tmp').write_bytes(path.read_bytes());cached.with_suffix('.tmp').replace(cached)
                        # Dependencies and the library share one non-cancellable commit.
                        from editor import atomic_json
                        dependencies=self.dependencies();dependencies[p['android']['packageId']]=p
                        atomic_json(cached.parent/'library.json', dependencies)
                    records=self.records();records[self.key(p,device)]=record
                    if p['id']=='studio.bambu' and p['type']=='corebar-widget':records.pop('studio.bambu.widget:pc',None)
                    self.save(records)
            self.update_job(state='complete',message='Installed. '+('Find the widgets in Studio & App Store. Drag onto Core, configure, then Deploy to activate.' if deferred or p['type'] in ('studio-plugin','corebar-widget') else 'Find the app in the CoreBAR app list.'))
        except Exception as exc:
            if isinstance(exc,StoreCancelled) or (cancel is not None and cancel.is_set()):
                self.update_job(state='cancelled',can_cancel=False,message='Update cancelled. Your existing library and Core setup are unchanged.')
                return
            text=str(exc) if isinstance(exc,(StoreError,server.DeviceError)) else 'Installation could not be completed. Check the connection and retry; Core may already have installed the package.'
            self.update_job(state='error',can_cancel=False,message=text)

    def install_on_core(self,path,p,device,notify=None,background=None):
        # Caller holds device_lock, including when invoked during Deploy.
        server=self.server
        notify=notify or (lambda message:self.update_job(message=message))
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
        prepared = screen_sync.prepare(server, target, p) if screen_sync.applies(p) else None
        notify('Installing on CoreBAR. Keep the connection open…')
        result=subprocess.run([str(server.ADB),'-s',target,'install','-r',str(path)],capture_output=True,timeout=120,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
        if result.returncode or 'Success' not in result.stdout.decode(errors='replace'):raise StoreError('Android rejected the installation. The existing app was not uninstalled. Check its signing identity, version and available storage.')
        dump=server.adb('-s',target,'shell','dumpsys','package',p['android']['packageId']).split('Hidden system packages:',1)[0]
        if not re.search(r'\bversionCode='+str(p['android']['versionCode'])+r'\b',dump):raise StoreError('Installation completed but its version could not be verified. Check Core before retrying.')
        if prepared is not None:
            notify('Configuring Screen Sync for your connected VivoCubes…')
            if background is not None:screen_sync.configure(server,target,prepared,settings=background.get('settings',{}),background=True)
            else:screen_sync.configure(server, target, prepared)
        elif background is not None:
            self.start_background(p['android']['packageId'],background.get('settings',{}))

    def start_background(self,package_id,settings):
        server=self.server;target=server.connection['target']
        if settings.get('launch',True):
            result=server.adb('-s',target,'shell','am','start','-a','android.intent.action.MAIN','-c','android.intent.category.LAUNCHER','-p',package_id)
            if re.search(r'error|exception',result,re.I):raise StoreError('Could not launch the background app: '+package_id)
        else:server.adb('-s',target,'shell','am','force-stop',package_id)

    def stop_removed_background(self,previous,current,profiles=None):
        visible={w['id'] for p in profiles or [] for w in p.get('homeData',[]) if w.get('type')=='APPS'}
        removed={a['id'] for a in previous}-{a['id'] for a in current}-visible
        for package_id in sorted(removed):
            if package_id==screen_sync.PACKAGE_ID:screen_sync.start_sync(self.server,self.server.connection['target'],False)
            else:self.server.adb('-s',self.server.connection['target'],'shell','am','force-stop',package_id)

    def dependencies(self):
        try:
            data=json.loads((self.server.DATA_DIR/'store/app-packages/library.json').read_text(encoding='utf-8'))
            if not isinstance(data,dict):raise ValueError()
            return data
        except FileNotFoundError:return {}
        except (OSError,ValueError) as exc:
            raise StoreError('Could not read the Core app library. Install the required apps again from Store.') from exc

    def deploy_dependencies(self,profiles,device,notify,background_apps=None):
        # No device access or package work unless an app is placed in a profile.
        requested={w['id'] for p in profiles for w in p.get('homeData',[]) if w.get('type')=='APPS'}
        background={a['id']:a for a in background_apps or []}
        requested.update(background)
        bundled=[w.get('param',{}).get('payload',{}).get('params',{}) for p in profiles for w in p.get('homeData',[]) if w.get('param',{}).get('payload',{}).get('action')=='studioNative' and w.get('param',{}).get('payload',{}).get('params',{}).get('companionApp')]
        if not requested and not bundled:return
        with self.lock:
            dependencies=self.dependencies()
        by_store={p['id']:p for p in dependencies.values()}
        for params in bundled:
            package=by_store.get(params.get('packageId'))
            if package is None:raise StoreError('Install the widget’s bundled app package into the library before deploying.')
            templates=bundle_contract.validate(package,widget_package)
            if not templates or params['companionApp']!=package['android']['packageId'] or not any(t['id']==params.get('widgetKey') and t['kind']==params.get('kind') for t in templates):raise StoreError('The placed widget is not declared by its bundled app package.')
            requested.add(package['android']['packageId'])
        if not requested:return
        plan=[];existing_background=[]
        for package_id in sorted(requested):
            if not ANDROID_ID.fullmatch(package_id):raise StoreError('Invalid Core app widget. Add the app from the library again.')
            p=dependencies.get(package_id)
            if p is None:
                # Old profiles can contain app placeholders even after an APK was
                # removed. Preserve those as before; only staged Store apps and
                # explicit background requests are installation dependencies.
                if package_id not in background:continue
                target=self.server.connection['target']
                if package_id==screen_sync.PACKAGE_ID and package_id in background:raise StoreError('Install Vivo Screen Sync into the library before using it in the background.')
                # pm path exits 1 for an absent package, which adb() correctly
                # treats as a failed command. Listing has a successful empty result.
                installed=self.server.adb('-s',target,'shell','pm','list','packages',package_id)
                if 'package:'+package_id in installed.splitlines():
                    if package_id in background:existing_background.append(package_id)
                    continue
                raise StoreError('Add the missing Core app to the Studio library before deploying: '+package_id)
            validate_entry(p)
            if p['type']!='corebar-app' or p['android']['packageId']!=package_id:raise StoreError('Invalid Core app library package.')
            if screen_sync.applies(p):screen_sync.validate_identity(p)
            if valid_version(p['compatibility']['minStudioVersion'])>valid_version(updates.VERSION) or p['compatibility']['hostApi']!=1:raise StoreError('Update Studio before deploying '+p['name']+'.')
            path=self.server.DATA_DIR/'store/app-packages'/(p['artifact']['sha256']+'.apk')
            try:
                if path.stat().st_size!=p['artifact']['size']:raise StoreError('Core app package integrity check failed. Install it again from Store: '+p['name'])
                raw=path.read_bytes()
            except OSError as exc:raise StoreError('Core app package is missing. Install it again from Store: '+p['name']) from exc
            if hashlib.sha256(raw).hexdigest()!=p['artifact']['sha256']:
                raise StoreError('Core app package integrity check failed. Install it again from Store: '+p['name'])
            notify('Verifying '+p['name']+'…')
            inspect_apk(self.server,path,p)
            plan.append((path,p))
        for path,p in plan:
            notify('Preparing '+p['name']+' on CoreBAR…')
            self.install_on_core(path,p,device,notify,background=background.get(p['android']['packageId']))
        for package_id in existing_background:self.start_background(package_id,background[package_id].get('settings',{}))

    def remove_plugin(self,package_id):
        with self.lock:
            if self.job and self.job['state']=='running':raise StoreError('Wait for the current installation to finish.')
            records=self.records();key=package_id+':pc'
            if key not in records or (records[key]['type'] not in ('studio-plugin','corebar-widget') and not records[key].get('deferred')):raise StoreError('Installed plugin not found.')
            del records[key];self.save(records)
        return dict(ok=True)

def register_store(server):
    store=Store(server);server.store=store
    @server.app.errorhandler(StoreError)
    def error(exc):return jsonify(error=str(exc)),400
    @server.app.get('/api/store')
    def get_store():
        with store.lock:installed=list(store.records().values())
        packages=catalog()+list(store.manual_packages().values());store.remember_icons(installed+packages)
        return jsonify(packages=[dict(p,links=package_links(p)) for p in packages],installed=[dict(p,links=package_links(p)) for p in installed],manual=list(store.manual_packages().values()),job=store.status(),pending_deploy=store.pending_deploy((server.connection.get('snapshot') or {}).get('device_id')))
    @server.app.get('/api/store/installed')
    def installed():
        with store.lock:
            installed=list(store.records().values());manual=list(store.manual_packages().values());store.remember_icons(installed+manual)
            return jsonify(installed=[dict(p,links=package_links(p)) for p in installed],widgets=store.templates(),manual=manual,job=store.status(),pending_deploy=store.pending_deploy((server.connection.get('snapshot') or {}).get('device_id')))
    @server.app.post('/api/store/open-link')
    def open_link():
        body=request.get_json(silent=True) or {}
        if not isinstance(body,dict) or body.get('kind') not in ('repository','issues','pulls'):raise StoreError('Choose a GitHub link from a package card.')
        with store.lock:url=store.github_links.get(str(body.get('id','')),{}).get(body['kind'])
        if not url:raise StoreError('This package has no verified GitHub repository link. Refresh Store and try again.')
        try:opened=webbrowser.open(url)
        except (OSError,webbrowser.Error):opened=False
        if not opened:raise StoreError('Could not open the system browser.')
        return jsonify(ok=True)
    @server.app.get('/api/store/stats')
    def stats():
        ids=request.args.get('ids','').split(',')
        if len(ids)>12 or any(not ID.fullmatch(key) for key in ids):raise StoreError('Choose up to 12 loaded packages.')
        return jsonify(packages=store.stats.request(ids))
    @server.app.get('/api/store/icons/<digest>')
    def icon(digest):
        from flask import Response
        if not HEX.fullmatch(digest):raise StoreError('Invalid icon ID.')
        return Response(store.icon(digest),mimetype='image/png',headers={'X-Content-Type-Options':'nosniff','Cache-Control':'private, max-age=3600'})
    @server.app.post('/api/store/install')
    def install():return jsonify(store.start(request.get_json(silent=True))),202
    @server.app.post('/api/store/cancel')
    def cancel_install():return jsonify(job=store.cancel(request.get_json(silent=True)))
    @server.app.post('/api/store/local/preview')
    def preview_local():return jsonify(store.preview_local(request.get_json(silent=True)))
    @server.app.post('/api/store/local/add')
    def add_local():return jsonify(store.add_local(request.get_json(silent=True)))
    @server.app.post('/api/store/local/install')
    def install_local():return jsonify(store.start_local(request.get_json(silent=True))),202
    @server.app.get('/api/store/job')
    def job():return jsonify(job=store.status())
    @server.app.post('/api/store/remove-plugin')
    def remove():
        body=request.get_json(silent=True) or {}
        if not ID.fullmatch(str(body.get('id',''))):raise StoreError('Invalid plugin ID.')
        return jsonify(store.remove_plugin(body['id']))
