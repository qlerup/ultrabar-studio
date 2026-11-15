'use strict';
(() => {
  let draft=null, dirty=false, working=false, profileIndex=0, widgetIndex=0, moduleSerial='', inputKey='', mode='layout', apps=[], pcActions=[], history=[], drag=null;
  let editorGeneration=0, pcDestination='widget', pcMetrics={};
  let storePresets=[];
  const clone=v=>structuredClone(v);
  const current=()=>draft?.profiles[profileIndex];
  const types={CPU:'CPU usage',MEMORY:'RAM usage',STORAGE:'Disk usage',TIME:'Clock',APPS:'Core app',PC_CONTROL:'PC action'};
  const glyphs={CPU:'▥',MEMORY:'▤',STORAGE:'◴',TIME:'◷',APPS:'▦',PC_CONTROL:'↗'};
  const message=(text,error=false)=>{$('editor-notice').textContent=text;$('editor-notice').classList.toggle('error',error);};
  function updateControls(){
    for(const id of ['draft-save','draft-deploy','draft-reset','draft-restore','widget-undo'])$(id).disabled=working||!draft;
    $('draft-status').textContent=!draft?'Loading draft…':dirty?'Unsaved draft changes':`Draft saved · ${new Date(draft.saved_at).toLocaleTimeString()}`;
    $('editor-content').classList.toggle('editor-working',working);
  }
  function checkpoint(){history.push(clone(draft.profiles));if(history.length>30)history.shift();dirty=true;updateControls();}
  function change(fn,refresh=true){if(working||!draft)return;checkpoint();fn();if(refresh)renderEditor();}
  function showMode(next){mode=next;for(const m of ['layout','actions','pc']){$(m+'-editor').hidden=m!==mode;$('mode-'+m).setAttribute('aria-pressed',m===mode);}if(mode==='pc')refreshPc();}
  async function openEditor(){
    if(!snapshot||busy||working)return;
    window.studioStore?.leave();
    document.body.classList.add('editing');$('nav-editor').classList.add('nav-active');$('nav-overview').classList.remove('nav-active');
    $('overview-content').hidden=true;$('editor-content').hidden=false;
    $('nav-editor').setAttribute('aria-pressed','true');$('nav-overview').setAttribute('aria-pressed','false');
    if(draft?.device_id===snapshot.device_id){renderEditor();loadStorePresets();return;}
    working=true;updateControls();const generation=++editorGeneration;
    try{
      const data=await (await api('/api/editor')).json();
      if(generation!==editorGeneration)return;
      draft=data.draft;dirty=false;history=[];profileIndex=Math.min(selectedProfile,draft.profiles.length-1);widgetIndex=0;
      message(data.conflict?'Core settings have changed since this draft was created. Use Draft & recovery tools to reload before deploying.':'Changes stay in your draft until you deploy.',data.conflict);
      renderEditor();
      await Promise.allSettled([loadCatalog(),refreshPc(),loadStorePresets()]);
    }catch(error){message(error.message,true);}
    finally{working=false;updateControls();}
  }
  function overview(){if(working)return;window.studioStore?.leave();document.body.classList.remove('editing');$('nav-editor').classList.remove('nav-active');$('nav-overview').classList.add('nav-active');$('overview-content').hidden=false;$('editor-content').hidden=true;$('nav-editor').setAttribute('aria-pressed','false');$('nav-overview').setAttribute('aria-pressed','true');}
  async function loadCatalog(){try{apps=(await (await api('/api/editor/catalog')).json()).apps;renderLibrary();renderActionLibrary();}catch(error){message(error.message,true);}}
  function option(select,value,label){const item=el('option','',label);item.value=value;select.append(item);}
  function renderEditor(){
    if(!draft)return;
    const select=$('edit-profile');select.replaceChildren();draft.profiles.forEach((p,i)=>option(select,i,p.name));select.value=profileIndex;
    $('edit-profile-name').value=current()?.name||'';$('edit-show-names').checked=current()?.showName!==false;
    renderLibrary();renderCanvas();renderProperties();renderModules();updateControls();
  }
  function nativeSpec(w){return w.param?.payload?.action==='studioNative'?w.param.payload.params:null;}
  function nativeTemplate(kind,name,drive='all'){return {type:'PC_CONTROL',name,bgColor:'#192325',iconScale:0,_new:true,_native:true,param:{output:10,payload:{action:'studioNative',params:{kind,accent:'#94d9bb',textColor:'#eef6f2',...(kind==='disk'?{drive}:{})}}}};}
  async function loadStorePresets(){
    try{
      const data=await(await api('/api/store/installed')).json();
      storePresets=(data.widgets||[]).map((w,i)=>{
        const t=w.kind==='clock'&&!w._widgetPackage?{type:'TIME',name:w.name,iconScale:100,_new:true}:nativeTemplate(w.kind,w.name);
        t._storePackage=w._storePackage;t._storeKey=w._storePackage+':'+(w.id||i);
        if(w.kindOptions)nativeSpec(t).kindOptions=[...w.kindOptions];
        if(w._widgetPackage){Object.assign(nativeSpec(t),{packageId:w._storePackage,packageVersion:w._storeVersion,widgetKey:w.id});if(w.kind==='clock')Object.assign(nativeSpec(t),{hourFormat:w.hourFormat||'24',showSeconds:w.showSeconds??true,showDate:w.showDate??true});}
        if(w.background)t.bgColor=w.background;
        if(nativeSpec(t)){if(w.textColor)nativeSpec(t).textColor=w.textColor;if(w.accent)nativeSpec(t).accent=w.accent;}
        return t;
      });
      if(draft&&!drag)renderLibrary();
    }catch(error){message('Could not load installed store presets. '+error.message,true);}
  }
  window.addEventListener('studio-store-changed',()=>{loadStorePresets();if(snapshot)loadCatalog();});
  function stock(){return [{type:'TIME',name:'Clock',iconScale:100,_new:true}];}
  function library(){
    const existing=draft.profiles.flatMap(p=>p.homeData||[]).filter(w=>!nativeSpec(w));const seen=new Set();
    return [...stock(),...storePresets,...apps,...existing].filter(w=>{const spec=nativeSpec(w);const key=w._storeKey||(spec?.packageId&&spec?.widgetKey?spec.packageId+':'+spec.widgetKey:null)||(w._new?(nativeSpec(w)?nativeSpec(w).kind+':'+(nativeSpec(w).drive||''):w.type):JSON.stringify([w.type,w.id]));if(w.param?.payload?.action==='studioMetric'||seen.has(key))return false;seen.add(key);return true;});
  }
  // Pointer-based dragging avoids native HTML5/WebView drag restrictions and
  // makes the entire scaled Core viewport a target, with a visible insert line.
  let widgetPointer=null,suppressWidgetClickUntil=0;
  function widgetDropIndex(x,y){
    const screen=$('core-screen').getBoundingClientRect();
    if(x<screen.left||x>screen.right||y<screen.top||y>screen.bottom)return null;
    const cards=[...$('core-canvas').querySelectorAll('.canvas-widget')];
    const next=cards.findIndex(card=>{const r=card.getBoundingClientRect();return x<r.left+r.width/2;});
    return next<0?cards.length:next;
  }
  function paintWidgetDrag(){
    const d=widgetPointer;if(!d?.active)return;
    const screen=$('core-screen').getBoundingClientRect();
    d.ghost.style.left=(d.x+14)+'px';d.ghost.style.top=(d.y+14)+'px';
    let at=widgetDropIndex(d.x,d.y);
    if(at!==null){
      if(d.x<screen.left+40)$('core-canvas').scrollLeft-=12;
      if(d.x>screen.right-40)$('core-canvas').scrollLeft+=12;
      at=widgetDropIndex(d.x,d.y);
      const cards=[...$('core-canvas').querySelectorAll('.canvas-widget')];
      const x=cards[at]?.getBoundingClientRect().left??cards.at(-1)?.getBoundingClientRect().right??screen.left+12;
      d.marker.hidden=false;d.marker.style.left=Math.max(screen.left+2,Math.min(screen.right-4,x))+'px';d.marker.style.top=(screen.top+8)+'px';d.marker.style.height=Math.max(10,screen.height-16)+'px';
    }else d.marker.hidden=true;
    d.index=at;d.frame=requestAnimationFrame(paintWidgetDrag);
  }
  function endWidgetDrag(cancel=false){
    const d=widgetPointer;if(!d)return;widgetPointer=null;
    if(d.node.hasPointerCapture(d.pointerId))d.node.releasePointerCapture(d.pointerId);
    if(!d.active)return;
    cancelAnimationFrame(d.frame);d.ghost.remove();d.marker.remove();d.node.classList.remove('dragging');
    const at=widgetDropIndex(d.x,d.y);drag=null;suppressWidgetClickUntil=Date.now()+400;
    if(cancel||at===null){message('Move cancelled.');return;}
    if(d.payload.kind==='widget-new')addWidget(d.payload.widget,at);
    else moveWidget(d.payload.index,at);
  }
  document.addEventListener('pointermove',event=>{
    const d=widgetPointer;if(!d||event.pointerId!==d.pointerId)return;
    d.x=event.clientX;d.y=event.clientY;
    if(!d.active&&Math.hypot(d.x-d.startX,d.y-d.startY)>7){
      d.active=true;drag=d.payload;d.node.setPointerCapture(event.pointerId);d.node.classList.add('dragging');
      d.ghost=el('div','widget-drag-ghost',d.payload.widget?.name||d.node.getAttribute('aria-label')||'Move widget');
      d.marker=el('div','widget-insert-marker');d.marker.hidden=true;document.body.append(d.ghost,d.marker);paintWidgetDrag();
    }
    if(d.active)event.preventDefault();
  },{passive:false});
  document.addEventListener('pointerup',event=>{if(widgetPointer?.pointerId===event.pointerId)endWidgetDrag();});
  document.addEventListener('pointercancel',()=>endWidgetDrag(true));
  window.addEventListener('blur',()=>endWidgetDrag(true));
  document.addEventListener('keydown',event=>{if(event.key==='Escape'&&widgetPointer){event.preventDefault();endWidgetDrag(true);}});
  document.addEventListener('click',event=>{if(Date.now()<suppressWidgetClickUntil&&event.target.closest('.library-item,.canvas-widget')){event.preventDefault();event.stopImmediatePropagation();}},true);
  function draggable(node,payload){
    if(payload.kind.startsWith('widget-')){
      node.draggable=false;node.style.touchAction='none';
      node.addEventListener('pointerdown',event=>{if(event.button!==0||working||widgetPointer)return;widgetPointer={node,payload,pointerId:event.pointerId,startX:event.clientX,startY:event.clientY,x:event.clientX,y:event.clientY,active:false};});
      return;
    }
    node.draggable=true;node.addEventListener('dragstart',event=>{if(working){event.preventDefault();return;}drag=payload;event.dataTransfer.setData('text/plain','ultrabar-studio');event.dataTransfer.effectAllowed='copyMove';node.classList.add('dragging');});node.addEventListener('dragend',()=>{drag=null;node.classList.remove('dragging');document.querySelectorAll('.drop-target').forEach(n=>n.classList.remove('drop-target'));});}
  function dropzone(node,handler){node.addEventListener('dragover',event=>{if(!drag||working)return;event.preventDefault();event.stopPropagation();node.classList.add('drop-target');});node.addEventListener('dragleave',()=>node.classList.remove('drop-target'));node.addEventListener('drop',event=>{if(!drag||working)return;event.preventDefault();event.stopPropagation();node.classList.remove('drop-target');handler(drag);drag=null;});}
  const libraryExpanded={ultrabar:true,studio:true,store:true,installed:false};
  function libraryGroup(w){
    if(w._storePackage||nativeSpec(w)?.packageId)return 'store';
    if(w.type==='APPS')return 'installed';
    if(nativeSpec(w)||w.param?.payload?.action==='studioAction')return 'studio';
    return ['CPU','MEMORY','STORAGE','TIME'].includes(w.type)?'ultrabar':'installed';
  }
  function renderLibrary(){
    if(!draft)return;
    const container=$('widget-library');
    // Keep the user's disclosure choices when metrics or the draft refresh.
    for(const group of container.querySelectorAll('details[data-group]')){
      if(!group.dataset.searching)libraryExpanded[group.dataset.group]=group.open;
    }
    container.replaceChildren();
    const query=$('library-search').value.trim().toLowerCase();
    const widgets=library().filter(w=>(w.name||types[w.type]||w.type).toLowerCase().includes(query));
    const groups=[['ultrabar','UltraBarX','Built-in Core widgets.'],['studio','Studio','Widgets and PC actions provided by Studio.'],['store','App Store','Widgets and presets installed from the Store.'],['installed','Other apps & widgets on Core','Already on Core. Their original source is not recorded.']];
    for(const [key,title,help] of groups){
      const items=widgets.filter(w=>libraryGroup(w)===key);
      if(query&&!items.length)continue;
      const group=el('details','library-group');group.dataset.group=key;
      group.open=query?true:libraryExpanded[key];if(query)group.dataset.searching='true';
      const summary=el('summary','library-group-heading');summary.append(el('span','',title),el('span','library-count',String(items.length)));
      const content=el('div','library-group-content');content.append(el('p','muted library-group-help',help));
      for(const w of items){const b=el('button','library-item');b.type='button';b.append(el('span','library-glyph',glyphs[w.type]||'?'),el('span','',w.name||types[w.type]||w.type));b.setAttribute('aria-label',w.name||types[w.type]||w.type);b.title='Add '+(w.name||w.type);b.onclick=()=>addWidget(w);draggable(b,{kind:'widget-new',widget:w});content.append(b);}
      if(!items.length)content.append(el('p','muted','No items available.'));
      group.append(summary,content);container.append(group);
    }
    if(!container.children.length)container.append(el('p','muted','No matching widgets.'));
  }
  function addWidget(template,at=current().homeData.length){
    const widget=clone(template);delete widget._storePackage;delete widget._storeKey;if(widget._new){widget.id=(widget._native?'studio_native_':'studio_')+crypto.randomUUID().replaceAll('-','');delete widget._new;delete widget._native;}
    if(current().homeData.some(w=>w.id===widget.id)){message('This widget is already on Core. Select its card to edit it.');return;}
    change(()=>{current().homeData.splice(at,0,widget);widgetIndex=at;});
  }
  function moveWidget(from,to){if(from===to)return;change(()=>{const list=current().homeData;const [w]=list.splice(from,1);list.splice(to>from?to-1:to,0,w);widgetIndex=list.indexOf(w);});}
  function renderNativePreview(w,card){
    const spec=nativeSpec(w);card.classList.add('native-preview');card.style.backgroundColor=w.bgColor||'#192325';card.style.color=spec.textColor||'#eef6f2';card.style.setProperty('--widget-accent',spec.accent);
    card.replaceChildren(el('strong','native-title',w.name||'Studio'));
    const bar=value=>{const track=el('span','native-track'),fill=el('span','');fill.style.width=Math.max(0,Math.min(100,value||0))+'%';track.append(fill);return track;};
    const number=value=>value==null?'--':Number(value).toFixed(1);
    if(spec.kind==='clock'){
      const now=new Date(),format={hour:'2-digit',minute:'2-digit',hour12:spec.hourFormat==='12'};if(spec.showSeconds!==false)format.second='2-digit';
      card.append(el('span','native-source','CORE CLOCK'),el('span','native-clock-time',now.toLocaleTimeString([],format)));
      if(spec.showDate!==false)card.append(el('span','native-detail',now.toLocaleDateString([],{weekday:'short',day:'numeric',month:'short',year:'numeric'})));
    }else if(spec.kind==='disk'){
      const drives=(pcMetrics.disks||[]).filter(d=>spec.drive==='all'||d.name===spec.drive);
      if(!drives.length){card.append(el('span','native-offline','Drive unavailable'));return;}
      if(spec.drive==='all'){
        for(const d of drives.slice(0,2)){const row=el('span','native-disk-row'),top=el('span','native-row-top');top.append(el('span','',d.name.slice(0,2)),el('span','',number(d.percent)+'%'));row.append(top,bar(d.percent),el('span','native-detail',number(d.used_gb)+' / '+number(d.total_gb)+' GB'));card.append(row);}
        if(drives.length>2)card.append(el('span','native-rotation',drives.length+' drives / 2 at a time'));
      }else{const d=drives[0];card.append(el('span','native-source',d.name.slice(0,2)+' / LOCAL DISK'),el('span','native-value',number(d.percent)+'%'),el('span','native-detail',number(d.used_gb)+' / '+number(d.total_gb)+' GB'),bar(d.percent),el('span','native-detail',number(d.total_gb-d.used_gb)+' GB free'));}
    }else{
      const value=spec.kind==='gpu'?pcMetrics.gpu?.usage:pcMetrics[spec.kind];let detail='PC usage';if(spec.kind==='memory')detail=number(pcMetrics.memory_used_gb)+' / '+number(pcMetrics.memory_total_gb)+' GB';if(spec.kind==='gpu')detail=pcMetrics.gpu?.name||'Sensor unavailable';
      card.append(el('span','native-source',spec.kind.toUpperCase()),el('span','native-value',number(value)+(value==null?'':'%')),el('span','native-detail',detail),bar(value));
    }
  }
  function renderStockPreview(w,card){
    card.classList.add('stock-preview');
    const title=el('strong','stock-title',w.name||types[w.type]||w.type);
    if(['CPU','MEMORY','STORAGE'].includes(w.type)){
      const disks=pcMetrics.disks||[],total=disks.reduce((s,d)=>s+d.total_gb,0);
      const value=w.type==='STORAGE'?(total?disks.reduce((s,d)=>s+d.used_gb,0)/total*100:null):pcMetrics[w.type==='CPU'?'cpu':'memory'];
      const gauge=el('span','stock-gauge');gauge.style.setProperty('--usage',Math.max(0,Math.min(100,value||0))+'%');
      gauge.append(el('span','stock-gauge-value',value==null?'--':Math.round(value)+'%'));
      card.replaceChildren(gauge,title,el('small','',w.type==='STORAGE'?'All PC drives':w.type==='MEMORY'?'Memory usage':'Processor usage'));
    }else if(w.type==='TIME'){
      card.classList.add('clock-preview');const now=new Date();
      const face=el('span','clock-face');face.append(el('span','clock-time',now.toLocaleTimeString([], {hour:'2-digit',minute:'2-digit'})),el('span','clock-date',now.toLocaleDateString([], {weekday:'long',day:'numeric',month:'short'})));
      card.replaceChildren(el('span','clock-art'),face,title);
    }else{
      const payload=w.param?.payload,action=pcActions.find(a=>a.id===payload?.params?.id);
      const text=payload?.action==='inputText'?payload.params?.text:null;
      const icon=el('span','stock-app-icon',text|| (w.type==='PC_CONTROL'?'↗':'▦'));
      icon.style.fontSize=(64*Math.min(2,Math.max(0,(w.iconScale??100)/100)))+'px';
      card.replaceChildren(icon,title,el('small','',action?.kind==='url'?'Open website':w.type==='PC_CONTROL'?'PC shortcut':'Core app'));
    }
  }
  function syncCoreScroll(){
    const canvas=$('core-canvas'),slider=$('core-scroll');
    slider.max=Math.max(0,canvas.scrollWidth-canvas.clientWidth);slider.value=canvas.scrollLeft;slider.disabled=Number(slider.max)===0;
  }
  const screen=$('core-screen');
  new ResizeObserver(()=>{const scale=screen.clientWidth/1424;$('core-canvas').style.transform=`scale(${scale})`;screen.style.height=(280*scale)+'px';syncCoreScroll();}).observe(screen);
  $('core-scroll').oninput=()=>{$('core-canvas').scrollLeft=Number($('core-scroll').value);};
  $('core-canvas').addEventListener('scroll',syncCoreScroll);
  $('core-previous').onclick=()=>{$('core-canvas').scrollLeft-=1424;};
  $('core-next').onclick=()=>{$('core-canvas').scrollLeft+=1424;};
  function renderCanvas(){
    const canvas=$('core-canvas'),position=canvas.scrollLeft;canvas.replaceChildren();
    current().homeData.forEach((w,i)=>{const card=el('button','canvas-widget'+(i===widgetIndex?' selected':''));card.setAttribute('aria-pressed',i===widgetIndex);card.setAttribute('aria-label',w.name||types[w.type]||w.type);card.append(el('span','canvas-glyph',glyphs[w.type]||'◇'),el('strong','',w.name||types[w.type]||w.type),el('small','',nativeSpec(w)?'Studio '+nativeSpec(w).kind:w.type==='PC_CONTROL'?'PC action':w.type));if(w.bgColor)card.style.backgroundColor=w.bgColor;if(nativeSpec(w))renderNativePreview(w,card);card.onclick=()=>{widgetIndex=i;renderCanvas();renderProperties();};draggable(card,{kind:'widget-move',index:i});dropzone(card,data=>{if(data.kind==='widget-new')addWidget(data.widget,i);if(data.kind==='widget-move')moveWidget(data.index,i);});canvas.append(card);});
    [...canvas.children].forEach((card,i)=>{if(!nativeSpec(current().homeData[i]))renderStockPreview(current().homeData[i],card);});
    if(!current().homeData.length)canvas.append(el('p','canvas-empty','Drop widgets here to build your Core screen'));
    canvas.scrollLeft=position;requestAnimationFrame(syncCoreScroll);
  }
  dropzone($('core-canvas'),data=>{if(data.kind==='widget-new')addWidget(data.widget);if(data.kind==='widget-move')moveWidget(data.index,current().homeData.length);});
  function field(label,value,onchange,type='text'){const wrap=el('label','property-field',label),input=el('input');input.type=type;input.value=value;input.onchange=()=>onchange(input.value);wrap.append(input);return wrap;}
  function button(text,fn,cls=''){const b=el('button',cls,text);b.type='button';b.onclick=fn;return b;}
  function renderProperties(){
    const panel=$('widget-properties');panel.replaceChildren(el('h3','','Widget settings'));const w=current().homeData[widgetIndex];if(!w){panel.append(el('p','muted','Select a card to edit it.'));return;}
    const spec=nativeSpec(w);
    panel.append(el('span','badge',spec?'Studio widget':w.type),field('Display name',w.name||'',v=>change(()=>w.name=v)),field('Background color',/^#[a-f0-9]{6}$/i.test(w.bgColor)?w.bgColor:(spec?'#192325':'#202a2b'),v=>change(()=>w.bgColor=v),'color'));
    if(spec){
      panel.append(field('Text color',spec.textColor||'#eef6f2',v=>change(()=>spec.textColor=v),'color'),field('Accent color',spec.accent,v=>change(()=>spec.accent=v),'color'));
      if(spec.packageId)panel.append(el('p','muted','Store package: '+spec.packageId+' / '+spec.packageVersion));
      if(spec.kind==='clock'){
        const wrap=el('label','property-field','Time format'),select=el('select');select.id='widget-hour-format';option(select,'24','24 hours');option(select,'12','12 hours');select.value=spec.hourFormat||'24';select.onchange=()=>change(()=>spec.hourFormat=select.value);wrap.append(select);panel.append(wrap);
        for(const [key,label] of [['showSeconds','Show seconds'],['showDate','Show date']]){const wrap=el('label','property-field',label),input=el('input');input.type='checkbox';input.id='widget-'+key;input.checked=spec[key]!==false;input.onchange=()=>change(()=>spec[key]=input.checked);wrap.append(input);panel.append(wrap);}
      }
      if(spec.kindOptions?.length){
        const wrap=el('label','property-field','Show'),select=el('select');select.id='widget-kind';
        const labels={cpu:'CPU usage',memory:'RAM usage',gpu:'GPU usage'};
        for(const kind of spec.kindOptions)option(select,kind,labels[kind]||kind);
        select.value=spec.kind;select.onchange=()=>change(()=>{spec.kind=select.value;});wrap.append(select);panel.append(wrap);
      }
      if(spec.kind==='disk'){
        const wrap=el('label','property-field','Drive'),select=el('select');select.id='widget-drive';option(select,'all','All drives (2 at a time)');
        const drives=new Set((pcMetrics.disks||[]).map(d=>d.name));if(spec.drive!=='all')drives.add(spec.drive);
        for(const drive of drives)option(select,drive,drive.slice(0,2));select.value=spec.drive;
        select.onchange=()=>change(()=>{spec.drive=select.value;delete spec.drives;});wrap.append(select);panel.append(wrap);
        if(spec.drive==='all')panel.append(el('p','muted','Shows two drives at a time. With more than two drives, the card switches to the next pair every 6 seconds.'));
      }
      panel.append(el('p','muted',spec.kind==='clock'?'Deploy to show this clock on Core. Uses Core time and locale; preview uses PC time. Keep Studio connected to restore the widget after Core restarts.':'Preview your colors here, then deploy to Core. Keep Studio connected for live readings.'));
    }else panel.append(field('Icon size (%)',w.iconScale??100,v=>{const n=Number(v);if(Number.isInteger(n)&&n>=0&&n<=200)change(()=>w.iconScale=n);else message('Icon size must be 0-200.',true);},'number'));
    const moves=el('div','property-moves');moves.append(button('←',()=>moveWidget(widgetIndex,Math.max(0,widgetIndex-1))),button('→',()=>moveWidget(widgetIndex,Math.min(current().homeData.length,widgetIndex+2))));panel.append(moves);
    panel.append(button('Remove from Core',()=>change(()=>{current().homeData.splice(widgetIndex,1);widgetIndex=Math.max(0,widgetIndex-1);}), 'danger-quiet'));
    if(w.type==='PC_CONTROL'&&!nativeSpec(w))panel.append(el('p','muted','PC actions require Studio or their original PC software to be connected.'));
    if(['CPU','MEMORY','STORAGE'].includes(w.type))panel.append(el('p','muted',w.type==='STORAGE'?'Shows combined usage of fixed PC drives. Individual drives appear under PC connection.':'Reads actual PC measurements while Studio is connected.'));
  }
  function modules(){const map=new Map((snapshot.hardware?.devices||[]).filter(d=>['DOT_KEY','VIVO_CUBE','KNOB_KEY','SENSE_CUBE'].includes(d.type)).map(d=>[d.serial,{serialNo:d.serial,productId:d.type}]));for(const m of current().module)map.set(m.serialNo,m);return [...map.values()];}
  function renderModules(){
    const list=modules();if(!list.some(m=>m.serialNo===moduleSerial))moduleSerial=list[0]?.serialNo||'';
    const select=$('action-module');select.replaceChildren();list.forEach(m=>option(select,m.serialNo,`${names[m.productId]||m.productId} · ${m.serialNo.slice(-6)}`));select.value=moduleSerial;
    const m=list.find(m=>m.serialNo===moduleSerial);const input=$('action-input');input.replaceChildren();
    if(m){if(m.productId==='SENSE_CUBE'){for(let i=0;i<5;i++)option(input,'sense:'+i,'Tap event '+(i+1));}
    else{const slots=m.productId==='DOT_KEY'?[2,3]:m.productId==='KNOB_KEY'?[0]:[...new Set([101,...(Array.isArray(m.config)?m.config.map(c=>c.keyCode):[])])];for(const key of slots)for(const [kind,label] of Object.entries({singleClick:'Single press',doubleClick:'Double press',longPress:'Long press'}))option(input,key+':'+kind,`${m.productId==='VIVO_CUBE'?'Screen button '+key:m.productId==='DOT_KEY'?'Button '+(key-1):'Button'} · ${label}`);}}
    if(![...input.options].some(o=>o.value===inputKey))inputKey=input.options[0]?.value||'';input.value=inputKey;renderActionLibrary();renderSequence();
  }
  function inputScene(create=false){
    let m=current().module.find(m=>m.serialNo===moduleSerial);if(!m&&create){const meta=modules().find(m=>m.serialNo===moduleSerial);if(!meta)return null;m={serialNo:meta.serialNo,productId:meta.productId,config:meta.productId==='KNOB_KEY'?{}:[]};current().module.push(m);}if(!m)return null;
    const [key,kind]=inputKey.split(':');
    if(key==='sense'){let scene=m.config.find(s=>s.mode===Number(kind));if(!scene&&create){scene={mode:Number(kind),actions:[],name:'Tap event '+(Number(kind)+1),type:'MANUAL',enabled:false,show:false};m.config.push(scene);}return scene;}
    let slot=m.productId==='KNOB_KEY'?m.config.button:m.config.find(s=>s.keyCode===Number(key));
    if(!slot&&create){slot={keyCode:Number(key)};if(m.productId==='VIVO_CUBE')slot.widgetType=1;if(m.productId==='KNOB_KEY')m.config.button=slot;else m.config.push(slot);}
    if(!slot)return null;if(!slot[kind]&&create)slot[kind]={actions:[],name:kind,type:'MANUAL',enabled:false,show:false};return slot[kind];
  }
  function actionName(a){if(a.type==='ACTIVITY')return apps.find(w=>w.id===a.values?.[0]?.value)?.name||a.values?.[0]?.value||'Open Core app';if(a.type==='PC_CONTROL'){const payload=a.values?.[0]?.value?.payload;return pcActions.find(p=>p.id===payload?.params?.id)?.name||a.name||payload?.action||'PC action';}return a.name||a.type||'Action';}
  function pcParam(a){return {output:10,payload:{action:'studioAction',params:{id:a.id}}};}
  function pcAction(a){return {type:'PC_CONTROL',values:[{id:'1',value:pcParam(a)}]};}
  function actionLibrary(){
    const list=apps.map(w=>({type:'ACTIVITY',id:'activity',values:[{id:'1',value:w.id}]}));list.push(...pcActions.map(pcAction));
    function walk(v){if(!v||typeof v!=='object')return;if(Array.isArray(v.actions))list.push(...v.actions);else Object.values(v).forEach(walk);}
    draft.profiles.forEach(p=>walk(p.module));const seen=new Set();return list.filter(a=>{const key=JSON.stringify(a);if(seen.has(key))return false;seen.add(key);return true;});
  }
  function renderActionLibrary(){if(!draft)return;const box=$('action-library');box.replaceChildren();for(const a of actionLibrary()){const b=button(actionName(a),()=>addAction(a),'library-item');draggable(b,{kind:'action-new',action:a});box.append(b);}}
  function addAction(a,index=null){if(!inputKey){message('Select a module input first.',true);return;}change(()=>{const s=inputScene(true);s.actions??=[];s.actions.splice(index??s.actions.length,0,clone(a));});}
  function moveAction(from,to){change(()=>{const list=inputScene().actions;const [a]=list.splice(from,1);list.splice(to>from?to-1:to,0,a);});}
  function renderSequence(){
    const box=$('action-sequence');box.replaceChildren();$('action-input-title').textContent=$('action-input').selectedOptions[0]?.textContent||'No module selected';
    const actions=inputScene()?.actions||[];actions.forEach((a,i)=>{const row=el('div','sequence-item');row.append(el('span','step-number',String(i+1).padStart(2,'0')),el('strong','',actionName(a)),el('small','muted',a.type));const controls=el('div','sequence-buttons');controls.append(button('↑',()=>moveAction(i,Math.max(0,i-1))),button('↓',()=>moveAction(i,Math.min(actions.length,i+2))),button('Remove',()=>change(()=>inputScene().actions.splice(i,1))));row.append(controls);draggable(row,{kind:'action-move',index:i});dropzone(row,data=>{if(data.kind==='action-new')addAction(data.action,i);if(data.kind==='action-move')moveAction(data.index,i);});box.append(row);});
    if(!actions.length)box.append(el('p','canvas-empty','Drop actions here, or choose one from the library'));
  }
  dropzone($('action-sequence'),data=>{if(data.kind==='action-new')addAction(data.action);if(data.kind==='action-move')moveAction(data.index,inputScene().actions.length);});
  async function save(){const response=await (await api('/api/editor/draft',{method:'POST',body:JSON.stringify({device_id:draft.device_id,revision:draft.revision,profiles:draft.profiles})})).json();draft=response.draft;dirty=false;updateControls();}
  async function operation(fn){if(working||!draft)return;working=true;busy=true;controls();updateControls();try{await fn();}catch(error){message(error.message,true);}finally{working=false;busy=false;controls();updateControls();}}
  async function refreshPc(){
    try{const data=await (await api('/api/pc')).json();pcActions=data.actions||[];pcMetrics=data.metrics||{};$('pc-status').textContent=data.status+' / '+(data.native_status||'');
      const metrics=$('pc-metrics');metrics.replaceChildren();for(const [label,value] of [['CPU',data.metrics?.cpu],['RAM',data.metrics?.memory],['GPU',data.metrics?.gpu?.usage]]){const card=el('div','metric-card');card.append(el('span','muted',label),el('strong','',value==null?'Unavailable':Math.round(value)+'%'));metrics.append(card);}for(const disk of data.metrics?.disks||[]){const card=el('div','metric-card');card.append(el('span','muted',disk.name),el('strong','',Math.round(disk.percent)+'%'),el('small','muted',disk.used_gb+' / '+disk.total_gb+' GB'));metrics.append(card);}
      $('pc-actions-list').replaceChildren(el('h3','','Saved PC actions'));for(const a of pcActions){const row=el('div','pc-action-row');row.append(el('strong','',a.name),el('span','muted',a.target),button('Add to Core',()=>{showMode('layout');addPcWidget(a);}));$('pc-actions-list').append(row);}if(draft){renderActionLibrary();if(!drag){renderLibrary();renderCanvas();}}
    }catch(error){$('pc-status').textContent=error.message;}
  }
  function addPcWidget(a){addWidget({id:'studio_pc_'+a.id,type:'PC_CONTROL',name:a.name,icon:'resId://pc_control_def_icon',iconScale:75,param:pcParam(a)});}
  function showPcDialog(destination){pcDestination=destination;$('pc-action-form').reset();$('pc-action-error').textContent='';$('pc-action-kind').dispatchEvent(new Event('change'));$('pc-action-dialog').showModal();}
  $('pc-action-form').onsubmit=async event=>{event.preventDefault();const submit=event.submitter;submit.disabled=true;try{const data=await (await api('/api/pc/actions',{method:'POST',body:JSON.stringify({name:$('pc-action-name').value,kind:$('pc-action-kind').value,target:$('pc-action-target').value,device_id:draft.device_id})})).json();pcActions=data.actions;$('pc-action-dialog').close();if(pcDestination==='widget')addPcWidget(data.action);else addAction(pcAction(data.action));}catch(error){$('pc-action-error').textContent=error.message;}finally{submit.disabled=false;}};
  $('pc-action-kind').onchange=()=>{const web=$('pc-action-kind').value==='url';$('pc-action-target-label').textContent=web?'Website URL':'Full path to program';$('pc-action-target').placeholder=web?'https://example.com':'C:\\Program Files\\App\\App.exe';$('pc-action-browse').hidden=web;};
  $('pc-action-browse').onclick=async()=>{try{const data=await (await api('/api/pc/browse',{method:'POST',body:'{}'})).json();if(data.path)$('pc-action-target').value=data.path;}catch(error){$('pc-action-error').textContent=error.message;}};
  $('pc-action-cancel').onclick=()=>$('pc-action-dialog').close();
  $('new-pc-widget').onclick=()=>showPcDialog('widget');$('new-pc-action').onclick=()=>showPcDialog('action');
  $('pc-connect').onclick=async()=>{try{await api('/api/pc/connect',{method:'POST',body:'{}'});await refreshPc();}catch(error){message(error.message,true);}};
  $('nav-editor').onclick=openEditor;$('nav-overview').onclick=overview;
  for(const m of ['layout','actions','pc'])$('mode-'+m).onclick=()=>showMode(m);
  $('library-search').oninput=renderLibrary;
  $('edit-profile').onchange=()=>{profileIndex=Number($('edit-profile').value);widgetIndex=0;renderEditor();};
  $('edit-profile-name').onchange=()=>change(()=>current().name=$('edit-profile-name').value);
  $('edit-show-names').onchange=()=>change(()=>current().showName=$('edit-show-names').checked);
  $('action-module').onchange=()=>{moduleSerial=$('action-module').value;inputKey='';renderModules();};
  $('action-input').onchange=()=>{inputKey=$('action-input').value;renderSequence();};
  $('widget-undo').onclick=()=>{if(working||!history.length)return;draft.profiles=history.pop();dirty=true;renderEditor();};
  $('draft-save').onclick=()=>operation(async()=>{await save();message('Draft saved on this PC. Core has not been changed.');});
  $('draft-deploy').onclick=()=>{if(!draft||working)return;const box=$('deploy-summary');box.replaceChildren();draft.profiles.forEach((p,i)=>{if(JSON.stringify(p)!==JSON.stringify(draft.base_profiles[i]))box.append(el('p','',`${p.name}: ${p.homeData.length} widgets · ${p.module.length} module configurations`));});if(!box.children.length)box.append(el('p','','No draft changes. This will verify and resend the current profile package.'));$('deploy-dialog').showModal();};
  $('deploy-cancel').onclick=()=>$('deploy-dialog').close();
  $('deploy-progress').addEventListener('cancel',event=>{if($('deploy-progress-close').disabled)event.preventDefault();});
  $('deploy-progress-close').onclick=()=>$('deploy-progress').close();
  $('deploy-confirm').onclick=()=>{$('deploy-dialog').close();operation(async()=>{
    const box=$('deploy-progress'),label=$('deploy-progress-message'),close=$('deploy-progress-close'),spinner=$('deploy-progress-spinner');
    const requestId=crypto.randomUUID(),started=Date.now();let polling=false,finished=false;
    box.dataset.state='running';box.setAttribute('aria-busy','true');$('deploy-progress-title').textContent='Deploying to Core';
    $('deploy-progress-help').textContent='Keep CoreBAR connected while Studio applies your changes.';
    $('deploy-progress-time').textContent='0 seconds elapsed';close.textContent='Deploying…';
    close.disabled=true;spinner.hidden=false;label.textContent='Saving your draft…';box.showModal();
    const timer=setInterval(async()=>{
      $('deploy-progress-time').textContent=Math.floor((Date.now()-started)/1000)+' seconds elapsed';
      if(polling||finished)return;polling=true;
      try{const status=await(await api('/api/editor/deploy-status')).json();if(!finished&&status.request_id===requestId)label.textContent=status.message;}catch(error){if(!finished)label.textContent='Waiting for a status response from Studio…';}finally{polling=false;}
    },750);
    try{
      await save();label.textContent='Contacting Core…';
      const response=await fetch('/api/editor/deploy',{method:'POST',headers:{'X-Studio-Token':token,'Content-Type':'application/json'},body:JSON.stringify({device_id:draft.device_id,revision:draft.revision,request_id:requestId})});
      const data=await response.json();if(!response.ok)throw new Error(data.error||'Deployment failed.');
      draft=data.draft;snapshot=data.snapshot;dirty=false;history=[];render();renderEditor();message(data.message);label.textContent=data.message;
      box.dataset.state='success';$('deploy-progress-title').textContent='Deployment complete';close.textContent='Done';
      $('deploy-progress-help').textContent='You can close this window and continue editing.';
      setTimeout(()=>{captureScreen();captureCubes();},1000);
    }catch(error){box.dataset.state='error';$('deploy-progress-title').textContent='Deployment interrupted';close.textContent='Close';$('deploy-progress-help').textContent='Review the message above before trying again.';label.textContent=error.message;message(error.message,true);}
    finally{finished=true;clearInterval(timer);spinner.hidden=true;close.disabled=false;box.setAttribute('aria-busy','false');$('deploy-progress-time').textContent=Math.floor((Date.now()-started)/1000)+' seconds elapsed';close.focus();}
  });};
  $('draft-reset').onclick=()=>{if(!confirm('Replace the local draft with current Core settings? Download the draft first if you want to keep it.'))return;operation(async()=>{const data=await (await api('/api/editor/reset',{method:'POST',body:JSON.stringify({device_id:draft.device_id,revision:draft.revision})})).json();draft=data.draft;snapshot=data.snapshot;dirty=false;history=[];render();renderEditor();message('Draft reloaded from Core.');});};
  $('draft-restore').onclick=()=>{if(!confirm('Replace this draft with the saved pre-deploy settings? Core changes only when you deploy.'))return;operation(async()=>{const data=await (await api('/api/editor/restore-draft',{method:'POST',body:JSON.stringify({device_id:draft.device_id,revision:draft.revision})})).json();draft=data.draft;snapshot=data.snapshot;dirty=false;history=[];render();renderEditor();message('Pre-deploy settings loaded as a draft. Review, then deploy to restore Core.');});};
  $('draft-export').onclick=()=>{const url=URL.createObjectURL(new Blob([JSON.stringify(draft,null,2)],{type:'application/json'}));const a=el('a');a.href=url;a.download='ultrabar-studio-draft.json';a.click();setTimeout(()=>URL.revokeObjectURL(url),1000);};
  window.addEventListener('beforeunload',event=>{if(dirty){event.preventDefault();event.returnValue='';}});
  window.studioEditor={async saveBeforeUpdate(){
    if(working||busy)throw new Error('Wait for the current device operation to finish before updating.');
    if(!dirty)return;
    working=true;busy=true;controls();updateControls();
    try{await save();}finally{working=false;busy=false;controls();updateControls();}
  },snapshotChanged(){ $('nav-editor').disabled=!snapshot;if(draft&&draft.device_id!==snapshot?.device_id){editorGeneration++;draft=null;dirty=false;apps=[];pcActions=[];overview();}if(snapshot)api('/api/pc/connect',{method:'POST',body:'{}'}).catch(error=>message(error.message,true));},hasUnsaved(){return dirty;}};
  setInterval(()=>{if(snapshot&&!document.hidden&&mode==='pc'&&!$('editor-content').hidden&&!working)refreshPc();},5000);
setInterval(()=>{if(!working&&!drag&&draft&&document.body.classList.contains('editing')){[...$('core-canvas').children].forEach((card,i)=>{const w=current().homeData[i];if(w&&nativeSpec(w)?.kind==='clock')renderNativePreview(w,card);});}},1000);
})();
