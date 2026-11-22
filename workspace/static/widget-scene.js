'use strict';
window.widgetScene=(()=>{
  const cache=new Map(), active=new WeakMap(), requested=new WeakMap();
  async function image(encoded){
    const bytes=Uint8Array.from(atob(encoded),c=>c.charCodeAt(0));
    return createImageBitmap(new Blob([bytes],{type:'image/png'}));
  }
  async function prepare(frame){
    const bg=await image(frame.png);
    const layers=await Promise.all(frame.layers.map(async layer=>({...layer,atlas:await image(layer.glyphs.png)})));
    return {...frame,bg,layers};
  }
  function value(l,d){
    const hour=d.getHours(), day=d.getDate(), month=d.getMonth();
    switch(l.value){
      case 'date':return l.days[(d.getDay()+6)%7]+', '+day+' '+l.months[month]+' '+d.getFullYear();
      case 'shortDate':return day+' '+l.months[month];
      case 'period':return hour<12?'AM':'PM';
      case 'hours':return String(l.twelve?(hour%12||12):hour).padStart(2,'0');
      case 'seconds':return String(d.getSeconds()).padStart(2,'0');
      default:return String(d.getMinutes()).padStart(2,'0');
    }
  }
  function paint(ctx,l,label){
    const [x,y,w,h]=l.box;
    const spans=Array.from(label,c=>l.glyphs.spans[c]).filter(Boolean);
    const width=spans.reduce((n,s)=>n+s[1],0);
    const scale=Math.min(1,w*(l.plate?0.9:1)/Math.max(1,width),h/l.glyphs.height);
    let dx=x+(l.plate?(w-width*scale)/2:0);
    const dh=l.glyphs.height*scale,dy=y+(h-dh)/2;
    for(const [sx,sw] of spans){ctx.drawImage(l.atlas,sx,0,sw,l.glyphs.height,dx,dy,sw*scale,dh);dx+=sw*scale;}
  }
  function draw(canvas,frame,stamp){
    const ctx=canvas.getContext('2d'),now=new Date(stamp);
    ctx.drawImage(frame.bg,0,0);
    let animating=false;
    for(const layer of frame.layers){
      const [x,y,w,h]=layer.box, current=value(layer,now), old=value(layer,new Date(stamp-1000));
      const phase=layer.duration?Math.min(1,(stamp%1000)/layer.duration):1;
      if(layer.plate && current!==old && phase<1){
        animating=true;
        for(const [top,label] of [[true,current],[false,old]]){
          ctx.save();ctx.beginPath();ctx.rect(x,y+(top?0:h/2),w,h/2);ctx.clip();paint(ctx,layer,label);ctx.restore();
        }
        const cosine=Math.cos(Math.PI*phase),upper=cosine>=0;
        ctx.save();ctx.translate(0,y+h/2);ctx.scale(1,Math.abs(cosine));ctx.translate(0,-y-h/2);
        ctx.beginPath();ctx.rect(x+1,y+(upper?0:h/2),w-2,h/2);ctx.clip();ctx.fillStyle=layer.plate;ctx.fillRect(x,y,w,h);
        paint(ctx,layer,upper?old:current);ctx.restore();
      }else paint(ctx,layer,current);
      if(layer.plate){ctx.fillStyle=layer.seam;ctx.fillRect(x,y+Math.floor(h/2),w,1);}
    }
    return animating;
  }
  function attach(card,frame){
    if(!card.isConnected||active.get(card)===frame)return;
    active.set(card,frame);
    const canvas=document.createElement('canvas');canvas.width=frame.width;canvas.height=frame.height;canvas.className='package-scene';
    card.replaceChildren(canvas);
    function tick(){
      if(!canvas.isConnected)return;
      const now=Date.now(),moving=draw(canvas,frame,now);
      if(frame.layers.length)setTimeout(tick,moving?40:1000-now%1000+2);
    }
    tick();
  }
  function preview(card,title,spec,size,api,version){
    const key=JSON.stringify([version,title,spec,size]);
    requested.set(card,key);
    const display=frame=>{if(frame&&requested.get(card)===key)attach(card,frame);};
    let item=cache.get(key);
    if(!item||(!item.loading&&Date.now()-item.time>3000)){
      const prior=item?.frame;
      item={time:Date.now(),frame:prior,loading:true};cache.set(key,item);
      item.result=api('/api/store/widget-layout',{method:'POST',body:JSON.stringify({title,spec,size})})
        .then(r=>r.json()).then(prepare).then(frame=>item.frame=frame).catch(()=>prior).finally(()=>item.loading=false);
      if(cache.size>64)cache.delete(cache.keys().next().value);
    }
    if(item.frame)queueMicrotask(()=>display(item.frame));
    item.result.then(display);
  }
  return {preview};
})();
