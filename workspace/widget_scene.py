"""Compile package layouts to pixels and clock glyphs for preview and Core."""
import base64
import calendar
import io
import math
import os
import time
from functools import lru_cache
from PIL import Image, ImageDraw, ImageFont

def encoded(image):
    buf=io.BytesIO()
    image.save(buf,'PNG',optimize=False)
    return base64.b64encode(buf.getvalue()).decode('ascii')

@lru_cache(maxsize=96)
def font(size,bold):
    for name in (('segoeuib.ttf','DejaVuSans-Bold.ttf') if bold else ('segoeui.ttf','DejaVuSans.ttf')):
        try:return ImageFont.truetype(name,size)
        except OSError:pass
    return ImageFont.load_default(size=size)

def color(value,settings,fallback):
    if value.startswith('$'):value=settings.get(value[1:],fallback)
    if isinstance(value,str) and len(value)==7 and value.startswith('#') and all(c in '0123456789abcdefABCDEF' for c in value[1:]):return value
    return fallback

@lru_cache(maxsize=64)
def atlas(chars,size,bold,tint):
    face=font(size,bold)
    ascent,descent=face.getmetrics()
    height=ascent+descent
    widths=[max(1,math.ceil(face.getlength(c))+2) for c in chars]
    image=Image.new('RGBA',(sum(widths),height+2))
    draw=ImageDraw.Draw(image)
    x=0
    spans={}
    for char,width in zip(chars,widths):
        draw.text((x+1,1+ascent),char,font=face,fill=tint,anchor='ls')
        spans[char]=[x,width]
        x+=width
    return dict(png=encoded(image),height=image.height,spans=spans)

def percent(value):
    return str(round(value))+'%' if isinstance(value,(float,int)) and math.isfinite(value) else '—'

