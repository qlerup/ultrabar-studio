"""Data-only widget layouts shared by the Studio preview and Core card."""
import copy
import math
import re

COLORS = re.compile(r'#[a-fA-F0-9]{6}|\$[a-zA-Z][a-zA-Z0-9]{0,63}')
OPS = {'text','bar','image','rect','time'}
COMMON = {'op','box','when'}
PROPERTIES = {'text':{'text','color','font','bold'}, 'bar':{'value','color','track','radius'},
              'image':{'value'}, 'rect':{'color','radius'}, 'time':{'value','color','font','bold','plate','radius','duration'}}
CLOCK = {'hours','minutes','seconds','period','date','shortDate'}
def validate(layout):
    if not isinstance(layout,dict) or not {'large','small'} <= set(layout) <= {'large','small','expanded'}:
        raise ValueError('Declare large and small widget layouts.')
    for size,items in layout.items():
        if size == 'expanded':
            validate_panel(items)
            continue
        if isinstance(items,dict) and set(items)=={'elements'}:
            validate_panel(items['elements'])
            continue
        if not isinstance(items,list) or not 1<=len(items)<=32:
            raise ValueError('Declare 1-32 elements per widget layout.')
        for item in items:
            if not isinstance(item,dict) or item.get('op') not in OPS or set(item)-COMMON-PROPERTIES[item['op']]:
                raise ValueError('Unsupported widget layout element.')
            box=item.get('box')
            if not isinstance(box,list) or len(box)!=4 or any(type(n) is not int for n in box):
                raise ValueError('A widget element needs integer x, y, width and height.')
            width,height=(260,240) if size=='large' else (130,120)
            x,y,w,h=box
            if min(x,y)<0 or min(w,h)<1 or x+w>width or y+h>height:raise ValueError('Element outside widget bounds.')
            for key in ('color','track','plate'):
                if key in item and (not isinstance(item[key],str) or not COLORS.fullmatch(item[key])):raise ValueError('Invalid layout color.')
            for key,maximum in [('font',96),('radius',120),('duration',600)]:
                if key in item and (type(item[key]) is not int or not (1 if key=='font' else 0)<=item[key]<=maximum):raise ValueError('Invalid layout dimension.')
            if 'bold' in item and not isinstance(item['bold'],bool):raise ValueError('Invalid typography.')
            if 'when' in item and (not isinstance(item['when'],str) or not re.fullmatch(r'!?[A-Za-z][A-Za-z0-9]{0,63}',item['when'])):raise ValueError('Invalid layout condition.')
            if item['op']=='time' and item.get('value') not in CLOCK:raise ValueError('Invalid clock source.')
            if item['op'] in ('text','bar','image'):
                field='text' if item['op']=='text' else 'value'
                if not isinstance(item.get(field),str) or len(item[field])>160:raise ValueError('Invalid display source.')
    return layout

# Expanded layouts use coordinates relative to their parent (0..1000).
# Leaves can read only the data passed to the renderer. No expressions execute.
PATH = re.compile(r'[a-zA-Z][a-zA-Z0-9_.]{0,95}')
TYPES = {'text','rect','bar','grid','group','swatch'}

def validate_panel(items):
    budget = [128]
    def walk(nodes, depth):
        if depth > 4 or not isinstance(nodes,list) or not 1 <= len(nodes) <= 64:
            raise ValueError('Invalid panel children.')
        for node in nodes:
            budget[0] -= 1
            if budget[0]<0 or not isinstance(node,dict) or not isinstance(node.get('op'),str) or node['op'] not in TYPES:
                raise ValueError('Invalid panel element.')
            op = node['op']
            allowed = {'op','box','when','equals','unless','oneOf','color','radius'}
            allowed.update({'text':{'text','size','bold','align','lookup','fallback','suffix'},
                            'rect':set(),'swatch':{'size'},'bar':{'source','track'},'group':{'children'},
                            'grid':{'source','children','columns','rows','slots','key','gap'}}[op])
            if set(node)-allowed:
                raise ValueError('Unknown panel element property.')
            box=node.get('box')
            if not isinstance(box,list) or len(box)!=4 or any(type(v) is not int for v in box):
                raise ValueError('Expected a panel rectangle.')
            x,y,w,h=box
            if min(x,y)<0 or min(w,h)<1 or x+w>1000 or y+h>1000:
                raise ValueError('Panel rectangle is outside its parent.')
            for k in ('source','when','unless','lookup','key'):
                if k in node and (not isinstance(node[k],str) or not PATH.fullmatch(node[k])):
                    raise ValueError('Invalid panel data path.')
            for k in ('color','track'):
                if k in node and (not isinstance(node[k],str) or not (COLORS.fullmatch(node[k]) or node[k].startswith('@') and PATH.fullmatch(node[k][1:]))):
                    raise ValueError('Invalid panel color.')
            for k,low,high in [('columns',1,16),('rows',1,16),('gap',0,24),('slots',1,16),('radius',0,80),('size',6,96)]:
                if k in node and (type(node[k]) is not int or not low<=node[k]<=high):
                    raise ValueError('Invalid panel dimension.')
            for k in ('text','equals','fallback','suffix'):
                if k in node and (not isinstance(node[k],str) or len(node[k])>180):
                    raise ValueError('Expected bounded panel text.')
            if 'oneOf' in node:
                choices=node['oneOf']
                if ('unless' not in node or not isinstance(choices,list) or not 1<=len(choices)<=32
                        or any(not isinstance(c,str) or len(c)>64 for c in choices)):
                    raise ValueError('Invalid panel exclusions.')
            if 'equals' in node and 'when' not in node or 'bold' in node and type(node['bold']) is not bool:
                raise ValueError('Invalid panel condition or font.')
            if node.get('align','left') not in ('left','center','right'):
                raise ValueError('Invalid text alignment.')
            if op=='text' and 'text' not in node or op in ('bar','grid') and 'source' not in node:
                raise ValueError('Missing panel content or data source.')
            if op in ('group','grid'):
                if op=='grid' and depth>0 and 'grid' in ancestors:
                    raise ValueError('Nested repeaters are unsupported.')
                ancestors.append(op)
                walk(node.get('children'),depth+1)
                ancestors.pop()
    ancestors=[]
    walk(items,0)
