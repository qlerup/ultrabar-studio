"""Read a user-selected package directory as data; never run build/install scripts."""
import copy,hashlib,json,re
from pathlib import Path


def read_folder(server,folder):
    from store import StoreError,MAX_SIZE,ASSET_PREFIX,validate_entry,validate_icon_bytes,widget_package,plugin_templates,inspect_apk,require_widget_version
    root=Path(folder).resolve()
    def read(name,limit,required=True):
        path=root/name
        if not path.exists() and not required:return None
        if path.is_symlink() or not path.is_file() or path.resolve().parent!=root or path.stat().st_size>limit:
            raise StoreError('Missing, linked or oversized package file: '+name)
        with path.open('rb') as stream:raw=stream.read(limit+1)
        if len(raw)>limit:raise StoreError('Package file is too large: '+name)
        return raw
    raw_manifest=read('manifest.json',65536,False)
    manifest=json.loads(raw_manifest) if raw_manifest else None
    if manifest is not None and not isinstance(manifest,dict):raise StoreError('manifest.json must be an object.')
    types={'corebar-widget':'widget.json','studio-plugin':'plugin.json','corebar-app':'app.apk'}
    present=[kind for kind,name in types.items() if (root/name).is_file()]
    kind=manifest.get('type') if manifest else present[0] if len(present)==1 else None
    if kind not in types:raise StoreError('Choose a folder with widget.json, plugin.json or app.apk and a matching manifest.json.')
    payload=read(types[kind],MAX_SIZE if kind=='corebar-app' else 65536)
    if kind=='corebar-widget':widget_package(payload)
    if kind=='studio-plugin':plugin_templates(payload)
    if kind=='corebar-app' and not manifest:raise StoreError('APK testing requires manifest.json with Android identity, permissions and compatibility.')
    original=copy.deepcopy(manifest or {})
    slug=re.sub('[^a-z0-9]+','-',root.name.lower()).strip('-')[:40] or 'package'
    folder_key=hashlib.sha256(str(root).casefold().encode()).hexdigest()[:12]
    p=manifest or dict(schemaVersion=1,id='test.'+slug+'-'+folder_key,name=root.name[:100],description='Local development package.',version='1.0.0',type=kind,license='Local development; see package license.',permissions=[],compatibility=dict(minStudioVersion='0.24.0',hostApi=1,models=['CB01'],abis=['armeabi-v7a'],lineosVersions=['1.0.8','1.0.9']))
    if kind=='corebar-widget':
        widgets=widget_package(payload)
        if manifest is None and any(w['kind']=='bambu' for w in widgets):p['compatibility']['minStudioVersion']='0.46.0'
        require_widget_version(widgets,p)
    if not isinstance(p.get('id'),str) or not re.fullmatch(r'[a-z][a-z0-9]*(?:\.[a-z][a-z0-9-]*)+',p['id']):raise StoreError('Invalid local package ID.')
    original_id=p['id'];p['id']='local.'+original_id
    p.pop('publisher',None);p['source']='local:folder'
    raw_icon=read('icon.png',262144)
    for name,raw in (('artifact',payload),('icon',raw_icon)):
        digest=hashlib.sha256(raw).hexdigest()
        if name in original and not isinstance(original[name],dict):raise StoreError('Invalid local '+name+' metadata.')
        if name in original and (original[name].get('sha256')!=digest or original[name].get('size')!=len(raw)):
            raise StoreError('Local '+name+' differs from its declared checksum or size. Update manifest.json before testing.')
        p[name]=dict(url=ASSET_PREFIX+'local/'+digest+('.png' if name=='icon' else '.apk' if kind=='corebar-app' else '.json'),size=len(raw),sha256=digest)
    p=validate_entry(p);validate_icon_bytes(raw_icon,p['icon'])
    if kind=='corebar-app':
        embedded=inspect_apk(server,root/types[kind],p)
        if isinstance(embedded,dict):p['bundledWidgets']=embedded
    p['origin']='local';p['original_id']=original_id
    return p,payload,raw_icon
