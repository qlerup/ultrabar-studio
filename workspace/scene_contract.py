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
    if not isinstance(layout,dict) or set(layout)!={'large','small'}:
        raise ValueError('Declare large and small widget layouts.')
    for size,items in layout.items():
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
