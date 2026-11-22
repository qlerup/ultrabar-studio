"""Rasterize a package's expanded layout for both the browser and Core."""
import math
import re
from functools import lru_cache
from PIL import Image, ImageDraw
from widget_scene import encoded, font

TOKEN = re.compile(r'\{([a-zA-Z][a-zA-Z0-9_.]{0,95})\}')

def value(data, path):
    for name in path.split('.'):
        if not isinstance(data,dict):
            return None
        data=data.get(name)
    return data

def template(pattern, data):
    def part(match):
        val=value(data,match[1])
        if isinstance(val,float) and val.is_integer():
            val=int(val)
        return str(val)[:120] if isinstance(val,(str,float,int)) else '\u2014'
    return TOKEN.sub(part,pattern)

@lru_cache(maxsize=64)
def rounded_mask(width, height, radius):
    scale = 4
    mask = Image.new('L', (width * scale, height * scale))
    ImageDraw.Draw(mask).rounded_rectangle(
        (0, 0, mask.width - 1, mask.height - 1), radius=radius * scale, fill=255
    )
    return mask.resize((width, height), Image.Resampling.BOX)


def paint(nodes, data, width, height, background):
    image=Image.new('RGB',(width,height),background)
    draw=ImageDraw.Draw(image)
    def tint(name,ctx,default):
        if name.startswith('@'):
            name=value(ctx,name[1:])
        elif name.startswith('$'):
            name=ctx['settings'].get(name[1:])
        return name if isinstance(name,str) and re.fullmatch('#[0-9a-fA-F]{6}',name) else default
    def render(nodes,ctx,left,top,width,height):
        for n in nodes:
            if 'when' in n:
                val=value(ctx,n['when'])
                if not (val==n['equals'] if 'equals' in n else bool(val)):
                    continue
            if 'unless' in n:
                excluded=value(ctx,n['unless'])
                skip = excluded in n['oneOf'] if 'oneOf' in n else bool(excluded)
                if skip:
                    continue
            a,b,c,d=n['box']
            x,y=left+round(width*a/1000),top+round(height*b/1000)
            w=left+round(width*(a+c)/1000)-x
            h=top+round(height*(b+d)/1000)-y
            if min(w,h)<1:continue
            op=n['op']
            ink=tint(n.get('color','$textColor'),ctx,'#eff6fa')
            radius=n.get('radius',0)
            bounds=(x,y,x+w-1,y+h-1)
            if op=='rect':
                if radius:
                    image.paste(ink, (x, y, x + w, y + h), rounded_mask(w, h, radius))
                else:
                    draw.rectangle(bounds, fill=ink)
            elif op=='swatch':
                side=min(n.get('size',16),w,h)
                sx,sy=x+(w-side)//2,y+(h-side)//2
                draw.rounded_rectangle((sx,sy,sx+side-1,sy+side-1),radius=radius,fill=ink,outline='#aab1b5')
            elif op=='text':
                label=template(n['text'],ctx)
                if 'lookup' in n:
                    table=value(ctx,n['lookup'])
                    label=(table.get(label) if isinstance(table,dict) else None) or template(n.get('fallback','\u2014'),ctx)
                label+=template(n.get('suffix',''),ctx)
                size=min(n.get('size',16),h)
                bold=n.get('bold',False)
                face=font(size,bold)
                while size>6 and face.getlength(label)>w:
                    size-=1
                    face=font(size,bold)
                align=n.get('align','left')
                offset={'left':0,'center':w/2,'right':w}[align]
                tile=Image.new('RGBA',(w,h))
                ImageDraw.Draw(tile).text((offset,h/2),label,font=face,fill=ink,anchor={'left':'lm','center':'mm','right':'rm'}[align])
                image.paste(tile,(x,y),tile)
            elif op=='bar':
                draw.rounded_rectangle(bounds,radius=radius,fill=tint(n.get('track','#344143'),ctx,'#344143'))
                amount=value(ctx,n['source'])
                if isinstance(amount,(int,float)) and math.isfinite(amount):
                    length=round(w*max(0,min(100,amount))/100)
                    if length:draw.rounded_rectangle((x,y,x+length-1,y+h-1),radius=radius,fill=ink)
            elif op=='group':
                render(n['children'],ctx,x,y,w,h)
            elif op=='grid':
                items=value(ctx,n['source'])
                items=[item for item in items[:16] if isinstance(item,dict)] if isinstance(items,list) else []
                if 'slots' in n:
                    key=n.get('key','id')
                    by_id={item[key]:item for item in items if type(item.get(key)) is int}
                    items=[by_id.get(i,{key:i}) for i in range(n['slots'])]
                if not items:continue
                cols=n.get('columns') or math.ceil(len(items)/n.get('rows',1))
                rows=math.ceil(len(items)/cols)
                gap=n.get('gap',3)
                for i,item in enumerate(items):
                    col,row=i%cols,i//cols
                    dx,dy=round((w+gap)*col/cols),round((h+gap)*row/rows)
                    cw=round((w+gap)*(col+1)/cols)-dx-gap
                    ch=round((h+gap)*(row+1)/rows)-dy-gap
                    if cw>0 and ch>0:render(n['children'],dict(ctx,item=item),x+dx,y+dy,cw,ch)
    render(nodes,data,0,0,width,height)
    return dict(width=width,height=height,png=encoded(image),layers=[])
