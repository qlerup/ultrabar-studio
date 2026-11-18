"""App-owned, declarative Studio panels for trusted widget renderers."""
import copy
import json
import re
from app_settings_contract import validate_schema


MIN_VERSION = (0, 49, 0)
SETTINGS = {
    'clock': {'hourFormat': ('choice', {'12', '24'}), 'showSeconds': ('boolean', None), 'showDate': ('boolean', None)},
    'disk': {'drive': ('string', None)},
    **{kind: {'kind': ('choice', {'cpu', 'memory', 'gpu'})} for kind in ('cpu', 'memory', 'gpu')},
    'bambu': {
        'primary': ('choice', {'progress', 'state', 'remaining', 'temperature'}),
        'secondary': ('choice', {'remaining', 'state', 'job', 'layers', 'temperature', 'none'}),
        'expandedSlots': ('integer', None),
        **{key: ('boolean', None) for key in ('showJob', 'showTemperatures', 'showLayers', 'showRemaining', 'showControls', 'liquidMotion')},
    },
}
CONNECTION_FIELDS = {
    'bambu-lan': {'name': 'string', 'host': 'string', 'serial': 'string', 'code': 'secret', 'controls': 'boolean', 'model': 'choice'},
}
for _settings in SETTINGS.values():
    _settings['preset'] = ('choice', None)


def _text(value, name, limit=100):
    if not isinstance(value, str) or not 1 <= len(value.strip()) <= limit or any(ord(c) < 32 for c in value):
        raise ValueError('studio: invalid '+name+'.')


def validate(descriptor, kind):
    if not isinstance(descriptor, dict) or set(descriptor)-{'api', 'settings', 'help', 'connection', 'sources', 'presentation'} or type(descriptor.get('api')) is not int or descriptor['api'] != 1:
        raise ValueError('studio: use declarative panel API 1; code and custom transports are unsupported.')
    if not {'settings', 'connection'} & set(descriptor):
        raise ValueError('studio: declare settings or a connection panel.')
    if 'help' in descriptor:
        _text(descriptor['help'], 'help', 2000)
    if 'settings' in descriptor:
        schema = validate_schema(descriptor['settings'])
        allowed = SETTINGS.get(kind, {})
        for field in schema['fields']:
            key = field['key']
            if key not in allowed or field['type'] != allowed[key][0]:
                raise ValueError('studio: unsupported setting for '+str(kind)+': '+key+'.')
            choices = allowed[key][1]
            if choices is not None and not {o['value'] for o in field['options']} <= choices:
                raise ValueError('studio: unsupported choices for '+key+'.')
            if key == 'expandedSlots' and not 2 <= field['min'] <= field['max'] <= 5:
                raise ValueError('studio: expandedSlots must stay between 2 and 5.')
            if key == 'drive' and field['default'] != 'all' and not re.fullmatch(r'[A-Z]:\\', field['default']):
                raise ValueError('studio: drive default must be all or a Windows drive root.')
    if 'sources' in descriptor:
        if kind != 'disk' or descriptor['sources'] != {'drive': 'pc.drives'} or not any(f['key'] == 'drive' for f in descriptor.get('settings', {}).get('fields', [])):
            raise ValueError('studio: unsupported setting source.')
    if 'connection' in descriptor:
        connection = descriptor['connection']
        keys = {'provider', 'key', 'label', 'title', 'manageLabel', 'itemLabel', 'setupHelp', 'fields'}
        if not isinstance(connection, dict) or set(connection) != keys:
            raise ValueError('studio: invalid connection panel properties.')
        if not isinstance(connection['provider'], str) or connection['provider'] not in CONNECTION_FIELDS or kind != 'bambu' or connection['provider'] != 'bambu-lan' or connection['key'] != 'printerId':
            raise ValueError('studio: connection provider is not supported by this widget renderer.')
        for key in ('label', 'title', 'manageLabel', 'itemLabel', 'setupHelp'):
            _text(connection[key], key, 2000 if key == 'setupHelp' else 100)
        fields = connection['fields']
        expected = CONNECTION_FIELDS[connection['provider']]
        if not isinstance(fields, list) or len(fields) not in (len(expected), len(expected)-1):
            raise ValueError('studio: declare every provider connection field exactly once.')
        seen = set()
        for field in fields:
            if not isinstance(field, dict) or set(field)-{'key', 'label', 'type', 'maxLength', 'required', 'help', 'options'}:
                raise ValueError('studio: invalid connection field.')
            key = field.get('key')
            if not isinstance(key, str) or key not in expected or key in seen or field.get('type') != expected[key]:
                raise ValueError('studio: connection fields must match the trusted provider contract.')
            seen.add(key)
            _text(field.get('label'), 'field label')
            if 'help' in field:
                _text(field['help'], 'field help', 500)
            if 'required' in field and type(field['required']) is not bool:
                raise ValueError('studio: required must be a boolean.')
            if field['type'] == 'choice':
                options = field.get('options')
                if not isinstance(options, list) or not 1 <= len(options) <= 32:
                    raise ValueError('studio: invalid printer model choices.')
                choices = set()
                for option in options:
                    from widget_presentation import identifier
                    if not isinstance(option, dict) or set(option) != {'value', 'label'} or not identifier(option['value']) or option['value'] in choices:
                        raise ValueError('studio: unsupported printer model.')
                    choices.add(option['value'])
                    _text(option['label'], 'model label')
                if 'maxLength' in field:
                    raise ValueError('studio: choice fields cannot have maxLength.')
            elif 'options' in field:
                raise ValueError('studio: options require a choice field.')
            elif field['type'] == 'boolean':
                if 'maxLength' in field:
                    raise ValueError('studio: boolean fields cannot have maxLength.')
            elif type(field.get('maxLength')) is not int or not 1 <= field['maxLength'] <= 2048:
                raise ValueError('studio: specify a bounded connection field length.')
        if seen != set(expected) and seen != set(expected)-{'model'}:
            raise ValueError('studio: declare every provider connection field exactly once.')
    if 'presentation' in descriptor:
        from widget_presentation import validate as validate_presentation
        validate_presentation(descriptor['presentation'], descriptor)
    if len(json.dumps(descriptor, allow_nan=False).encode()) > 32768:
        raise ValueError('studio: panel descriptor exceeds 32 KiB.')
    return copy.deepcopy(descriptor)


