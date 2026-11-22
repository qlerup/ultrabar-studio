"""Package-owned presentation presets; no model names, protocols or executable code."""
import copy
import json
import math
import re

IDENTIFIER = re.compile(r'[a-zA-Z0-9][a-zA-Z0-9_.-]{0,63}')


def identifier(value):
    return isinstance(value, str) and IDENTIFIER.fullmatch(value) is not None


def validate(presentation, panel):
    if not isinstance(presentation, dict) or set(presentation) != {'api', 'source', 'presets'} or type(presentation['api']) is not int or presentation['api'] != 1:
        raise ValueError('presentation: declare API 1, source and presets.')
    source = presentation['source']
    if not isinstance(source, dict) or set(source) != {'scope', 'key'} or source['scope'] not in ('setting', 'connection') or not identifier(source['key']):
        raise ValueError('presentation: source must be a declared choice setting or connection field.')
    fields = panel.get('settings' if source['scope'] == 'setting' else 'connection', {}).get('fields', [])
    field = next((f for f in fields if f['key'] == source['key'] and f['type'] == 'choice'), None)
    if field is None:
        raise ValueError('presentation: source must be a declared choice field, never a secret or address.')
    choices = {option['value'] for option in field['options']}
    presets = presentation['presets']
    if not isinstance(presets, list) or not 1 <= len(presets) <= 32:
        raise ValueError('presentation: declare 1-32 presets.')
    seen = set()
    for preset in presets:
        if not isinstance(preset, dict) or set(preset)-{'value', 'labels', 'artwork', 'splitFlap'} or not isinstance(preset.get('value'), str) or preset['value'] not in choices or preset['value'] in seen:
            raise ValueError('presentation: presets must name distinct declared choices.')
        seen.add(preset['value'])
        if 'splitFlap' in preset:
            face = preset['splitFlap']
            if not isinstance(face, dict) or set(face) != {'plateColor', 'durationMs'}:
                raise ValueError('splitFlap requires plateColor and durationMs.')
            if not isinstance(face['plateColor'], str) or not re.fullmatch(r'#[0-9a-fA-F]{6}', face['plateColor']):
                raise ValueError('Invalid split-flap plate color.')
            if type(face['durationMs']) is not int or not 0 <= face['durationMs'] <= 600:
                raise ValueError('Split-flap duration must be 0-600 milliseconds.')
        labels = preset.get('labels', {})
        if not isinstance(labels, dict) or len(labels) > 32 or any(not identifier(k) or not isinstance(v, str) or not 1 <= len(v) <= 64 or any(ord(c) < 32 for c in v) for k, v in labels.items()):
            raise ValueError('presentation: labels must be bounded plain text.')
        shapes = preset.get('artwork', [])
        if not isinstance(shapes, list) or len(shapes) > 64:
            raise ValueError('presentation: artwork supports at most 64 vector shapes.')
        for shape in shapes:
            if not isinstance(shape, dict) or set(shape) != {'type', 'points', 'fill'} or shape['type'] not in ('rect', 'roundRect', 'oval', 'polygon'):
                raise ValueError('presentation: unsupported artwork primitive.')
            color, points = shape['fill'], shape['points']
            if not isinstance(color, str) or (color != 'accent' and not re.fullmatch(r'#[a-fA-F0-9]{6}', color)):
                raise ValueError('presentation: use a hex color or the widget accent.')
            count = 6 if shape['type'] == 'roundRect' else 4
            if not isinstance(points, list):
                raise ValueError('presentation: coordinates must be a list.')
            valid_count = 6 <= len(points) <= 32 and len(points) % 2 == 0 if shape['type'] == 'polygon' else len(points) == count
            if not valid_count or any(type(n) not in (float, int) or not math.isfinite(n) or not 0 <= n <= 100 for n in points):
                raise ValueError('presentation: shape coordinates must fit a 100 by 100 canvas.')
            if shape['type'] != 'polygon' and (points[0] > points[2] or points[1] > points[3]):
                raise ValueError('presentation: invalid artwork bounds.')
    if len(json.dumps(presentation, allow_nan=False).encode()) > 24576:
        raise ValueError('presentation: presets exceed 24 KiB.')
    return copy.deepcopy(presentation)


def resolve(presentation, settings, connection=None):
    source = presentation['source']
    values = settings if source['scope'] == 'setting' else (connection or {})
    selected = values.get(source['key'])
    preset = next((p for p in presentation['presets'] if p['value'] == selected), {})
    return {key: copy.deepcopy(preset[key]) for key in ('labels', 'artwork', 'splitFlap') if key in preset}


def bindings(specs, records):
    """Resolve installed package ownership rather than trusting draft-supplied presets."""
    result = {}
    for key, spec in specs.items():
        package = next((p for p in records.values() if p.get('id') == spec.get('packageId')), {})
        template = next((w for w in package.get('widgets', []) if w.get('id') == spec.get('widgetKey')), {})
        panel = template.get('studio', {})
        if 'presentation' in panel:
            import studio_contract
            studio_contract.validate(panel, template.get('kind'))
            result[key] = (panel['presentation'], panel.get('connection', {}).get('provider'), panel.get('connection', {}).get('key'))
    return result


def apply(specs, bindings, providers):
    result = {key: {k: v for k, v in spec.items() if k != '_presentation'} for key, spec in specs.items()}
    for key, (presentation, provider, connection_key) in bindings.items():
        spec = result[key]
        connection = providers.get(provider, {}).get(spec.get(connection_key), {})
        spec['_presentation'] = resolve(presentation, spec, connection)
    return result
