"""One reviewed APK may supply declarative templates for trusted native renderers."""
import json,zipfile

def validate(manifest,parse):
    if 'bundledWidgets' not in manifest:return []
    if manifest.get('type')!='corebar-app':raise ValueError('bundledWidgets requires a corebar-app package.')
    if tuple(map(int,manifest.get('compatibility',{}).get('minStudioVersion','0.0.0').split('.')))<(0,46,0):raise ValueError('Bundled native widgets require Studio 0.46.0+.')
    descriptor=manifest['bundledWidgets']
    if not isinstance(descriptor,dict):raise ValueError('bundledWidgets must be a widget.json object.')
    templates=parse(json.dumps(descriptor).encode())
    if any('studio' in w for w in templates) and tuple(map(int,manifest['compatibility']['minStudioVersion'].split('.')))<(0,49,0):
        raise ValueError('App-owned Studio panels require Studio 0.49.0 or newer.')
    if any(w['kind']=='bambu' for w in templates) and manifest.get('android',{}).get('packageId')!='dk.ultrabar.bambu':
        raise ValueError('The Bambu renderer requires its fixed dk.ultrabar.bambu companion.')
    return templates

def inspect_apk(path,manifest):
    with zipfile.ZipFile(path) as archive:
        matches=[i for i in archive.infolist() if i.filename=='assets/ultrabar-widgets.json']
        if not matches and 'bundledWidgets' not in manifest:return None
        if len(matches)!=1 or matches[0].file_size>65536:raise ValueError('APK requires one bounded assets/widget.json descriptor.')
        descriptor=json.loads(archive.read(matches[0]))
        if 'bundledWidgets' in manifest and descriptor!=manifest['bundledWidgets']:raise ValueError('APK widget descriptor differs from its recorded bundle.')
        return descriptor
