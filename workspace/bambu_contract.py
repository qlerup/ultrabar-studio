"""Supported, data-only Bambu widget options. No contributor code or credentials."""
FIELDS = {'primary', 'secondary', 'expandedSlots', 'showJob', 'showTemperatures',
          'showLayers', 'showRemaining', 'showControls', 'liquidMotion'}
DEFAULTS = dict(primary='progress', secondary='remaining', expandedSlots=3,
                showJob=True, showTemperatures=True, showLayers=True,
                showRemaining=True, showControls=True, liquidMotion=True)


def validate(spec):
    if spec.get('kind') != 'bambu':
        if FIELDS & set(spec):
            raise ValueError('Printer display settings require a Bambu widget.')
        return
    if spec.get('primary', 'progress') not in ('progress', 'state', 'remaining', 'temperature'):
        raise ValueError('Choose progress, state, remaining time or nozzle temperature.')
    if spec.get('secondary', 'remaining') not in ('remaining', 'state', 'job', 'layers', 'temperature', 'none'):
        raise ValueError('Choose a supported secondary printer reading.')
    slots = spec.get('expandedSlots', 3)
    if type(slots) is not int or not 2 <= slots <= 5:
        raise ValueError('Expanded printer size must be 2, 3, 4 or 5 slots.')
    for key in FIELDS - {'primary', 'secondary', 'expandedSlots'}:
        if key in spec and type(spec[key]) is not bool:
            raise ValueError(key + ' must be true or false.')