def legacy_bambu():
    """Compatibility only: new app releases carry this data in their package."""
    choices = lambda key, label, default, options: dict(key=key, label=label, type='choice', default=default, options=[dict(value=v, label=t) for v, t in options])
    fields = [
        choices('primary', 'Main reading', 'progress', [('progress', 'Print progress'), ('state', 'Printer status'), ('remaining', 'Time remaining'), ('temperature', 'Nozzle temperature')]),
        choices('secondary', 'Secondary reading', 'remaining', [('remaining', 'Time remaining'), ('state', 'Printer status'), ('job', 'Job name'), ('layers', 'Layer count'), ('temperature', 'Nozzle temperature'), ('none', 'None')]),
        dict(key='expandedSlots', label='Size when unfolded', type='integer', default=3, min=2, max=5, step=1),
    ]
    fields += [dict(key=k, label=label, type='boolean', default=True) for k, label in [
        ('showJob', 'Job name'), ('showTemperatures', 'Temperatures'), ('showLayers', 'Layer count'),
        ('showRemaining', 'Time remaining'), ('showControls', 'Printer controls'), ('liquidMotion', 'Liquid unfold animation')]]
    connection = dict(provider='bambu-lan', key='printerId', label='Printer', title='Bambu printers', manageLabel='Manage printers', itemLabel='printer',
        setupHelp='Find the IP, serial and LAN access code in the printer network settings. The PC and printer need LAN access. Some firmware requires Developer Mode for controls.',
        fields=[dict(key=k, label=label, type=kind, **({'maxLength':limit} if limit else {}), required=k not in ('controls',)) for k, label, kind, limit in [
            ('name', 'Printer name', 'string', 48), ('host', 'Printer IP address', 'string', 48), ('serial', 'Printer serial number', 'string', 32),
            ('code', '8-character LAN access code', 'secret', 8), ('controls', 'Enable pause, resume, stop and light', 'boolean', None)]])
    return dict(api=1, settings=dict(api=1, fields=fields), connection=connection,
        help='Display preferences apply to this widget. Printer connections and access codes stay on this PC. Enable controls in Manage printers. Unfolding moves neighboring cards, then restores them on close.')


def legacy_descriptor(widget):
    kind = widget.get('kind')
    if kind == 'bambu':
        return legacy_bambu()
    if kind == 'clock':
        fields = [dict(key='hourFormat', label='Time format', type='choice', default='24', options=[dict(value='24', label='24 hours'), dict(value='12', label='12 hours')])]
        fields += [dict(key=k, label=label, type='boolean', default=True) for k, label in [('showSeconds', 'Show seconds'), ('showDate', 'Show date')]]
        return dict(api=1, settings=dict(api=1, fields=fields))
    if kind == 'disk':
        return dict(api=1, settings=dict(api=1, fields=[dict(key='drive', label='Drive', type='string', default='all', maxLength=128)]), sources={'drive': 'pc.drives'},
            help='Shows two drives at a time. With more than two drives, the card switches to the next pair every 6 seconds.')
    if kind in ('cpu', 'memory', 'gpu') and widget.get('kindOptions'):
        labels = dict(cpu='CPU usage', memory='RAM usage', gpu='GPU usage')
        return dict(api=1, settings=dict(api=1, fields=[dict(key='kind', label='Show', type='choice', default=kind, options=[dict(value=k, label=labels[k]) for k in widget['kindOptions']])]))
    return None


def legacy_descriptors():
    return {kind: legacy_descriptor(dict(kind=kind, **({'kindOptions': ['cpu', 'memory', 'gpu']} if kind in ('cpu', 'memory', 'gpu') else {}))) for kind in ('clock', 'disk', 'bambu', 'cpu', 'memory', 'gpu')}


def resolve(widget):
    descriptor = widget.get('studio')
    if descriptor is None:
        descriptor = legacy_descriptor(widget)
    return validate(descriptor, widget.get('kind')) if descriptor is not None else None
