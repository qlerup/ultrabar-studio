"""Studio settings API 1: declarative fields only; no code, paths or commands."""
import copy
import json
import math
import re
from urllib.parse import urlsplit

KEY=re.compile(r'[a-zA-Z][a-zA-Z0-9_]{0,63}')

def validate_schema(schema):
    def fail(message):raise ValueError('settings: '+message+' Fix: follow docs/APP-SETTINGS.md (settings API 1).')
    if not isinstance(schema,dict) or set(schema)!={'api','fields'} or type(schema['api']) is not int or schema['api']!=1:fail('Use integer api 1 and a fields array; custom code/transport is unsupported.')
    if not isinstance(schema['fields'],list) or not 1<=len(schema['fields'])<=32:fail('Declare 1-32 fields.')
    seen=set()
    for field in schema['fields']:
        if not isinstance(field,dict) or set(field)-{'key','label','help','type','default','min','max','step','maxLength','options'}:fail('Unknown field properties.')
        key=field.get('key')
        if not isinstance(key,str) or not KEY.fullmatch(key) or key in seen:fail('Field keys must be unique identifiers.')
        seen.add(key)
        for name,limit in (('label',100),('help',500)):
            if name=='help' and name not in field:continue
            if not isinstance(field.get(name),str) or not 1<=len(field[name].strip())<=limit:fail(key+': invalid '+name+'.')
        kind=field.get('type')
        if kind not in ('boolean','integer','number','string','url','choice'):fail(key+': unsupported type.')
        specific={'boolean':set(),'integer':{'min','max','step'},'number':{'min','max','step'},'string':{'maxLength'},'url':{'maxLength'},'choice':{'options'}}[kind]
        if (set(field)&{'min','max','step','maxLength','options'})-specific:fail(key+': properties do not match the field type.')
        if kind in ('integer','number'):
            for name in ('min','max','step'):
                value=field.get(name)
                if type(value) not in ((int,) if kind=='integer' else (int,float)) or abs(value)>1e12 or not math.isfinite(value):fail(key+': specify finite min, max and step.')
            if field['min']>field['max'] or field['step']<=0:fail(key+': invalid range or step.')
        if kind in ('string','url') and (type(field.get('maxLength')) is not int or not 1<=field['maxLength']<=2048):fail(key+': specify maxLength from 1 to 2048.')
        if kind=='choice':
            options=field.get('options')
            if not isinstance(options,list) or not 1<=len(options)<=32:fail(key+': specify 1-32 choices.')
            values=set()
            for option in options:
                if not isinstance(option,dict) or set(option)!={'value','label'} or any(not isinstance(option[n],str) or not 1<=len(option[n])<=100 for n in ('value','label')) or option['value'] in values:fail(key+': invalid or duplicate choice.')
                values.add(option['value'])
        if 'default' not in field:fail(key+': missing default.')
        try:validate_value(field,field['default'])
        except ValueError as exc:fail(str(exc))
    if len(json.dumps(schema,allow_nan=False).encode())>32768:fail('Schema exceeds 32 KiB.')
    return copy.deepcopy(schema)

def validate_value(field,value):
    kind=field['type'];valid=False
    if kind=='boolean':valid=type(value) is bool
    elif kind in ('integer','number'):
        valid=type(value) in ((int,) if kind=='integer' else (int,float)) and field['min']<=value<=field['max'] and math.isfinite(value)
        if valid:
            count=(value-field['min'])/field['step'];valid=abs(count-round(count))<=1e-7
    elif kind in ('string','url'):
        valid=isinstance(value,str) and len(value)<=field['maxLength'] and not any(ord(c)<32 for c in value)
        if valid and kind=='url':
            try:
                parsed=urlsplit(value);valid=parsed.scheme in ('http','https') and bool(parsed.hostname) and parsed.username is None and parsed.password is None
                parsed.port  # Reject invalid/non-numeric/out-of-range ports.
            except ValueError:valid=False
    elif kind=='choice':valid=isinstance(value,str) and value in [o['value'] for o in field['options']]
    if not valid:raise ValueError(field['key']+': invalid '+kind+' value, range or step.')
    return value

def validate_values(schema,values,fill_defaults=True):
    schema=validate_schema(schema)
    if not isinstance(values,dict) or set(values)-{f['key'] for f in schema['fields']}:raise ValueError('Unknown app settings. Reload the installed package settings before editing.')
    result={}
    for field in schema['fields']:
        if field['key'] not in values and not fill_defaults:raise ValueError('Missing app setting: '+field['key'])
        result[field['key']]=validate_value(field,values.get(field['key'],field['default']))
    return result

def inspect_apk(path,schema):
    import zipfile
    validate_schema(schema)
    try:
        with zipfile.ZipFile(path) as archive:
            if archive.namelist().count('assets/studio-settings.json')!=1:raise ValueError('Missing or duplicate embedded settings.')
            info=archive.getinfo('assets/studio-settings.json')
            if info.file_size>32768:raise ValueError('Embedded settings exceed 32 KiB.')
            embedded=json.loads(archive.read(info))
        validate_schema(embedded)
        if embedded!=schema:raise ValueError('Embedded settings differ from manifest.json.')
    except (OSError,KeyError,zipfile.BadZipFile,ValueError) as exc:
        raise ValueError('app.apk: missing or mismatched assets/studio-settings.json. Fix: package the exact reviewed settings schema in the APK assets and rebuild.') from exc

def validate_receiver(xml,package_id):
    nodes=[];current=None;level=0
    for line in xml.splitlines():
        element=re.match(r'(\s*)E: ([\w-]+)',line)
        if element:
            indent=len(element[1])
            if current is not None and indent<=level:current=None
            if element[2]=='receiver':current={};nodes.append(current);level=indent
        match=re.match(r'\s*A: android:([\w-]+)(?:\(0x[0-9a-f]+\))?=(.*)',line)
        if match and current is not None:current[match[1]]=match[2]
    for node in nodes:
        name=re.match(r'"([^"]+)"',node.get('name',''))
        if name and name[1] in ('.StudioSettingsReceiver',package_id+'.StudioSettingsReceiver'):
            if re.match(r'\(type 0x12\)0xffffffff\b',node.get('exported','')) and node.get('permission','').startswith('"android.permission.DUMP"') and not re.match(r'\(type 0x12\)0x0\b',node.get('enabled','')):return
    raise ValueError('AndroidManifest.xml: settings API 1 requires an enabled .StudioSettingsReceiver, exported=true and permission=android.permission.DUMP. Fix: copy the receiver declaration in APP-SETTINGS.md; arbitrary components/transports are not supported.')