def readings(spec,metrics,printer,title,now,small):
    kind=spec.get('kind')
    out=dict(title=title)
    if kind=='bambu':
        p=printer
        live=bool(p.get('fresh'))
        status={'RUNNING':'Printing','PAUSE':'Paused','IDLE':'Ready','FINISH':'Complete','FAILED':'Stopped','PREPARE':'Preparing'}.get(p.get('gcode_state'),'Connected') if live else p.get('connection','Choose a printer')
        minutes=p.get('mc_remaining_time')
        values=dict(progress=percent(p.get('mc_percent')),state=status,job=p.get('subtask_name') or 'No active job',
                    remaining=f'{minutes//60}h {minutes%60}m' if isinstance(minutes,int) and minutes>=0 else '—',
                    temperature=str(round(p['nozzle_temper']))+'°C' if isinstance(p.get('nozzle_temper'),(float,int)) else '—',
                    layers=str(p.get('layer_num','—'))+' / '+str(p.get('total_layer_num','—')),none='')
        out.update(values)
        out.update(title=p.get('name') or title,status=status,live='Live' if live else '',progress=p.get('mc_percent',0) if live else 0,
                   primary=values.get(spec.get('primary','progress'),'—') if live else '—',secondary=values.get(spec.get('secondary','remaining'),'') if live else '')
    elif kind=='disk':
        selected=spec.get('drive','all')
        disks=[d for d in metrics.get('disks',[]) if isinstance(d,dict) and (selected=='all' or d.get('name')==selected)]
        if spec.get('drives'):disks=[d for d in disks if d.get('name') in spec['drives']]
        pair=not small and len(disks)>1
        stride=2 if pair else 1
        page=int(now//6)%max(1,math.ceil(len(disks)/stride))
        batch=disks[stride*page:stride*(page+1)]
        def capacity(d):return f"{d['used_gb']:.1f} / {d['total_gb']:.1f} GB" if all(isinstance(d.get(k),(int,float)) for k in ('used_gb','total_gb')) else ''
        d=batch[0] if batch else {}
        used=d.get('percent')
        out.update(source=d.get('name','Drive unavailable'),usage=used,value=percent(used),detail=capacity(d),foot='',paired=pair)
        if capacity(d):out['foot']=f"{d['total_gb']-d['used_gb']:.1f} GB free"
        for key,disk in zip(('one','two'),batch):
            out[key]=disk.get('name','')+'    '+percent(disk.get('percent'))
            out[key+'Detail']=capacity(disk);out[key+'Usage']=disk.get('percent')
    elif kind in ('cpu','gpu','memory'):
        gpu=metrics.get('gpu') or {}
        used=gpu.get('usage') if kind=='gpu' else metrics.get(kind)
        out.update(source={'cpu':'CPU','gpu':'GPU','memory':'RAM'}[kind],value=percent(used),usage=used,detail='PC usage',foot='')
        if kind=='memory' and metrics.get('memory_total_gb') is not None:out['detail']=f"{metrics.get('memory_used_gb',0):.1f} / {metrics['memory_total_gb']:.1f} GB"
        if kind=='gpu':out['detail']=gpu.get('name','Sensor unavailable')
    return out

def fallback_art(spec):
    shapes=spec.get('_presentation',{}).get('artwork',[])
    if not shapes:return None
    image=Image.new('RGBA',(100,100));draw=ImageDraw.Draw(image)
    for shape in shapes:
        coords=shape['points'];fill=spec.get('accent','#86e4c3') if shape['fill']=='accent' else shape['fill']
        if shape['type']=='rect':draw.rectangle(coords,fill=fill)
        elif shape['type']=='oval':draw.ellipse(coords,fill=fill)
        elif shape['type']=='roundRect':draw.rounded_rectangle(coords[:4],radius=coords[4],fill=fill)
        elif shape['type']=='polygon':draw.polygon(coords,fill=fill)
    return encoded(image)


def make(layout,size,spec,metrics,printer,title,now,art=None):
    if size=='expanded' or isinstance(layout[size],dict):
        from package_panel import paint
        settings={**spec,**spec.get('packageSettings',{})}
        values=readings(spec,metrics,printer,title,now,False)
        public_settings={k:v for k,v in settings.items() if not k.startswith('_')}
        slots=spec.get('expandedSlots',3)
        width=280*max(2,min(5,slots if type(slots) is int else 3))-20
        live=printer.get('fresh',False)
        public_printer=printer if live else {k:printer[k] for k in ('name','model','connection') if k in printer}
        ctx=dict(settings=public_settings,values=values,printer=public_printer,metrics=metrics,
                 labels=spec.get('_presentation',{}).get('labels',{}),narrow=width<700)
        if size=='expanded':
            return paint(layout[size],ctx,width,230,color('$background',settings,'#192325'))
        w,h=(130,120) if size=='small' else (260,240)
        ctx['narrow']=size=='small'
        return paint(layout[size]['elements'],ctx,w,h,color('$background',settings,'#192325'))
    width,height=(130,120) if size=='small' else (260,240)
    settings={**spec,**spec.get('packageSettings',{})}
    values=readings(spec,metrics,printer,title,now,size=='small')
    background=color('$background',settings,'#192325')
    image=Image.new('RGB',(width,height),background);draw=ImageDraw.Draw(image)
    layers=[]
    for item in layout[size]:
        when=item.get('when')
        if when and bool(values.get(when.lstrip('!'),settings.get(when.lstrip('!'))))==when.startswith('!'):continue
        x,y,w,h=item['box'];op=item['op'];box=(x,y,x+w-1,y+h-1)
        ink=color(item.get('color','$textColor'),settings,'#eef6f2')
        radius=item.get('radius',0)
        if op=='text':
            label=item['text']
            label=str(values.get(label[1:],settings.get(label[1:],''))) if label.startswith('@') else label
            point=item.get('font',14);face=font(point,item.get('bold',False))
            while point>7 and face.getlength(label)>w:
                point-=1;face=font(point,item.get('bold',False))
            tile=Image.new('RGBA',(w,h));ImageDraw.Draw(tile).text((0,h/2),label,font=face,fill=ink,anchor='lm')
            image.paste(tile,(x,y),tile)
        elif op=='rect':draw.rounded_rectangle(box,radius=radius,fill=ink)
        elif op=='bar':
            draw.rounded_rectangle(box,radius=radius,fill=color(item.get('track','#344143'),settings,'#344143'))
            amount=max(0,min(100,values.get(item['value']) or 0));end=round(w*amount/100)
            if end:draw.rounded_rectangle((x,y,x+end-1,y+h-1),radius=radius,fill=ink)
        elif op=='image':
            art=art or fallback_art(spec)
            if not art:continue
            with Image.open(io.BytesIO(base64.b64decode(art))) as source:
                pic=source.convert('RGBA');pic.thumbnail((w,h),Image.Resampling.LANCZOS)
                image.paste(pic,(x+(w-pic.width)//2,y+(h-pic.height)//2),pic)
        elif op=='time':
            value=item['value']
            twelve=spec.get('hourFormat')=='12'
            if value=='period' and not twelve:continue
            months=list(calendar.month_abbr)[1:];days=list(calendar.day_abbr)
            chars='0123456789' if value in ('hours','minutes','seconds') else ''.join(sorted(set('0123456789 ,AMPamp'+''.join(months+days))))
            layer=dict(value=value,box=item['box'],twelve=twelve,glyphs=atlas(chars,item.get('font',16),item.get('bold',False),ink))
            if value in ('date','shortDate'):layer.update(months=months,days=days)
            if 'plate' in item:
                plate=color(item['plate'],settings,'#353839')
                draw.rounded_rectangle(box,radius=radius,fill=plate)
                layer.update(plate=plate,duration=item.get('duration',0),seam=background)
            layers.append(layer)
    return dict(width=width,height=height,png=encoded(image),layers=layers)

def installed(spec,records):
    package=records.get(str(spec.get('packageId',''))+':pc',{})
    widget=next((w for w in package.get('widgets',[]) if w.get('id')==spec.get('widgetKey')), {})
    return widget.get('studio',{}).get('layout')

def frames(spec,layout,metrics,printers,title,now):
    from bambu_artwork import thumbnail
    printer=printers.get(spec.get('printerId'),{})
    art=thumbnail(printer.get('model')) if printer.get('model') else None
    return {size:make(layout,size,spec,metrics,printer,title,now,art) for size in layout}

def compact_frames(widgets):
    """Share identical PNGs across sizes, instances and profiles in one atomic update."""
    import hashlib
    images={}
    def intern(obj):
        data=obj['png']
        key=hashlib.sha256(data.encode('ascii')).hexdigest()
        images[key]=data
        obj['png']=key
    for spec in widgets.values():
        for frame in spec.get('_scene', {}).values():
            intern(frame)
            for layer in frame['layers']:
                layer['glyphs']=dict(layer['glyphs'])
                intern(layer['glyphs'])
    return images
