'use strict';
(() => {
  let draft=null, dirty=false, working=false, profileIndex=0, widgetIndex=0, moduleSerial='', inputKey='', mode='layout', apps=[], pcActions=[], history=[], drag=null;
  let editorGeneration=0, pcMetrics={}, pcRequest=null;
  let printerMetrics={}, printerRequest=false, renderBambuUnfolded=null;
  let storePresets=[];
  const storeIconByPackage=new Map(),storeIconByApp=new Map(),libraryIconCache=new Map(),libraryIconFailures=new Map();
  let backgroundIndex=-1;
  const notificationsIndex=-2;
  let notificationTestSound='complete';
  let inputChoices=[], actionType='', actionChoiceItems=[], editingActionIndex=null, actionSaving=false;
  const pcWidgetForms=new Map();
  const appSettingsDefs=new Map();
  const studioBindings=new Map();
  const packageUI=window.studioPackageUI.create({api,onConnectionsChange:()=>{if(draft){renderCanvas();renderProperties();}},onError:text=>message(text,true)});
  const picturePrefix='/sdcard/Android/data/com.ultrabar.launch/files/studio-icons/';
  const screenSyncId='dk.ultrabarx.screensync';
  const pcStandbyId='dk.qlerup.corestandby';
  const coreNotificationsId='dk.ultrabarx.notifications';
  const clone=v=>structuredClone(v);
  const current=()=>draft?.profiles[profileIndex];
  const types={CPU:'CPU usage',MEMORY:'RAM usage',STORAGE:'Disk usage',TIME:'Clock',APPS:'Core app',PC_CONTROL:'PC action'};
  const glyphs={CPU:'▥',MEMORY:'▤',STORAGE:'◴',TIME:'◷',APPS:'▦',PC_CONTROL:'↗'};
  const message=(text,error=false)=>{$('editor-notice').textContent=text;$('editor-notice').classList.toggle('error',error);};
  function updateControls(){
    for(const id of ['draft-save','draft-deploy','draft-reset','draft-restore','widget-undo'])$(id).disabled=working||actionSaving||!draft;
    $('draft-status').textContent=!draft?'Loading draft…':dirty?'Unsaved draft changes':`Draft saved · ${new Date(draft.saved_at).toLocaleTimeString()}`;
    $('editor-content').classList.toggle('editor-working',working||actionSaving);
    $('edit-profile').disabled=working||actionSaving;
    $('action-undo').disabled=working||actionSaving||!history.length;
    for(const control of $('vivo-screen-settings').querySelectorAll('button,input'))control.disabled=working||actionSaving;
  }
  function checkpoint(){history.push(clone({profiles:draft.profiles,background_apps:draft.background_apps||[],app_settings:draft.app_settings||{},vivo_screens:draft.vivo_screens||{},compact_profiles:draft.compact_profiles||{}}));if(history.length>30)history.shift();dirty=true;updateControls();}
  function change(fn,refresh=true){if(working||!draft)return;checkpoint();fn();if(refresh)renderEditor();}
  function showMode(next){if(actionSaving)return;mode=next;for(const m of ['layout','actions','pc']){$(m+'-editor').hidden=m!==mode;$('mode-'+m).setAttribute('aria-pressed',m===mode);}if(mode==='pc')refreshPc();if(mode==='actions'){renderModules();requestAnimationFrame(()=>centerHardware($('action-devices')));}}
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
  function overview(){if(working||actionSaving)return;window.studioStore?.leave();document.body.classList.remove('editing');$('nav-editor').classList.remove('nav-active');$('nav-overview').classList.add('nav-active');$('overview-content').hidden=false;$('editor-content').hidden=true;$('nav-editor').setAttribute('aria-pressed','false');$('nav-overview').setAttribute('aria-pressed','true');}
  async function loadCatalog(){try{apps=(await (await api('/api/editor/catalog')).json()).apps;renderLibrary();renderActionLibrary();}catch(error){message(error.message,true);}}
  function option(select,value,label){const item=el('option','',label);item.value=value;select.append(item);}
  function renderEditor(){
    if(!draft)return;
    draft.background_apps??=[];for(const app of draft.background_apps)app.settings??={};
    draft.app_settings??={};
    draft.vivo_screens??={};
    draft.compact_profiles??={};
    widgetIndex=Math.min(widgetIndex,Math.max(0,current().homeData.length-1));
    if(backgroundIndex>=draft.background_apps.length)backgroundIndex=-1;
    const select=$('edit-profile');select.replaceChildren();draft.profiles.forEach((p,i)=>option(select,i,p.name));
    option(select,'new','+ New profile…');select.lastElementChild.disabled=draft.profiles.length>=64;
    select.value=profileIndex;
    $('edit-profile-name').value=current()?.name||'';$('edit-show-names').checked=current()?.showName!==false;
    renderLibrary();renderCanvas();renderBackground();renderProperties();renderModules();renderAppSettingsRecovery();updateControls();
    refreshPrinterPreviews();
  }
  function nativeSpec(w){return w.param?.payload?.action==='studioNative'?w.param.payload.params:null;}
  function widgetSizes(widget){
    const spec=nativeSpec(widget);
    if(!spec)return ['large'];
    const template=storePresets.find(item=>{
      const candidate=nativeSpec(item);
      return candidate&&candidate.packageId===spec.packageId&&candidate.widgetKey===spec.widgetKey;
    });
    return template?._sizes||['large','small'];
  }
  const cellPitch = 140.4, rowPitch = 130, gridMargin = 20;
  function layoutParts(profile=current()){
    const layouts=draft?.compact_profiles||{};
    const value=Object.hasOwn(layouts,profile.id)?layouts[profile.id]:null;
    return Array.isArray(value)?{small:value,positions:null,splits:[]}:{small:[],positions:null,splits:[],...value};
  }
  function hasGrid(){const layout=layoutParts();return !!(layout.small.length||layout.splits.length||Object.keys(layout.positions||{}).length);}
  function isSmall(widget){return layoutParts().small.includes(widget.id);}
  function footprintWidth(widget,small){return small?1:widget.type==='TIME'?4:2;}
  function storeLayout(profile,small,positions,splits=layoutParts(profile).splits){
    if(splits.length)draft.compact_profiles={...draft.compact_profiles,[profile.id]:{small,positions:positions||{},splits}};
    else if(positions&&Object.keys(positions).length)draft.compact_profiles={...draft.compact_profiles,[profile.id]:{small,positions}};
    else if(small.length)draft.compact_profiles={...draft.compact_profiles,[profile.id]:small};
    else delete draft.compact_profiles[profile.id];
  }
  function automaticPositions(){
    const positions=Object.create(null);let column=0,row=0;
    for(const widget of current().homeData){
      if(isSmall(widget)){
        positions[widget.id]=[column,row];
        if(row===1)column++;
        row=1-row;
      }else{
        if(row===1){column++;row=0;}
        positions[widget.id]=[column,0];column+=footprintWidth(widget,false);
      }
    }
    return positions;
  }
  function positionsForCurrent(){
    const {positions}=layoutParts();
    return positions&&Object.keys(positions).length?positions:automaticPositions();
  }
  function splitOverlaps(column,width){
    return layoutParts().splits.some(split=>column<split+2&&split<column+width);
  }
  function findOverlaps(widget,small,cell,positions){
    const [column,row]=cell;
    return current().homeData.filter(other=>{
      if(other.id===widget.id||!Object.hasOwn(positions,other.id))return false;
      const [x,y]=positions[other.id], otherSmall=isSmall(other);
      return column<x+footprintWidth(other,otherSmall)&&x<column+footprintWidth(widget,small)&&(!small||!otherSmall||row===y);
    });
  }
  function nextFreeColumn(positions){
    return Math.max(0,...layoutParts().splits.map(col=>col+2),...current().homeData.filter(w=>Object.hasOwn(positions,w.id)).map(w=>positions[w.id][0]+footprintWidth(w,isSmall(w))));
  }
  function proposePosition(widget,small,cell){
    if(!small&&splitOverlaps(cell[0],footprintWidth(widget,false)))return null;
    const positions={...positionsForCurrent()}, from=positions[widget.id], overlaps=findOverlaps(widget,small,cell,positions);
    delete positions[widget.id];
    if(overlaps.length){
      if(!from||overlaps.length!==1)return null;
      const other=overlaps[0], otherSmall=isSmall(other), destination=[from[0],otherSmall?from[1]:0];
      positions[widget.id]=cell;
      if((!otherSmall&&splitOverlaps(destination[0],footprintWidth(other,false)))||findOverlaps(other,otherSmall,destination,positions).length)return null;
      positions[other.id]=destination;
    }
    return positions;
  }
  function applyPositions(widget,cell,positions){
    const layout=layoutParts();
    const selected={...positions,[widget.id]:cell};
    current().homeData.sort((a,b)=>selected[a.id][0]-selected[b.id][0]||selected[a.id][1]-selected[b.id][1]);
    storeLayout(current(),layout.small,selected);
    widgetIndex=current().homeData.indexOf(widget);
    backgroundIndex=-1;
  }
  function removePlacement(profile,widgetId){
    const layout=layoutParts(profile),positions=layout.positions?{...layout.positions}:null;
    if(positions)delete positions[widgetId];
    storeLayout(profile,layout.small.filter(id=>id!==widgetId),positions);
  }
  function nativeTemplate(kind,name,drive='all'){return {type:'PC_CONTROL',name,bgColor:'#192325',iconScale:0,_new:true,_native:true,param:{output:10,payload:{action:'studioNative',params:{kind,accent:'#94d9bb',textColor:'#eef6f2',...(kind==='disk'?{drive}:{})}}}};}
  async function loadStorePresets(){
    try{
      const data=await(await api('/api/store/installed')).json();
      appSettingsDefs.clear();for(const p of data.installed||[])if(p.settings&&p.android?.packageId)appSettingsDefs.set(p.android.packageId,{name:p.name,schema:p.settings});
      studioBindings.clear();
      for(const widget of data.widgets||[]){const descriptor=widget._studio||widget.studio;if(descriptor)studioBindings.set(widget._storePackage+':'+widget.id,{packageId:widget._storePackage,widgetKey:widget.id,kind:widget.kind,kindOptions:widget.kindOptions,version:widget._storeVersion,rendererFields:widget._rendererFields,descriptor});}
      storeIconByPackage.clear();storeIconByApp.clear();
      for(const p of data.installed||[]){if(/^[a-f0-9]{64}$/.test(p.icon?.sha256||'')){storeIconByPackage.set(p.id,p.icon.sha256);if(p.android?.packageId)storeIconByApp.set(p.android.packageId,p.icon.sha256);}}
      storePresets=(data.widgets||[]).map((w,i)=>{
        if(w.type==='APPS')return {...w,_storeKey:w._storePackage+':'+w.id};
        const t=w.kind==='clock'&&!w._widgetPackage?{type:'TIME',name:w.name,iconScale:100,_new:true}:nativeTemplate(w.kind,w.name);
        t._storePackage=w._storePackage;t._storeKey=w._storePackage+':'+(w.id||i);
        if(w._bundledApp&&w.kind!=='bambu'){t._bundledApp=clone(w._bundledApp);nativeSpec(t).companionApp=w._bundledApp.id;}
        if(w.kindOptions)nativeSpec(t).kindOptions=[...w.kindOptions];
        if(nativeSpec(t))for(const field of (w._studio||w.studio)?.settings?.fields||[]){
          if((w._studio||w.studio).api===2 && !(w._rendererFields||[]).includes(field.key))continue;
          nativeSpec(t)[field.key]=w[field.key]??field.default;
        }
        if(w._widgetPackage){Object.assign(nativeSpec(t),{packageId:w._storePackage,packageVersion:w._storeVersion,widgetKey:w.id});if(w.kind==='clock')Object.assign(nativeSpec(t),{hourFormat:nativeSpec(t).hourFormat??w.hourFormat??'24',showSeconds:nativeSpec(t).showSeconds??w.showSeconds??true,showDate:nativeSpec(t).showDate??w.showDate??true});}
        else if(nativeSpec(t))Object.assign(nativeSpec(t),{packageId:w._storePackage,packageVersion:w._storeVersion});
        if(w.sizes)t._sizes=w.sizes;
        if(w.background)t.bgColor=w.background;
        if(nativeSpec(t)){if(w.textColor)nativeSpec(t).textColor=w.textColor;if(w.accent)nativeSpec(t).accent=w.accent;}
        if((w._studio||w.studio)?.api===2){
          for(const field of (w._studio||w.studio).settings?.fields||[]){
            if(field.key==='background')t.bgColor=field.default;
            else if(['accent','textColor'].includes(field.key)||w._rendererFields.includes(field.key))nativeSpec(t)[field.key]=field.default;
          }
        }
        return t;
      });
      if(draft&&(data.installed||[]).some(p=>p.id==='studio.bambu'&&p.type==='corebar-widget'&&p.source?.startsWith('https://github.com/qlerup/ultrabar-bambu/blob/'))){
        const saved=(data.installed||[]).find(p=>p.id==='studio.bambu');
        const needs=draft.profiles.some(p=>p.homeData.some(w=>{const s=nativeSpec(w);return s?.kind==='bambu'&&['studio.bambu','studio.bambu.widget'].includes(s.packageId)&&(s.companionApp==='dk.ultrabar.bambu'||s.packageId!=='studio.bambu'||s.packageVersion!==saved.version);}));
        if(needs)change(()=>{
          for(const profile of draft.profiles)for(const w of profile.homeData){const s=nativeSpec(w);if(s?.kind==='bambu'&&['studio.bambu','studio.bambu.widget'].includes(s.packageId)){s.packageId='studio.bambu';s.packageVersion=saved.version;if(s.companionApp==='dk.ultrabar.bambu')delete s.companionApp;}}
          draft.background_apps=draft.background_apps.filter(a=>a.id!=='dk.ultrabar.bambu');if(draft.app_settings)delete draft.app_settings['dk.ultrabar.bambu'];
        },false);
      }
      if(draft&&!drag){
        renderLibrary();
        renderCanvas();
        renderProperties();
        refreshPrinterPreviews();
      }
    }catch(error){message('Could not load installed store presets. '+error.message,true);}
  }
  window.addEventListener('studio-store-changed',()=>{loadStorePresets();if(snapshot)loadCatalog();});
  function studioPcTemplate(kind){return {type:'PC_CONTROL',name:kind==='url'?'Open website':'Launch PC app',bgColor:'#242235',icon:'resId://pc_control_def_icon',iconScale:100,_new:true,_pcPending:true,param:{output:10,payload:{action:'studioAction',params:{id:'',kind}}}};}
  function stock(){return [{type:'TIME',name:'Clock',iconScale:100,_new:true},studioPcTemplate('url'),studioPcTemplate('program')];}
  function library(){
    const existing=draft.profiles.flatMap(p=>p.homeData||[]).filter(w=>!nativeSpec(w)&&w.param?.payload?.action!=='studioAction');const seen=new Set();
    const hasBambuWidget=storePresets.some(w=>w._storePackage==='studio.bambu'&&nativeSpec(w)?.kind==='bambu');
    return [...stock(),...storePresets,...apps,...existing].filter(w=>{const spec=nativeSpec(w);const key=w.type==='APPS'?'app:'+w.id:w._storeKey||(spec?.packageId&&spec?.widgetKey?spec.packageId+':'+spec.widgetKey:null)||(w._pcPending&&w._new?'studio-pc:'+w.param.payload.params.kind:w.type==='TIME'?'TIME':w._new?(nativeSpec(w)?nativeSpec(w).kind+':'+(nativeSpec(w).drive||''):w.type):JSON.stringify([w.type,w.id]));if(w.param?.payload?.action==='studioMetric'||seen.has(key)||(hasBambuWidget&&w.type==='APPS'&&w.id==='dk.ultrabar.bambu'))return false;seen.add(key);return true;});
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
  function overBackground(x,y){const r=$('background-drop').getBoundingClientRect();return x>=r.left&&x<=r.right&&y>=r.top&&y<=r.bottom;}
  function dragApp(payload){return payload.widget||(payload.kind==='widget-move'?current().homeData[payload.index]:null);}
  function gridInsertion(widget,small,column){
    const positions=positionsForCurrent(), {splits}=layoutParts(), span=footprintWidth(widget,small);
    if(nextFreeColumn(positions)+span>512)return null;
    const blocks=current().homeData.map(w=>{
      const start=positions[w.id][0];
      return [start,start+footprintWidth(w,isSmall(w))];
    }).concat(splits.map(start=>[start,start+2]));
    // Do not insert through an existing widget or a 2×2 group.
    const boundaries=[...new Set(blocks.flat())].filter(edge=>blocks.every(([start,end])=>edge<=start||edge>=end));
    const at=boundaries.reduce((closest,edge)=>Math.abs(edge-column)<Math.abs(closest-column)?edge:closest,Infinity);
    if(!Number.isFinite(at))return null;
    const shift=start=>start>=at?start+span:start;
    return {insertion:true,cell:[at,0],small,span,splits:splits.map(shift),
      positions:Object.fromEntries(Object.entries(positions).map(([id,[start,row]])=>[id,[shift(start),row]]))};
  }
  function gridDrop(d){
    const widget=dragApp(d.payload);
    const sizes=widgetSizes(widget);
    const currentSmall=d.payload.kind==='widget-move'&&isSmall(widget);
    if(!hasGrid()&&!currentSmall&&sizes.includes('large'))return null;
    const canvas=$('core-canvas'),rect=canvas.getBoundingClientRect(),scale=rect.width/1424;
    const column=((d.x-rect.left)/scale+canvas.scrollLeft-gridMargin+10)/cellPitch;
    const col=Math.max(0,Math.min(511,Math.floor(column)));
    const largeSlot=currentSmall&&sizes.includes('large')&&[...canvas.querySelectorAll('.core-slot:not(.core-slot-split)')].find(slot=>{
      const start=Number(slot.dataset.slotColumn);
      return col>=start&&col<start+2;
    });
    const small=!largeSlot&&(currentSmall||!sizes.includes('large')||(sizes.includes('small')&&splitOverlaps(col,1)));
    const row=small&&(d.y-rect.top)/scale>=140?1:0, cell=[largeSlot?Number(largeSlot.dataset.slotColumn):col,row];
    const positions=proposePosition(widget,small,cell);
    const insertion=!positions&&d.payload.kind==='widget-new'&&gridInsertion(widget,!sizes.includes('large'),column);
    return {...(insertion||{cell,positions,small,span:footprintWidth(widget,small)}),rect,scale};
  }
  function paintWidgetDrag(){
    const d=widgetPointer;if(!d?.active)return;
    $('background-drop').classList.toggle('is-drop-target',overBackground(d.x,d.y)&&dragApp(d.payload)?.type==='APPS');
    const screen=$('core-screen').getBoundingClientRect();
    d.ghost.style.left=(d.x+14)+'px';d.ghost.style.top=(d.y+14)+'px';
    let at=widgetDropIndex(d.x,d.y);
    if(at!==null){
      if(d.x<screen.left+40)$('core-canvas').scrollLeft-=12;
      if(d.x>screen.right-40)$('core-canvas').scrollLeft+=12;
      at=widgetDropIndex(d.x,d.y);
      const grid=gridDrop(d);
      $('core-canvas').classList.toggle('grid-drag',!!grid);
      d.marker.classList.toggle('grid-marker',!!grid&&!grid.insertion);
      d.marker.classList.toggle('invalid-grid-marker',!!grid&&!grid.positions);
      if(grid&&!grid.insertion){
        const {cell:[col,row],rect,scale,span,small}=grid,canvas=$('core-canvas');
        const x=rect.left+(gridMargin+col*cellPitch-canvas.scrollLeft)*scale;
        const left=Math.max(screen.left,x),right=Math.min(screen.right,x+(span*cellPitch-20)*scale);
        d.marker.hidden=right<=left;
        d.marker.style.left=left+'px';d.marker.style.top=(rect.top+(gridMargin+row*rowPitch)*scale)+'px';
        d.marker.style.width=Math.max(0,right-left)+'px';d.marker.style.height=((small?110:240)*scale)+'px';
        d.frame=requestAnimationFrame(paintWidgetDrag);return;
      }
      d.marker.style.width='';
      const cards=[...$('core-canvas').querySelectorAll('.canvas-widget')];
      const x=grid?.insertion?grid.rect.left+(gridMargin+grid.cell[0]*cellPitch-$('core-canvas').scrollLeft-10)*grid.scale:
        cards[at]?.getBoundingClientRect().left??cards.at(-1)?.getBoundingClientRect().right??screen.left+12;
      const height=Math.min(90,screen.height*.42);
      d.marker.hidden=false;d.marker.style.left=Math.max(screen.left+10,Math.min(screen.right-14,x))+'px';
      d.marker.style.top=(screen.top+(screen.height-height)/2)+'px';d.marker.style.height=height+'px';
    }else{d.marker.hidden=true;$('core-canvas').classList.remove('grid-drag');}
    d.frame=requestAnimationFrame(paintWidgetDrag);
  }
  function endWidgetDrag(cancel=false){
    const d=widgetPointer;if(!d)return;widgetPointer=null;
    if(d.node.hasPointerCapture(d.pointerId))d.node.releasePointerCapture(d.pointerId);
    if(!d.active)return;
    cancelAnimationFrame(d.frame);d.ghost.remove();d.marker.remove();d.node.classList.remove('dragging');
    $('background-drop').classList.remove('is-drop-target');
    $('core-canvas').classList.remove('grid-drag');
    const at=widgetDropIndex(d.x,d.y);drag=null;suppressWidgetClickUntil=Date.now()+400;
    if(!cancel&&overBackground(d.x,d.y)){addBackground(dragApp(d.payload));return;}
    if(cancel||at===null){message('Move cancelled.');return;}
    const grid=gridDrop(d);
    if(grid&&!grid.positions){message('Choose an empty position or drop onto a widget that can swap places.',true);return;}
    if(d.payload.kind==='widget-new')addWidget(d.payload.widget,at,grid);
    else if(d.payload.kind==='widget-background'){
      const app=d.payload.widget;
      change(()=>{
        draft.background_apps.splice(d.payload.index,1);backgroundIndex=-1;
        const widget={id:app.id,type:'APPS',name:app.name,iconScale:100};
        current().homeData.splice(at,0,widget);
        if(grid)applyPositions(widget,grid.cell,grid.positions);
        else widgetIndex=at;
      });
    }else if(grid){
      const widget=current().homeData[d.payload.index];
      change(()=>{
        if(grid.small!==isSmall(widget)){
          const {small,positions}=layoutParts();
          storeLayout(current(),grid.small?[...small,widget.id]:small.filter(id=>id!==widget.id),positions);
        }
        applyPositions(widget,grid.cell,grid.positions);
      });
    }else moveWidget(d.payload.index,at);
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
  const builtInCoreApps=new Set(['com.ultrabar.calculator','com.ultrabar.alarmclock','com.aiks.leisuregame','com.aiks.aurorasniper','com.ultrabar.whitenoise','com.stellarring.screensaver','com.flip.screensaver']);
  function libraryGroup(w){
    if(w._storePackage||nativeSpec(w)?.packageId)return 'store';
    if(w.type==='APPS')return builtInCoreApps.has(w.id)?'ultrabar':'installed';
    if(nativeSpec(w)||w.param?.payload?.action==='studioAction')return 'studio';
    return ['CPU','MEMORY','STORAGE','TIME'].includes(w.type)?'ultrabar':'installed';
  }
  async function showLibraryIcon(w,box){
    const packageId=w._storePackage||nativeSpec(w)?.packageId;
    const digest=storeIconByPackage.get(packageId)||storeIconByApp.get(w.id);
    const shortcut=pcWidgetSpec(w);
    const path=digest?'/api/store/icons/'+digest:shortcut?'/api/pc/widget-icons/'+shortcut.kind:w.type==='TIME'?'/api/editor/icons/clock':w.type==='APPS'?'/api/editor/icons/app/'+encodeURIComponent(w.id):null;
    if(!path)return;
    const key=path.startsWith('/api/store/')?path:snapshot.device_id+':'+snapshot.target+':'+path;
    if(Date.now()-(libraryIconFailures.get(key)||0)<30000)return;
    try{
      if(!libraryIconCache.has(key))libraryIconCache.set(key,api(path).then(r=>r.blob()).then(blob=>URL.createObjectURL(blob)).catch(error=>{libraryIconCache.delete(key);throw error;}));
      const url=await libraryIconCache.get(key);if(!box.isConnected)return;
      const img=el('img');img.src=url;img.alt='';img.width=32;img.height=32;img.draggable=false;box.replaceChildren(img);
    }catch(_){libraryIconFailures.set(key,Date.now());/* Keep the package initial while an icon is unavailable. */}
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
    const groups=[['ultrabar','UltraBarX','Built-in Core apps and widgets.'],['studio','Studio','Widgets and PC actions provided by Studio.'],['store','App Store','Widgets and presets installed from the Store.'],['installed','Other apps & widgets on Core','Already on Core. Their original source is not recorded.']];
    for(const [key,title,help] of groups){
      const items=widgets.filter(w=>libraryGroup(w)===key);
      if(query&&!items.length)continue;
      const group=el('details','library-group');group.dataset.group=key;
      group.open=query?true:libraryExpanded[key];if(query)group.dataset.searching='true';
      const summary=el('summary','library-group-heading');summary.append(el('span','',title),el('span','library-count',String(items.length)));
      const content=el('div','library-group-content');content.append(el('p','muted library-group-help',help));
      for(const w of items){const b=el('button','library-item');b.type='button';const icon=el('span','library-icon',(w.name||types[w.type]||w.type||'?').slice(0,1).toUpperCase());b.append(icon,el('span','',w.name||types[w.type]||w.type));b.setAttribute('aria-label',w.name||types[w.type]||w.type);b.title='Drag '+(w.name||w.type)+' onto the Core bar'+(w.type==='APPS'?' or into Background apps.':'.');draggable(b,{kind:'widget-new',widget:w});content.append(b);showLibraryIcon(w,icon);}
      if(!items.length)content.append(el('p','muted','No items available.'));
      group.append(summary,content);container.append(group);
    }
    if(!container.children.length)container.append(el('p','muted','No matching widgets.'));
  }
  function addWidget(template,at=current().homeData.length,target=null){
    backgroundIndex=-1;
    const widget=clone(template),companion=widget._bundledApp,sizes=widgetSizes(template);delete widget._sizes;delete widget._bundledApp;delete widget._storePackage;delete widget._storeKey;delete widget._storeVersion;if(widget._new){widget.id=(widget._native?'studio_native_':'studio_')+crypto.randomUUID().replaceAll('-','');delete widget._new;delete widget._native;}
    if(current().homeData.some(w=>w.id===widget.id)){message('This widget is already on Core. Select its card to edit it.');return;}
    change(()=>{if(widget.type==='APPS')draft.background_apps=draft.background_apps.filter(a=>a.id!==widget.id);if(companion&&!draft.background_apps.some(a=>a.id===companion.id)&&!draft.profiles.some(p=>p.homeData.some(w=>w.type==='APPS'&&w.id===companion.id)))draft.background_apps.push({id:companion.id,name:companion.name,settings:{launch:false}});const layout=layoutParts();
      const previous=hasGrid()?positionsForCurrent():null;
      current().homeData.splice(at,0,widget);
      const small=target?.small||!sizes.includes('large'),selected=small?[...layout.small,widget.id]:layout.small;
      storeLayout(current(),selected,layout.positions,target?.splits??layout.splits);
      if(target)applyPositions(widget,target.cell,target.positions);
      else if(previous)applyPositions(widget,[nextFreeColumn(previous),0],previous);
      else widgetIndex=at;});
  }
  function addBackground(w){
    if(!w||w.type!=='APPS'){message('Background apps supports Core apps. Display widgets belong on the bar.',true);return;}
    if(w.id===coreNotificationsId||/^(android\.|com\.android\.|com\.ultrabar\.)/.test(w.id)){message('System apps cannot be added to Background apps.',true);return;}
    const existing=draft.background_apps.findIndex(a=>a.id===w.id);
    if(existing>=0){backgroundIndex=existing;renderBackground();renderProperties();return;}
    change(()=>{
      for(const profile of draft.profiles){
        profile.homeData=profile.homeData.filter(item=>item.type!=='APPS'||item.id!==w.id);
        removePlacement(profile,w.id);
      }
      const definition=appSettingsDefs.get(w.id);
      let settings={launch:true};
      if(definition){
        settings={};
      }else if(w.id===screenSyncId){
        settings={enabled:true,wakeDelayMs:1000};
      }
      draft.background_apps.push({id:w.id,name:w.name||w.id,settings});
      backgroundIndex=draft.background_apps.length-1;
    });
  }
  function renderBackground(){
    const list=$('background-apps');list.replaceChildren();
    $('background-count').textContent=draft.background_apps.length+1;
    const selectNotifications=()=>{
      backgroundIndex=notificationsIndex;
      renderCanvas();
      renderBackground();
      renderProperties();
    };
    const notifications=button('',selectNotifications,'background-app'+(backgroundIndex===notificationsIndex?' selected':''));
    notifications.dataset.builtin='';
    notifications.setAttribute('aria-pressed',String(backgroundIndex===notificationsIndex));
    notifications.setAttribute('aria-label','Core Notifications background settings');
    notifications.append(el('span','background-app-dot'),el('span','','Core Notifications'),el('small','','Built in'));
    list.append(notifications);
    draft.background_apps.forEach((app,i)=>{const chip=el('button','background-app'+(backgroundIndex===i?' selected':''));chip.type='button';chip.setAttribute('aria-pressed',String(backgroundIndex===i));chip.setAttribute('aria-label',app.name+' background settings');chip.append(el('span','background-app-dot'),el('span','',app.name),el('small','',appSettingsDefs.has(app.id)?'':app.id===pcStandbyId?'Follows Studio':app.id===screenSyncId?((draft.app_settings?.[app.id]?.enabled??app.settings.enabled)===false?'Always on':'Follow Core'):(app.settings.launch===false?'Install only':'Launch on Deploy')));chip.onclick=()=>{backgroundIndex=i;renderCanvas();renderBackground();renderProperties();};draggable(chip,{kind:'widget-background',index:i,widget:{id:app.id,type:'APPS',name:app.name}});list.append(chip);});
  }
  function studioBinding(spec){
    return studioBindings.get(spec.packageId+':'+spec.widgetKey)||[...studioBindings.values()].find(b=>b.packageId===spec.packageId&&(b.kind===spec.kind||b.kindOptions?.includes(spec.kind)));
  }
  function renderPackageSettings(panel,spec,widget){
    const binding=studioBinding(spec);
    if(!binding){panel.append(el('p','muted','Install this widget package to load its settings.'));return;}
    const descriptor=binding.descriptor;
    const update=(key,value)=>change(()=>{spec[key]=value;if(descriptor.sources?.[key]==='pc.drives')delete spec.drives;});
    if(descriptor.connection)packageUI.picker(panel,binding,spec,update);
    if(descriptor.settings){
      if(descriptor.api===2){
        const colors=['background','textColor','accent'];
        const shared=key=>colors.includes(key)||binding.rendererFields.includes(key);
        const values=Object.fromEntries(descriptor.settings.fields.map(f=>[f.key,
          (f.key==='background'?widget.bgColor:shared(f.key)?spec[f.key]:spec.packageSettings?.[f.key])??f.default]));
        window.studioPackageUI.fields(panel,descriptor.settings,values,(key,value)=>{
          if(key==='background')change(()=>widget.bgColor=value);
          else if(shared(key))update(key,value);
          else change(()=>{spec.packageSettings={...spec.packageSettings,[key]:value};});
        },{sources:descriptor.sources,metrics:pcMetrics,prefix:'widget-setting'});
      }else window.studioPackageUI.fields(panel,descriptor.settings,spec,update,{sources:descriptor.sources,metrics:pcMetrics,prefix:'widget-setting'});
    }
    if(descriptor.help)panel.append(el('p','muted',descriptor.help));
  }
  function renderBackgroundProperties(panel){
    if(backgroundIndex===notificationsIndex){
      const soundField=el('label','property-field','Test sound');
      const sound=el('select');
      option(sound,'complete','Print complete');
      option(sound,'error','Print error');
      option(sound,'silent','Silent');
      sound.value=notificationTestSound;
      sound.onchange=()=>{notificationTestSound=sound.value;};
      soundField.append(sound);
      const test=button('Send test notification',()=>operation(async()=>{
        const response=await api('/api/editor/core-notifications/test',{
          method:'POST',body:JSON.stringify({device_id:draft.device_id,sound:notificationTestSound})
        });
        message((await response.json()).message);
      }));
      panel.replaceChildren(
        el('h3','','Core Notifications'),
        el('p','muted','Studio installs the built-in notification service when you deploy. Supported Core apps and widgets use it to show banners.'),
        soundField,test
      );
      return;
    }
    const app=draft.background_apps[backgroundIndex];if(!app)return;
    panel.replaceChildren(el('h3','','Background app settings'),el('span','badge','NO BAR SPACE'),el('h4','',app.name));
    if(appSettingsDefs.has(app.id)){
      renderAppSettings(app.id,panel);
    }else if(app.id===pcStandbyId){
      panel.append(el('p','muted','Deploy connects PC Standby to Studio automatically. Core sleeps when Studio stops answering and wakes when it reconnects.'));
    }else if(app.id===screenSyncId){
      const wrap=el('label','property-field','Vivo screens'),select=el('select');select.id='background-sync-mode';option(select,'follow','Follow Core');option(select,'always','Always on');select.value=app.settings.enabled===false?'always':'follow';select.onchange=()=>change(()=>app.settings.enabled=select.value==='follow');wrap.append(select);panel.append(wrap);
      const delay=field('Wake delay (ms)',app.settings.wakeDelayMs??1000,v=>{const n=Number(v);if(Number.isInteger(n)&&n>=0&&n<=3000&&n%250===0)change(()=>app.settings.wakeDelayMs=n);else{message('Use 0–3000 ms in steps of 250.',true);renderProperties();}},'number');const input=delay.querySelector('input');input.id='background-wake-delay';input.min='0';input.max='3000';input.step='250';panel.append(delay,el('p','muted','VivoCubes follow Core screen power. Wake delay applies when Core turns on. Deploy installs the app, sends these settings and starts syncing in the background.'));
    }else{
      const wrap=el('label','property-field','Launch after Deploy'),input=el('input');input.type='checkbox';input.id='background-launch';input.checked=app.settings.launch!==false;input.onchange=()=>change(()=>app.settings.launch=input.checked);wrap.append(input);panel.append(wrap,el('p','muted','Installed without a card on Core. Background behavior depends on the app; apps with their own background service can keep running.'));
    }
    if(draft.app_settings?.[app.id])panel.append(button('Forget draft app settings',()=>change(()=>delete draft.app_settings[app.id]),'danger-quiet'));
    panel.append(button('Remove background app',()=>change(()=>{draft.background_apps.splice(backgroundIndex,1);backgroundIndex=-1;}),'danger-quiet'),el('p','muted','Changes apply on Deploy. Removing an app here stops its background operation on the next Deploy; the Android app remains installed.'));
  }
  function renderAppSettings(packageId,panel){
    const definition=appSettingsDefs.get(packageId);if(!definition)return;
    const section=el('section','app-settings-form');section.append(el('h4','',definition.name+' settings'));
    const defaults=Object.fromEntries(definition.schema.fields.map(f=>[f.key,f.default]));
    const legacy=draft.background_apps.find(a=>a.id===packageId)?.settings;
    if(legacy)for(const key of Object.keys(defaults))if(key!=='launch'&&Object.hasOwn(legacy,key))defaults[key]=legacy[key];
    const values={...defaults,...draft.app_settings?.[packageId]};
    section.append(el('p','muted',draft.app_settings?.[packageId]?'Saved in this draft. Settings apply to this app across all profiles after Deploy.':'Defaults are shown. Read from Core to load the app’s current settings before editing.'));
    window.studioPackageUI.fields(section,definition.schema,values,(key,value)=>{
      change(()=>{draft.app_settings??={};draft.app_settings[packageId]={...values,[key]:value};});
    },{prefix:'app-setting'});
    const read=button('Read settings from Core',()=>operation(async()=>{
      const device=draft.device_id;
      const data=await(await api('/api/editor/app-settings/read',{method:'POST',body:JSON.stringify({device_id:device,package:packageId})})).json();
      if(draft?.device_id!==device)throw new Error('The selected Core changed. Read settings again.');
      checkpoint();draft.app_settings??={};draft.app_settings[packageId]=data.values;renderEditor();message('Current app settings loaded into your draft.');
    }));section.append(read,el('p','muted','Studio waits for the app to confirm applied settings. Keep the app installed and Core connected.'));
    panel.append(section);
  }
  function renderAppSettingsRecovery(){
    let box=$('draft-app-settings');if(!box){box=el('div');box.id='draft-app-settings';document.querySelector('.draft-tools').append(box);}
    box.replaceChildren();for(const key of Object.keys(draft.app_settings||{}))box.append(button('Forget draft settings: '+(appSettingsDefs.get(key)?.name||key),()=>change(()=>delete draft.app_settings[key]),'danger-quiet'));
    for(const serial of Object.keys(draft.vivo_screens||{}))box.append(button('Forget draft Vivo picture: '+serial.slice(-6),()=>change(()=>delete draft.vivo_screens[serial]),'danger-quiet'));
  }
  function moveWidget(from,to){backgroundIndex=-1;if(from===to)return;change(()=>{const list=current().homeData;const [w]=list.splice(from,1);list.splice(to>from?to-1:to,0,w);widgetIndex=list.indexOf(w);});}
  function bambuPreview(spec){
    const printer=printerMetrics[spec.printerId],live=printer?.fresh===true;
    const status=live?({RUNNING:'Printing',PAUSE:'Paused',PREPARE:'Preparing',FINISH:'Complete',FAILED:'Stopped',IDLE:'Ready'}[printer.gcode_state]||'Connected'):
      !spec.printerId?'Choose a printer':printer?.connection==='Connected'?'Waiting for readings':printer?.connection||'Waiting for printer';
    const progress=live&&Number.isFinite(printer.mc_percent)?Math.max(0,Math.min(100,Math.round(printer.mc_percent))):null;
    const minutes=live&&Number.isFinite(printer.mc_remaining_time)&&printer.mc_remaining_time>=0?Math.floor(printer.mc_remaining_time):null;
    const values={
      progress:progress===null?'—':progress+'%',state:status,
      remaining:minutes===null?'—':Math.floor(minutes/60)+'h '+minutes%60+'m',
      temperature:live&&Number.isFinite(printer.nozzle_temper)?Math.round(printer.nozzle_temper)+'°C':'—',
      job:live?(printer.subtask_name||'No active job'):'',
      layers:live&&Number.isFinite(printer.layer_num)?'Layer '+printer.layer_num+' / '+(printer.total_layer_num??'—'):'',
      none:''
    };
    return {live,progress,status,name:printer?.name,values,primary:values[spec.primary||'progress'],secondary:live?values[spec.secondary||'remaining']:''};
  }
  function showBambuUnfolded(widget){
    const spec=nativeSpec(widget),dialog=el('dialog','studio-connections-dialog bambu-preview-dialog');
    dialog.setAttribute('aria-labelledby','bambu-unfolded-title');
    dialog.style.setProperty('--widget-accent',spec.accent);
    const heading=el('div','studio-connections-heading'),title=el('h3','','');
    title.id='bambu-unfolded-title';
    heading.append(title,button('Close',()=>dialog.close()));
    const content=el('div','bambu-unfolded-content');
    dialog.append(heading,content);
    renderBambuUnfolded=()=>{
      const installed=studioBinding(spec);
      if(installed?.descriptor.layout?.expanded){
        title.textContent=widget.name;
        content.classList.add('package-expanded-preview');
        window.widgetScene.preview(content,widget.name,{...spec,background:widget.bgColor},'expanded',api,installed.version);
        return;
      }
      const preview=bambuPreview(spec),{live,values}=preview;
      const presentation=packageUI.presentation(studioBinding(spec),spec);
      const printer=live?printerMetrics[spec.printerId]:{};
      title.textContent=preview.name||presentation.connectionName||widget.name;
      const summary=el('section','bambu-unfolded-summary');
      summary.append(el('span','native-source',preview.status),el('strong','bambu-unfolded-progress',values.progress));
      if(live&&spec.showJob!==false)summary.append(el('span','bambu-unfolded-job',values.job));
      const track=el('progress','bambu-unfolded-track');
      track.max=100;track.value=preview.progress??0;track.setAttribute('aria-label','Print progress');
      summary.append(track);
      if(live){
        const details=[spec.showRemaining!==false&&values.remaining!=='—'?values.remaining+' left':'',spec.showLayers!==false?values.layers:''].filter(Boolean);
        if(details.length)summary.append(el('span','muted',details.join(' · ')));
      }
      content.replaceChildren(summary);
      if(spec.showTemperatures===false)return;
      const reported=Array.isArray(printer.nozzle_readings)?printer.nozzle_readings:[];
      const tools=new Map(reported.map(reading=>[reading.tool,reading]));
      for(const key of Object.keys(presentation.labels||{})){
        if(/^nozzle[.][0-9]+$/.test(key)){
          const tool=Number(key.slice(6));
          if(!tools.has(tool))tools.set(tool,{tool});
        }
      }
      const readings=[...tools.values()].sort((a,b)=>a.tool-b.tool);
      const temperatures=el('dl','bambu-unfolded-temperatures');
      const grid=presentation.minTemperatureRows>1;
      if(grid){
        const columns=Math.ceil(Math.max(1,readings.length)/presentation.minTemperatureRows);
        temperatures.style.gridTemplateColumns='repeat('+columns+',minmax(0,1fr))';
        temperatures.classList.add('nozzle-grid');
        if(presentation.nozzleGrid){
          const {materialSize,swatchSize,verticalInset}=presentation.nozzleGrid;
          temperatures.style.setProperty('--material-size',materialSize+'px');
          temperatures.style.setProperty('--swatch-size',swatchSize+'px');
          temperatures.style.setProperty('--cell-padding',(14-verticalInset)+'px');
        }
      }
      const temperature=value=>Number.isFinite(value)?Math.round(value)+'°C':'—';
      function addTemperature(label,value,parent=temperatures){
        const tile=el('div','bambu-temperature');
        tile.append(el('dt','',label),el('dd','',temperature(value)));
        parent.append(tile);
      }
      for(const {tool,temperature:value,material,filamentProfile,color} of readings){
        addTemperature(presentation.labels?.['nozzle.'+tool]||'NOZZLE T'+tool,value);
        if(grid){
          const footer=el('dd','nozzle-material',material||presentation.labels?.['filament.'+filamentProfile]||'—');
          if(/^#[a-f0-9]{6}$/i.test(color||'')){
            const chip=el('span','nozzle-swatch');chip.style.backgroundColor=color;chip.title=color;footer.append(chip);
          }
          temperatures.lastElementChild.append(footer);
        }
      }
      if(!readings.length)addTemperature('NOZZLE',printer.nozzle_temper);
      const sideFields=presentation.nozzleGrid?.sideTemperatures;
      if(grid && sideFields?.length){
        const group=el('div','bambu-temperature-panel');
        const side=el('dl','bambu-side-temperatures');
        for(const key of sideFields)addTemperature(presentation.labels?.[key]||key,printer[key],side);
        group.append(temperatures,side);
        content.append(group);
        return;
      }
      if(grid)summary.append(el('span','muted','Bed '+temperature(printer.bed_temper)+'    Chamber '+temperature(printer.chamber_temper)));
      else{
        addTemperature('BED',printer.bed_temper);
        addTemperature('CHAMBER',printer.chamber_temper);
      }
      content.append(temperatures);
    };
    const panelTimer=studioBinding(spec)?.descriptor.layout?.expanded ? setInterval(()=>renderBambuUnfolded?.(),3000) : null;
    dialog.addEventListener('close',()=>{clearInterval(panelTimer);renderBambuUnfolded=null;dialog.remove();},{once:true});
    renderBambuUnfolded();
    document.body.append(dialog);dialog.showModal();refreshPrinterPreviews();
  }
  function splitFlapPreview(w, card, spec, face){
    const small=card.classList.contains('small-widget'), now=new Date(), epoch=Math.floor(now.getTime()/1000);
    const twelve=spec.hourFormat==='12', seconds=!small && spec.showSeconds!==false;
    const pairs=[twelve?(now.getHours()%12||12):now.getHours(),now.getMinutes()];
    if(seconds)pairs.push(now.getSeconds());
    const digits=pairs.map(n=>String(n).padStart(2,'0'));
    const previous=Number(card.dataset.flapTick)===epoch-1?card.dataset.flapDigits?.split(','):[];
    card.dataset.flapDigits=digits.join(',');card.dataset.flapTick=epoch;
    const board=el('span','flap-board'), header=el('span','flap-header');
    header.append(el('span','flap-name',w.name||'Clock'));
    if(twelve){
      const parts=new Intl.DateTimeFormat(undefined,{hour:'numeric',hour12:true}).formatToParts(now);
      header.append(el('span','flap-period',parts.find(p=>p.type==='dayPeriod')?.value||''));
    }
    const tiles=el('span','flap-tiles');
    tiles.setAttribute('aria-label',digits.join(':'));
    function half(number,position){
      const layer=el('span','flap-half '+position);
      layer.setAttribute('aria-hidden','true');layer.append(el('span','',number));return layer;
    }
    digits.forEach((value,i)=>{
      const tile=el('span','flap-tile'+(i===2?' flap-seconds':''));
      tile.append(half(value,'upper'),half(value,'lower'));
      const old=previous?.[i];
      if(old && old!==value && face.durationMs){
        tile.append(half(old,'lower old'),half(old,'upper falling'),half(value,'lower arriving'));
      }
      tiles.append(tile);
    });
    board.style.setProperty('--plate',spec.packageSettings?.[face.plateColorSetting]??face.plateColor);
    board.style.setProperty('--flip-half',face.durationMs/2+'ms');
    board.append(header,tiles);
    if(spec.showDate!==false)board.append(el('span','flap-date',now.toLocaleDateString(undefined,small?
      {day:'numeric',month:'short'}:{weekday:'short',day:'numeric',month:'short',year:'numeric'})));
    card.replaceChildren(board);
  }
  function renderNativePreview(w,card){
    const spec=nativeSpec(w);card.classList.add('native-preview');card.style.backgroundColor=w.bgColor||'#192325';card.style.color=spec.textColor||'#eef6f2';card.style.setProperty('--widget-accent',spec.accent);
    const installed=studioBinding(spec);
    if(installed?.descriptor.layout){
      window.widgetScene.preview(card,w.name,{...spec,background:w.bgColor},isSmall(w)?'small':'large',api,installed.version);
      return;
    }
    const presentation=packageUI.presentation(studioBinding(spec),spec);
    if(spec.kind==='clock' && presentation.splitFlap){
      splitFlapPreview(w,card,spec,presentation.splitFlap);
      return;
    }
    const printer=spec.kind==='bambu'?bambuPreview(spec):null;
    const printerName=printer?.name||presentation.connectionName;
    card.replaceChildren(el('strong','native-title',printerName||presentation.labels?.title||w.name||'Studio'));
    if(!card.classList.contains('small-widget')||spec.kind!=='bambu'){
      if(spec.kind==='bambu'&&presentation.imageUrl){
        const image=el('img','package-artwork');image.src=presentation.imageUrl;image.alt='';image.draggable=false;card.append(image);
      }else window.studioPackageUI.artwork(card,presentation.artwork);
    }
    const bar=value=>{const track=el('span','native-track'),fill=el('span','');fill.style.width=Math.max(0,Math.min(100,value||0))+'%';track.append(fill);return track;};
    const number=value=>value==null?'--':Number(value).toFixed(1);
    if(card.classList.contains('small-widget')){
      const now=new Date(),drives=pcMetrics.disks||[];
      const drive=drives.find(d=>spec.drives?.includes(d.name)||spec.drive==='all'||spec.drive===d.name);
      const usage=spec.kind==='disk'?drive?.percent:spec.kind==='gpu'?pcMetrics.gpu?.usage:pcMetrics[spec.kind];
      const reading=spec.kind==='clock'?now.toLocaleTimeString([], {hour:'2-digit',minute:'2-digit',hour12:spec.hourFormat==='12'}):
        printer?(printer.live?printer.primary:'—'):
        usage==null?'--':Math.round(usage)+'%';
      card.append(el('span','compact-reading',reading));
      if(printer)card.append(el('span','compact-detail',printer.status),bar(printer.progress));
      else if(usage!=null){
        const detail=spec.kind==='disk'?drive.name.slice(0,2):spec.kind==='memory'?'RAM':spec.kind.toUpperCase();
        card.append(el('span','compact-detail',detail),bar(usage));
      }
      else if(spec.kind==='clock'&&spec.showDate!==false)card.append(el('span','compact-detail',now.toLocaleDateString([], {day:'numeric',month:'short'})));
      return;
    }
    if(printer){
      const primary=spec.primary||'progress';
      const labels={state:'PRINTER STATUS',remaining:'TIME REMAINING',temperature:'ACTIVE NOZZLE'};
      card.classList.add('bambu-preview');
      const unfold=el('span','bambu-unfold','Tap to unfold'),arrow=el('span','bambu-unfold-arrow','↗');
      arrow.setAttribute('aria-hidden','true');unfold.append(arrow);
      card.append(el('span','native-value'+(primary==='progress'?' bambu-percent':''),printer.live?printer.primary:'—'),
        el('span','native-source',printer.live?labels[primary]||printer.status:printer.status),el('span','native-detail',printer.secondary),
        bar(printer.progress),unfold);
    }else if(spec.kind==='clock'){
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
  function pcWidgetSpec(w){
    if(w.type!=='PC_CONTROL'||w.param?.payload?.action!=='studioAction')return null;
    const action=pcActions.find(a=>a.id===w.param.payload.params?.id);
    const kind=w.param.payload.params?.kind||action?.kind;
    return ['url','program'].includes(kind)?{kind,action}:null;
  }
  function widgetPictureHash(icon){return typeof icon==='string'&&icon.startsWith(picturePrefix)&&/^[a-f0-9]{64}\.png$/.test(icon.slice(picturePrefix.length))?icon.slice(picturePrefix.length,-4):null;}
  function pcWidgetForm(w){
    const spec=pcWidgetSpec(w);let state=pcWidgetForms.get(w.id);
    if(!state){state={target:spec.action?.target||'',imageHash:widgetPictureHash(w.icon),imageSource:w.param.payload.params?.imageSource||null,touched:false,actionId:spec.action?.id||null,error:'',busy:false};pcWidgetForms.set(w.id,state);}
    if(spec.action&&!state.touched&&state.actionId!==spec.action.id){state.target=spec.action.target;state.actionId=spec.action.id;}
    return state;
  }
  async function showShortcutPicture(path,box){
    try{
      if(!libraryIconCache.has(path))libraryIconCache.set(path,api(path).then(r=>r.blob()).then(b=>URL.createObjectURL(b)).catch(error=>{libraryIconCache.delete(path);throw error;}));
      const url=await libraryIconCache.get(path);if(!box.isConnected)return;
      const img=el('img');img.src=url;img.alt='';img.draggable=false;box.replaceChildren(img);
    }catch(_){/* Keep the shortcut initial if its picture is unavailable. */}
  }
  function renderPcShortcutPreview(w,card){
    const spec=pcWidgetSpec(w),state=pcWidgetForm(w);
    card.classList.add('pc-shortcut-preview');
    const picture=el('span','pc-shortcut-image'+(state.imageSource==='custom'?' custom-picture':''),spec.kind==='url'?'W':'A');
    picture.style.setProperty('--shortcut-scale',(w.iconScale??100)/100);
    showShortcutPicture(state.imageHash?'/api/pc/images/'+state.imageHash:'/api/pc/widget-icons/'+spec.kind,picture);
    const target=state.target||spec.action?.target||'';
    const detail=target?(spec.kind==='url'?target.replace(/^https?:\/\//,''):target.split(/[\\/]/).pop()):(spec.kind==='url'?'Set a website URL':'Choose a PC program');
    card.replaceChildren(el('span','pc-shortcut-kind',spec.kind==='url'?'WEBSITE':'PC APP'),picture,el('strong','stock-title',w.name),el('small','pc-shortcut-detail',detail));
  }
  async function shortcutImage(state,kind){
    if(state.imageSource==='custom'&&state.imageHash)return {sha256:state.imageHash,icon:picturePrefix+state.imageHash+'.png',source:'custom'};
    const path=kind==='program'?'/api/pc/program-icon':'/api/pc/default-image';
    const body=kind==='program'?{target:state.target.trim()}:{kind};
    const data=await(await api(path,{method:'POST',body:JSON.stringify(body)})).json();
    state.imageHash=data.image.sha256;state.imageSource=data.image.source;return data.image;
  }
  function renderPcWidgetSettings(w,panel){
    const spec=pcWidgetSpec(w),state=pcWidgetForm(w),form=el('form','pc-widget-form');form.id='pc-widget-form';
    form.append(el('h4','',spec.kind==='url'?'Website settings':'PC app settings'));
    const label=el('label','property-field',spec.kind==='url'?'Website URL':'Program on this PC'),target=el('input');target.id='pc-widget-target';target.type=spec.kind==='url'?'url':'text';target.required=true;target.maxLength=2048;target.value=state.target;target.placeholder=spec.kind==='url'?'https://example.com':'Choose an .exe program';
    target.oninput=()=>{state.target=target.value;state.touched=true;};label.append(target);form.append(label);
    if(spec.kind==='program')form.append(button('Browse programs',async()=>{
      if(state.busy)return;state.busy=true;state.error='';
      try{const data=await(await api('/api/pc/browse',{method:'POST',body:'{}'})).json();if(data.path){state.target=data.path;state.touched=true;if(state.imageSource!=='custom'){await shortcutImage(state,'program');}}}
      catch(error){state.error=error.message;}finally{state.busy=false;if(current()?.homeData[widgetIndex]?.id===w.id){renderCanvas();renderProperties();}}
    }));
    const preview=el('div','pc-picture-preview',spec.kind==='url'?'W':'A');showShortcutPicture(state.imageHash?'/api/pc/images/'+state.imageHash:'/api/pc/widget-icons/'+spec.kind,preview);form.append(preview);
    const uploadLabel=el('label','property-field','Widget picture'),upload=el('input');upload.id='pc-widget-picture';upload.type='file';upload.accept='image/png,image/jpeg,image/webp';upload.disabled=state.busy;
    upload.onchange=async()=>{
      const file=upload.files[0];if(!file||state.busy)return;
      if(file.size>2*1024*1024){state.error='Choose a PNG, JPG or WebP picture up to 2 MB.';renderProperties();return;}
      state.busy=true;state.error='';
      try{const body=new FormData();body.append('image',file);const data=await(await api('/api/pc/images',{method:'POST',body})).json();state.imageHash=data.image.sha256;state.imageSource='custom';state.touched=true;}
      catch(error){state.error=error.message;}finally{state.busy=false;if(current()?.homeData[widgetIndex]?.id===w.id){renderCanvas();renderProperties();}}
    };
    uploadLabel.append(upload);form.append(uploadLabel,el('p','muted','PNG, JPG or WebP, up to 2 MB. Apply settings to keep your changes.'));
    form.append(button(spec.kind==='program'?'Use program icon':'Use default picture',async()=>{
      if(state.busy)return;state.busy=true;state.error='';state.imageSource=null;state.imageHash=null;
      try{await shortcutImage(state,spec.kind);}catch(error){state.error=error.message;}
      finally{state.busy=false;if(current()?.homeData[widgetIndex]?.id===w.id){renderCanvas();renderProperties();}}
    }));
    const source=state.imageSource==='custom'?'Your uploaded picture':state.imageSource==='program'?'Automatic program icon':state.imageSource==='default'&&spec.kind==='program'?'Default picture (program icon unavailable)':spec.kind==='program'?'The program icon is selected automatically.':'Studio website picture';
    form.append(el('p','muted pc-picture-source',source));
    const error=el('p','error',state.error);error.id='pc-widget-error';error.setAttribute('role','alert');form.append(error);
    const submit=el('button','primary',state.busy?'Loading picture...':'Apply settings');submit.id='pc-widget-apply';submit.type='submit';submit.disabled=state.busy||actionSaving;form.append(submit,el('p','muted','Opens on your PC. Keep Studio running. Changes activate after Deploy.'));
    form.onsubmit=async event=>{
      event.preventDefault();if(state.busy||actionSaving||working)return;
      state.error='';state.target=target.value;const context=[draft.device_id,current().id,w.id].join('|');actionSaving=true;busy=true;updateControls();submit.disabled=true;
      try{
        const image=await shortcutImage(state,spec.kind);
        const data=await(await api('/api/pc/actions',{method:'POST',body:JSON.stringify({name:w.name||'PC shortcut',kind:spec.kind,target:state.target.trim(),device_id:draft.device_id})})).json();
        if(context!==[draft?.device_id,current()?.id,current()?.homeData[widgetIndex]?.id].join('|'))throw new Error('The selected widget changed. Select it and apply the settings again.');
        pcActions=data.actions;pcWidgetForms.delete(w.id);
        change(()=>{w.param={output:10,payload:{action:'studioAction',params:{id:data.action.id,kind:spec.kind,imageSource:image.source}}};w.icon=image.icon;delete w._pcPending;});
        message('Widget settings applied to your draft. Save, then Deploy to Core when ready.');
      }catch(error){state.error=error.message;}
      finally{actionSaving=false;busy=false;updateControls();if(current()?.homeData[widgetIndex]?.id===w.id)renderProperties();}
    };
    panel.append(form);
  }
  function renderStockPreview(w,card){
    card.classList.add('stock-preview');
    if(pcWidgetSpec(w)){renderPcShortcutPreview(w,card);return;}
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
  function chooseSlotSize(column,split){
    if(working||actionSaving)return;
    const dialog=el('dialog','core-slot-dialog');
    const title=el('h3','','Slot layout');title.id='core-slot-dialog-title';
    dialog.setAttribute('aria-labelledby',title.id);
    const options=el('div','core-slot-options');
    const update=next=>{
      dialog.close();
      if(next===split)return;
      change(()=>{
        const {small,positions,splits}=layoutParts();
        const updated=next?[...splits,column].sort((a,b)=>a-b):splits.filter(value=>value!==column);
        storeLayout(current(),small,positions,updated);
      });
      $('core-canvas').querySelector(`[data-slot-column="${column}"] button`)?.focus({preventScroll:true});
    };
    for(const [divided,label] of [[false,'One large slot'],[true,'2×2 grid']]){
      const option=button('',()=>update(divided),'core-slot-option');
      option.setAttribute('aria-pressed',String(divided===split));
      option.autofocus=divided===split;
      const screen=el('span','core-slot-preview');screen.setAttribute('aria-hidden','true');
      const layout=el('span','core-slot-preview-layout'+(divided?' is-split':''));
      for(let i=0;i<(divided?4:1);i++)layout.append(el('span','core-slot-preview-widget'));
      screen.append(el('span','core-slot-preview-neighbor'),layout);
      option.append(screen,el('span','core-slot-option-label',label));options.append(option);
    }
    dialog.append(title,options,button('Cancel',()=>dialog.close(),'core-slot-cancel'));
    dialog.addEventListener('close',()=>dialog.remove(),{once:true});
    document.body.append(dialog);dialog.showModal();
  }
  function renderEmptySlots(canvas,positions){
    const occupied=new Set();
    const key=(column,row)=>column*2+row;
    for(const widget of current().homeData){
      const [column,row]=positions[widget.id],small=isSmall(widget);
      for(let offset=0;offset<footprintWidth(widget,small);offset++){
        occupied.add(key(column+offset,row));
        if(!small)occupied.add(key(column+offset,1));
      }
    }
    const {splits}=layoutParts(),end=Math.min(512,Math.max(10,nextFreeColumn(positions)+2));
    let lastSlotEnd=0;
    function addSlot(column,split){
      const slot=el('div',split?'core-slot core-slot-split':'core-slot');
      slot.dataset.slotColumn=column;
      slot.style.left=gridMargin+column*cellPitch+'px';
      let empty=0;
      for(let offset=0;offset<2;offset++)for(let row=0;row<2;row++){
        if(occupied.has(key(column+offset,row)))continue;
        empty++;
        if(split){
          const cell=el('span','core-slot-cell');
          cell.style.left=offset*cellPitch+'px';cell.style.top=row*rowPitch+'px';
          slot.append(cell);
        }
      }
      if(empty===4){
        const trigger=button(split?'⋯':'+',()=>chooseSlotSize(column,split),'core-slot-trigger');
        trigger.setAttribute('aria-label',split?'Change empty 2×2 grid':'Choose layout for empty slot');
        trigger.setAttribute('aria-haspopup','dialog');
        slot.append(trigger);
      }
      if(empty){
        canvas.append(slot);
        lastSlotEnd=Math.max(lastSlotEnd,column+2);
      }
    }
    for(const column of splits)addSlot(column,true);
    for(let column=0;column+1<end;column++){
      if(splitOverlaps(column,2)||[0,1,2,3].some(offset=>occupied.has(key(column,0)+offset)))continue;
      addSlot(column,false);column++;
    }
    // Absolutely positioned slots do not contribute trailing padding to the scroll area.
    canvas.style.setProperty('--slot-right',gridMargin+lastSlotEnd*cellPitch+'px');
  }
  function renderCanvas(){
    const canvas=$('core-canvas'),position=canvas.scrollLeft;canvas.replaceChildren();
    const grid=hasGrid(),positions=positionsForCurrent();
    canvas.classList.toggle('mixed-widgets',grid);
    if(grid)canvas.style.setProperty('--layout-right',gridMargin+nextFreeColumn(positions)*cellPitch+'px');
    else canvas.style.removeProperty('--layout-right');
    current().homeData.forEach((w,i)=>{const card=el('button','canvas-widget'+(backgroundIndex===-1&&i===widgetIndex?' selected':''));card.setAttribute('aria-pressed',backgroundIndex===-1&&i===widgetIndex);card.setAttribute('aria-label',w.name||types[w.type]||w.type);card.append(el('span','canvas-glyph',glyphs[w.type]||'◇'),el('strong','',w.name||types[w.type]||w.type),el('small','',nativeSpec(w)?'Studio '+nativeSpec(w).kind:w.type==='PC_CONTROL'?'PC action':w.type));if(w.bgColor)card.style.backgroundColor=w.bgColor;if(isSmall(w))card.classList.add('small-widget');if(grid){const [col,row]=positions[w.id];card.style.left=gridMargin+col*cellPitch+'px';card.style.top=gridMargin+row*rowPitch+'px';}if(nativeSpec(w))renderNativePreview(w,card);
      card.onclick=event=>{
        if(event.target.closest('.bambu-unfold') || (event.target.closest('.package-scene') && (nativeSpec(w)?.kind==='bambu'||studioBinding(nativeSpec(w)||{})?.descriptor.layout?.expanded) && event.offsetY>=card.clientHeight*.78)){showBambuUnfolded(w);return;}
        backgroundIndex=-1;widgetIndex=i;renderCanvas();renderBackground();renderProperties();
      };
      draggable(card,{kind:'widget-move',index:i});dropzone(card,data=>{if(data.kind==='widget-new')addWidget(data.widget,i);if(data.kind==='widget-move')moveWidget(data.index,i);});canvas.append(card);
    });
    [...canvas.children].forEach((card,i)=>{if(!nativeSpec(current().homeData[i]))renderStockPreview(current().homeData[i],card);});
    renderEmptySlots(canvas,positions);
    canvas.scrollLeft=position;requestAnimationFrame(syncCoreScroll);
  }
  dropzone($('core-canvas'),data=>{if(data.kind==='widget-new')addWidget(data.widget);if(data.kind==='widget-move')moveWidget(data.index,current().homeData.length);});
  function field(label,value,onchange,type='text'){const wrap=el('label','property-field',label),input=el('input');input.type=type;input.value=value;input.onchange=()=>onchange(input.value);wrap.append(input);return wrap;}
  function button(text,fn,cls=''){const b=el('button',cls,text);b.type='button';b.onclick=fn;return b;}
  function renderProperties(){
    if(backgroundIndex!==-1){renderBackgroundProperties($('widget-properties'));return;}
    const panel=$('widget-properties');panel.replaceChildren(el('h3','','Widget settings'));const w=current().homeData[widgetIndex];if(!w){panel.append(el('p','muted','Select a card to edit it.'));return;}
    const spec=nativeSpec(w),shortcut=pcWidgetSpec(w);
    const packagePanel=spec&&studioBinding(spec)?.descriptor.api===2;
    panel.append(el('span','badge',spec?'Studio widget':shortcut?(shortcut.kind==='url'?'Website':'PC app'):w.type),field('Display name',w.name||'',v=>change(()=>w.name=v)));
    if(!packagePanel)panel.append(field('Background color',/^#[a-f0-9]{6}$/i.test(w.bgColor)?w.bgColor:(spec?'#192325':'#202a2b'),v=>change(()=>w.bgColor=v),'color'));
    if(spec){
      if(!packagePanel)panel.append(field('Text color',spec.textColor||'#eef6f2',v=>change(()=>spec.textColor=v),'color'),field('Accent color',spec.accent,v=>change(()=>spec.accent=v),'color'));
      if(spec.packageId)panel.append(el('p','muted','Store package: '+spec.packageId+' / '+spec.packageVersion));
      renderPackageSettings(panel,spec,w);
      if(spec.kind==='bambu'||studioBinding(spec)?.descriptor.layout?.expanded){
        const unfold=button('Preview unfolded widget',()=>showBambuUnfolded(w));
        unfold.setAttribute('aria-haspopup','dialog');panel.append(unfold);
      }
      panel.append(el('p','muted',spec.kind==='bambu'?'The preview shows live readings when the selected printer is connected. Save and Deploy to apply this widget to Core.':'Preview shows sample data. Save and Deploy to show this widget on Core. Keep Studio running for live PC data.'));
    }else panel.append(field('Icon size (%)',w.iconScale??100,v=>{const n=Number(v);if(Number.isInteger(n)&&n>=0&&n<=200)change(()=>w.iconScale=n);else message('Icon size must be 0-200.',true);},'number'));
    if(shortcut)renderPcWidgetSettings(w,panel);
    if(w.type==='APPS')renderAppSettings(w.id,panel);
    if(w.type==='APPS'&&draft.app_settings?.[w.id])panel.append(button('Forget draft app settings',()=>change(()=>delete draft.app_settings[w.id]),'danger-quiet'));
    panel.append(button('Remove from Core',()=>change(()=>{removePlacement(current(),w.id);current().homeData.splice(widgetIndex,1);widgetIndex=Math.max(0,widgetIndex-1);}), 'danger-quiet'));
    if(w.type==='PC_CONTROL'&&!nativeSpec(w)&&!shortcut)panel.append(el('p','muted','PC actions require Studio or their original PC software to be connected.'));
    if(['CPU','MEMORY','STORAGE'].includes(w.type))panel.append(el('p','muted',w.type==='STORAGE'?'Shows combined usage of fixed PC drives. Individual drives appear under PC connection.':'Reads actual PC measurements while Studio is connected.'));
  }
  function modules(){if(!current())return [];const map=new Map((snapshot?.hardware?.devices||[]).filter(d=>['DOT_KEY','VIVO_CUBE','KNOB_KEY','SENSE_CUBE'].includes(d.type)).map(d=>[d.serial,{serialNo:d.serial,productId:d.type}]));for(const m of current().module)map.set(m.serialNo,m);return [...map.values()];}
  function renderActionDevices(){
    if(!draft)return;
    const strip=$('action-devices'),focused=strip.contains(document.activeElement)?document.activeElement.dataset.layoutKey:null;
    const live=new Map((snapshot.hardware?.devices||[]).map(d=>[d.serial,d]));
    const cards=new Map();
    const core=createHardwareUnit();core.title='Edit CoreBAR screen layout';core.onclick=()=>showMode('layout');cards.set('core',core);
    for(const m of modules()){
      const device=live.get(m.serialNo)||{serial:m.serialNo,type:m.productId,name:names[m.productId]||m.productId,online:null};
      const card=createHardwareUnit(device),selected=m.serialNo===moduleSerial;
      card.classList.toggle('action-device-selected',selected);card.setAttribute('aria-pressed',String(selected));
      card.setAttribute('aria-label',`${names[m.productId]||m.productId} / ${m.serialNo.slice(-6)}`);
      card.title=`Configure ${names[m.productId]||m.productId} / ${m.serialNo}`;
      card.append(el('span','action-device-serial',m.serialNo.slice(-6)));
      card.onclick=()=>{if(working||actionSaving)return;moduleSerial=m.serialNo;inputKey='';resetActionComposer();renderModules();};
      cards.set(m.serialNo,card);
    }
    const order=[...new Set([...(snapshot.layout_order||[]),...cards.keys()])];
    strip.replaceChildren(...order.filter(key=>cards.has(key)).map(key=>cards.get(key)));
    centerHardware(strip);
    if(focused)[...strip.children].find(card=>card.dataset.layoutKey===focused)?.focus({preventScroll:true});
  }
  window.addEventListener('studio-hardware-changed',()=>{if(mode==='actions'&&!$('editor-content').hidden)renderActionDevices();});
  new ResizeObserver(()=>centerHardware($('action-devices'))).observe($('action-devices'));
  function moduleInputs(m){
    const choices=[];if(!m)return choices;
    const add=(key,label,hint)=>choices.push({key,label,hint});
    if(m.productId==='SENSE_CUBE'){for(let i=0;i<5;i++)add('sense:'+i,'Tap event '+(i+1),'Use this configured tap event.');}
    else{
      const slots=m.productId==='DOT_KEY'?[2,3]:m.productId==='KNOB_KEY'?[0]:[...new Set([101,...(Array.isArray(m.config)?m.config.map(c=>c.keyCode):[])])];
      for(const key of slots)for(const [kind,label,hint] of [['singleClick','Single press','Press once.'],['doubleClick','Double press','Press twice quickly.'],['longPress','Long press','Press and hold.']]){
        const prefix=m.productId==='DOT_KEY'?'Button '+(key-1)+' / ':m.productId==='VIVO_CUBE'?'Screen button '+key+' / ':'';
        add(key+':'+kind,prefix+label,hint);
      }
      if(m.productId==='KNOB_KEY'){add('knob:clockwise','Turn clockwise','Turn the dial to the right.');add('knob:counterclockwise','Turn counterclockwise','Turn the dial to the left.');}
    }
    return choices;
  }
  function currentInput(){return inputChoices.find(item=>item.key===inputKey);}
  function vivoButton(module){const saved=draft.vivo_screens?.[module.serialNo];return saved?.button||(Array.isArray(module.config)&&module.config[0]?.keyCode)||101;}
  function ensureVivoSlot(serial,button){
    let module=current().module.find(m=>m.serialNo===serial);if(!module){module={serialNo:serial,productId:'VIVO_CUBE',config:[]};current().module.push(module);}
    if(!module.config.some(slot=>slot.keyCode===button))module.config.push({keyCode:button,widgetType:1});
  }
  async function prepareVivoPicture(action,force=false){
    const module=modules().find(m=>m.serialNo===moduleSerial);if(module?.productId!=='VIVO_CUBE')return null;
    if(draft.vivo_screens?.[moduleSerial]?.source==='custom'&&!force)return null;
    const saved=action?savedPcAction(action):null;let image;
    if(saved?.kind==='program')image=(await(await api('/api/pc/program-icon',{method:'POST',body:JSON.stringify({target:saved.target})})).json()).image;
    else{
      const app=action?.type==='ACTIVITY'?action.values?.find(v=>v.id==='1')?.value:null;
      if(typeof app==='string'){
        try{const blob=await(await api('/api/editor/icons/app/'+encodeURIComponent(app))).blob(),body=new FormData();body.append('image',blob,'app.png');image=(await(await api('/api/pc/images',{method:'POST',body})).json()).image;}catch(_){/* Use the Studio app picture if the device icon is unavailable. */}
      }
      if(!image)image=(await(await api('/api/pc/default-image',{method:'POST',body:JSON.stringify({kind:action?.type==='ACTIVITY'?'program':'url'})})).json()).image;
    }
    return {image:image.sha256,clear:false,button:vivoButton(module),source:'action'};
  }
  function renderVivoScreen(module){
    const box=$('vivo-screen-settings');box.replaceChildren();box.hidden=module?.productId!=='VIVO_CUBE';if(box.hidden)return;
    const serial=module.serialNo,record=draft.vivo_screens?.[serial],preview=el('div','vivo-picture-preview'),copy=el('div','vivo-picture-controls');
    if(record?.clear)preview.textContent='Blank screen';
    else if(record?.image)showShortcutPicture('/api/editor/vivo-picture/'+record.image,preview);
    else if(cubeImages[serial]?.url){const img=el('img');img.src=cubeImages[serial].url;img.alt='Current Vivo screen';preview.append(img);}
    else preview.textContent='Choose a picture';
    copy.append(el('h3','','Vivo screen picture'),el('p','muted','One full-screen button. This image is shared across profiles and all press types on this Cube. Upload a picture, or use the action’s icon. Changes apply on Deploy.'));
    const label=el('label','property-field','Upload screen picture'),upload=el('input');upload.id='vivo-picture-upload';upload.type='file';upload.accept='image/png,image/jpeg,image/webp';label.append(upload);copy.append(label,el('p','muted','PNG, JPG or WebP, up to 2 MB. Studio automatically rounds the picture corners on the Vivo screen.'));
    async function updatePicture(getPicture){
      if(working||actionSaving)return;const context=[draft.device_id,current().id,serial].join('|');actionSaving=true;busy=true;updateControls();
      try{const image=await getPicture();if(context!==[draft?.device_id,current()?.id,moduleSerial].join('|'))throw new Error('The selected device changed. Choose its picture again.');
        change(()=>{ensureVivoSlot(serial,image.button);draft.vivo_screens??={};draft.vivo_screens[serial]=image;});$('action-feedback').textContent='Vivo screen picture saved in your draft. Save, then Deploy to display it.';
      }catch(error){message(error.message,true);}finally{actionSaving=false;busy=false;updateControls();}
    }
    upload.onchange=()=>{const file=upload.files[0];if(!file)return;if(file.size>2*1024*1024){message('Choose a PNG, JPG or WebP picture up to 2 MB.',true);return;}
      updatePicture(async()=>{const body=new FormData();body.append('image',file);const data=await(await api('/api/pc/images',{method:'POST',body})).json();return {image:data.image.sha256,clear:false,button:vivoButton(module),source:'custom'};});
    };
    const tools=el('div','editor-buttons');tools.append(button('Use action icon',()=>updatePicture(()=>prepareVivoPicture(inputScene()?.actions?.[0]||module.config?.[0]?.singleClick?.actions?.[0],true))),button('Clear screen & actions',()=>{
      if(working||actionSaving||!confirm('Clear this Vivo screen and its button actions across all profiles? Save and Deploy to apply.'))return;
      change(()=>{ensureVivoSlot(serial,vivoButton(module));for(const profile of draft.profiles)for(const m of profile.module)if(m.serialNo===serial)for(const slot of m.config)for(const kind of ['singleClick','doubleClick','longPress'])if(slot[kind])slot[kind].actions=[];draft.vivo_screens??={};draft.vivo_screens[serial]={image:null,clear:true,button:vivoButton(module),source:'blank'};});
      $('action-feedback').textContent='Vivo screen and actions cleared in the draft. Save and Deploy to apply.';
    },'danger-quiet'));copy.append(tools);box.append(preview,copy);
  }
  function renderModules(){
    const list=modules();if(!list.some(m=>m.serialNo===moduleSerial)){moduleSerial='';inputKey='';resetActionComposer();}
    renderActionDevices();
    const m=list.find(m=>m.serialNo===moduleSerial);inputChoices=moduleInputs(m);
    if(inputKey&&!currentInput()){inputKey='';resetActionComposer();}
    $('action-config').hidden=!m;$('action-device-empty').hidden=!!m;
    $('action-module-title').textContent=m?`${names[m.productId]||m.productId} / ${m.serialNo.slice(-6)}`:'';
    $('action-module-status').textContent='Set up one press or gesture at a time.';
    $('action-vivo-help').hidden=m?.productId!=='VIVO_CUBE';
    renderVivoScreen(m);
    const box=$('action-input-choices'),focused=box.contains(document.activeElement)?document.activeElement.dataset.inputKey:null;box.replaceChildren();
    for(const item of inputChoices){
      const b=button('',()=>{if(working||actionSaving)return;inputKey=item.key;resetActionComposer();renderModules();});
      b.dataset.inputKey=item.key;b.setAttribute('aria-label',item.label);b.setAttribute('aria-pressed',String(inputKey===item.key));
      b.append(el('strong','',item.label),el('span','',item.hint));box.append(b);
    }
    if(focused)[...box.children].find(b=>b.dataset.inputKey===focused)?.focus({preventScroll:true});
    $('action-step-type').hidden=!inputKey;
    $('action-step-type-help').textContent=currentInput()?`When you use ${currentInput().label.toLowerCase()}, what should happen?`:'';
    renderActionLibrary();renderSequence();
  }
  function inputScene(create=false){
    if(!inputKey||!moduleSerial)return null;
    let m=current().module.find(m=>m.serialNo===moduleSerial);if(!m&&create){const meta=modules().find(m=>m.serialNo===moduleSerial);if(!meta)return null;m={serialNo:meta.serialNo,productId:meta.productId,config:meta.productId==='KNOB_KEY'?{}:[]};current().module.push(m);}if(!m)return null;
    const [key,kind]=inputKey.split(':');
    if(key==='knob'){if(!m.config[kind]&&create)m.config[kind]={actions:[],name:kind,type:'MANUAL',enabled:false,show:false};return m.config[kind];}
    if(key==='sense'){let scene=m.config.find(s=>s.mode===Number(kind));if(!scene&&create){scene={mode:Number(kind),actions:[],name:'Tap event '+(Number(kind)+1),type:'MANUAL',enabled:false,show:false};m.config.push(scene);}return scene;}
    let slot=m.productId==='KNOB_KEY'?m.config.button:m.config.find(s=>s.keyCode===Number(key));
    if(!slot&&create){slot={keyCode:Number(key)};if(m.productId==='VIVO_CUBE')slot.widgetType=1;if(m.productId==='KNOB_KEY')m.config.button=slot;else m.config.push(slot);}
    if(!slot)return null;if(!slot[kind]&&create)slot[kind]={actions:[],name:kind,type:'MANUAL',enabled:false,show:false};return slot[kind];
  }
  function readableAppName(id){
    const app=[...apps,...storePresets].find(w=>w.id===id);
    if(app?.name&&app.name!==id)return app.name;
    const text=String(id||'Core app').split('.').pop().replace(/[_-]/g,' ').replace(/([a-z])([A-Z])/g,'$1 $2');
    return text.charAt(0).toUpperCase()+text.slice(1);
  }
  function savedPcAction(a){return a.type==='PC_CONTROL'?pcActions.find(p=>p.id===a.values?.[0]?.value?.payload?.params?.id):null;}
  function actionName(a){
    if(a.type==='ACTIVITY')return 'Launch '+readableAppName(a.values?.[0]?.value);
    const saved=savedPcAction(a);if(saved)return saved.name;
    const payload=a.values?.[0]?.value?.payload;
    const label=a.name||payload?.action||a.type||'Action';
    return ({startApp:'Open PC program',PC_CONTROL:'PC action',PC_VOLUME:'Volume control',PC_MEDIA:'Media control'})[label]||label.replace(/_/g,' ').replace(/([a-z])([A-Z])/g,'$1 $2');
  }
  function actionDetail(a){const saved=savedPcAction(a);return saved?`${saved.kind==='url'?'Website':'PC program'} / ${saved.target}`:a.type==='ACTIVITY'?'Opens on CoreBAR':'Existing device action';}
  function pcParam(a){return {output:10,payload:{action:'studioAction',params:{id:a.id}}};}
  function pcAction(a){return {type:'PC_CONTROL',values:[{id:'1',value:pcParam(a)}]};}
  function actionLibrary(){
    const list=apps.map(w=>({type:'ACTIVITY',id:'activity',values:[{id:'1',value:w.id}]}));list.push(...pcActions.map(pcAction));
    function walk(v){if(!v||typeof v!=='object')return;if(Array.isArray(v.actions))list.push(...v.actions);else Object.values(v).forEach(walk);}
    draft.profiles.forEach(p=>walk(p.module));const seen=new Set();return list.filter(a=>{const key=JSON.stringify(a);if(seen.has(key))return false;seen.add(key);return true;});
  }
  function resetActionComposer(){
    actionType='';editingActionIndex=null;actionChoiceItems=[];
    $('action-setup-form').reset();$('action-setup-error').textContent='';$('action-feedback').textContent='';
    $('action-step-settings').hidden=true;
  }
  function renderActionLibrary(){
    if(!draft)return;
    const other=actionLibrary().filter(a=>a.type!=='ACTIVITY'&&!a.type?.startsWith('PC_'));
    for(const b of document.querySelectorAll('[data-action-type]')){b.setAttribute('aria-pressed',String(b.dataset.actionType===actionType));if(b.dataset.actionType==='existing')b.hidden=!other.length;}
    $('action-step-settings').hidden=!inputKey||!actionType;
    if(!actionType)return;
    const custom=actionType==='website'||actionType==='program';
    $('action-target-fields').hidden=!custom;$('action-choice-field').hidden=custom;
    $('action-target').required=custom;$('action-choice').required=!custom;
    $('action-target').disabled=!custom;
    $('action-browse-program').hidden=actionType!=='program';
    $('action-target-label').textContent=actionType==='website'?'Website URL':'Program on this PC';
    $('action-target').type=actionType==='website'?'url':'text';
    $('action-target').placeholder=actionType==='website'?'https://example.com':'C:\\Program Files\\App\\App.exe';
    const labels={website:'Which website should open?',program:'Which program should open?', 'core-app':'Which Core app should open?', 'pc-action':'Which PC action should run?',existing:'Which existing action should run?'};
    $('action-step-settings-title').textContent=labels[actionType];
    $('action-settings-help').textContent=custom?(actionType==='website'?'Opens in your default PC browser. Keep Studio running on this PC.':'Choose an existing .exe file on this PC. Keep Studio running for this action to work.'):actionType==='core-app'?'The app opens on CoreBAR when you use this input.':'Choose an action already configured for this device. PC controls may require their original PC software.';
    $('action-setup-submit').textContent=editingActionIndex===null?'Add action':'Update action';
    $('action-choice-empty').hidden=true;$('action-setup-submit').disabled=actionSaving;
    if(custom){$('action-choice').disabled=true;return;}
    const select=$('action-choice'),previous=select.selectedOptions[0]?.dataset.identity;select.replaceChildren();
    if(actionType==='core-app'){
      const seen=new Set();actionChoiceItems=[...apps.filter(a=>a.type==='APPS').map(a=>({type:'ACTIVITY',id:'activity',values:[{id:'1',value:a.id}]})),...storePresets.filter(a=>a.type==='APPS').map(a=>({type:'ACTIVITY',id:'activity',values:[{id:'1',value:a.id}]})),...actionLibrary().filter(a=>a.type==='ACTIVITY')].filter(a=>{const id=a.values?.[0]?.value;if(!id||seen.has(id))return false;seen.add(id);return true;});
    }else actionChoiceItems=actionLibrary().filter(a=>actionType==='pc-action'?a.type?.startsWith('PC_'):a.type!=='ACTIVITY'&&!a.type?.startsWith('PC_'));
    actionChoiceItems.forEach((a,i)=>{option(select,String(i),actionName(a));select.lastChild.dataset.identity=JSON.stringify(a);});
    const match=[...select.options].find(o=>o.dataset.identity===previous);if(match)select.value=match.value;
    select.disabled=!actionChoiceItems.length;$('action-setup-submit').disabled=actionSaving||!actionChoiceItems.length;
    $('action-choice-label').textContent=actionType==='core-app'?'App on CoreBAR':'Saved action';
    if(!actionChoiceItems.length){$('action-choice-empty').hidden=false;$('action-choice-empty').textContent=actionType==='core-app'?'No Core apps are available. Refresh the connection to load apps from CoreBAR.':'No saved actions of this type are available. Choose Open website or Open PC program to create a PC action.';}
  }
  function chooseActionType(type){if(working||actionSaving)return;const index=editingActionIndex;resetActionComposer();editingActionIndex=index;actionType=type;renderActionLibrary();}
  function commitWizardAction(a,artwork=null){
    const index=editingActionIndex;resetActionComposer();
    change(()=>{const scene=inputScene(true);scene.actions??=[];if(index!==null)scene.actions.splice(index,1,clone(a));else scene.actions.push(clone(a));if(artwork){draft.vivo_screens??={};draft.vivo_screens[moduleSerial]=artwork;}});
    $('action-feedback').textContent=(index===null?'Action added.':'Action updated.')+' Save your draft, then Deploy to Core when ready.';
  }
  function editAssignedAction(a,index){
    resetActionComposer();editingActionIndex=index;const saved=savedPcAction(a);
    actionType=a.type==='ACTIVITY'?'core-app':saved?(saved.kind==='url'?'website':'program'):a.type?.startsWith('PC_')?'pc-action':'existing';
    renderActionLibrary();
    if(saved){$('action-target').value=saved.target;$('action-name').value=saved.name;}
    else{const match=actionChoiceItems.findIndex(item=>JSON.stringify(item)===JSON.stringify(a));if(match>=0)$('action-choice').value=String(match);}
    $('action-step-settings').scrollIntoView({block:'nearest'});
  }
  for(const b of document.querySelectorAll('[data-action-type]'))b.onclick=()=>chooseActionType(b.dataset.actionType);
  $('action-setup-cancel').onclick=()=>{resetActionComposer();renderActionLibrary();};
  $('action-browse-program').onclick=async()=>{
    const browse=$('action-browse-program'),context=[draft.device_id,current().id,moduleSerial,inputKey,actionType].join('|');browse.disabled=true;
    try{const data=await(await api('/api/pc/browse',{method:'POST',body:'{}'})).json();if(context===[draft?.device_id,current()?.id,moduleSerial,inputKey,actionType].join('|')&&data.path)$('action-target').value=data.path;}
    catch(error){$('action-setup-error').textContent=error.message;}finally{browse.disabled=false;}
  };
  $('action-setup-form').onsubmit=async event=>{
    event.preventDefault();if(working||actionSaving||!inputKey||!actionType)return;
    $('action-setup-error').textContent='';
    const context=[draft.device_id,current().id,moduleSerial,inputKey].join('|');
    const target=$('action-target').value.trim(),kind=actionType==='website'?'url':'program';
    const fallback=kind==='url'?target.replace(/^https?:\/\//,'').split('/')[0]:target.split(/[\\/]/).pop().replace(/\.exe$/i,'');
    const name=$('action-name').value.trim()||('Open '+fallback).slice(0,100);
    actionSaving=true;busy=true;updateControls();$('action-setup-submit').disabled=true;
    try{
      let action;
      if(actionType==='website'||actionType==='program'){const data=await(await api('/api/pc/actions',{method:'POST',body:JSON.stringify({name,kind,target,device_id:draft.device_id})})).json();pcActions=data.actions;action=pcAction(data.action);}
      else action=actionChoiceItems[Number($('action-choice').value)];
      if(!action)throw new Error('Choose an action first.');
      const artwork=await prepareVivoPicture(action);
      if(context!==[draft?.device_id,current()?.id,moduleSerial,inputKey].join('|'))throw new Error('The selected input changed. Your PC action was saved; choose it under PC action to assign it.');
      commitWizardAction(action,artwork);
    }catch(error){$('action-setup-error').textContent=error.message;}
    finally{actionSaving=false;busy=false;updateControls();renderActionLibrary();}
  };
  function addAction(a,index=null){if(!inputKey){message('Select a module input first.',true);return;}change(()=>{const s=inputScene(true);s.actions??=[];s.actions.splice(index??s.actions.length,0,clone(a));});}
  function moveAction(from,to){resetActionComposer();change(()=>{const list=inputScene().actions;const [a]=list.splice(from,1);list.splice(to>from?to-1:to,0,a);});}
  function renderSequence(){
    const box=$('action-sequence');box.replaceChildren();$('assigned-actions').hidden=!inputKey;$('action-input-title').textContent=currentInput()?'Actions for '+currentInput().label:'Assigned actions';
    const actions=inputScene()?.actions||[];actions.forEach((a,i)=>{const row=el('div','sequence-item');row.append(el('span','step-number',String(i+1).padStart(2,'0')),el('strong','',actionName(a)),el('small','muted',actionDetail(a)));const controls=el('div','sequence-buttons');controls.append(button('Edit',()=>editAssignedAction(a,i)),button('↑',()=>moveAction(i,Math.max(0,i-1))),button('↓',()=>moveAction(i,Math.min(actions.length,i+2))),button('Remove',()=>{resetActionComposer();change(()=>inputScene().actions.splice(i,1));}));row.append(controls);draggable(row,{kind:'action-move',index:i});dropzone(row,data=>{if(data.kind==='action-new')addAction(data.action,i);if(data.kind==='action-move')moveAction(data.index,i);});box.append(row);});
    if(!actions.length)box.append(el('p','canvas-empty','No actions assigned yet. Choose what happens in step 2, then fill in step 3.'));
  }
  dropzone($('action-sequence'),data=>{if(data.kind==='action-new')addAction(data.action);if(data.kind==='action-move')moveAction(data.index,inputScene().actions.length);});
  async function save(profiles=draft.profiles){const response=await (await api('/api/editor/draft',{method:'POST',body:JSON.stringify({device_id:draft.device_id,revision:draft.revision,profiles,background_apps:draft.background_apps||[],app_settings:draft.app_settings||{},vivo_screens:draft.vivo_screens||{},compact_profiles:draft.compact_profiles||{}})})).json();draft=response.draft;dirty=false;updateControls();}
  async function operation(fn){if(working||!draft)return;working=true;busy=true;controls();updateControls();try{await fn();}catch(error){message(error.message,true);}finally{working=false;busy=false;controls();updateControls();}}
  function readPc(){
    if(!pcRequest)pcRequest=api('/api/pc').then(response=>response.json()).finally(()=>{pcRequest=null;});
    return pcRequest;
  }
  function usesPcMetrics(widget){
    const spec=nativeSpec(widget);
    return spec?['cpu','memory','gpu','disk'].includes(spec.kind):['CPU','MEMORY','STORAGE'].includes(widget.type);
  }
  async function refreshPrinterPreviews(){
    if(printerRequest||drag||document.hidden||mode!=='layout'||$('editor-content').hidden)return;
    const specs=current()?.homeData.map(nativeSpec).filter(spec=>spec?.kind==='bambu'&&/^[a-f0-9]{32}$/.test(spec.printerId))||[];
    const binding=specs.map(studioBinding).find(item=>item?.descriptor.connection);
    if(!binding)return;
    const generation=editorGeneration,ids=[...new Set(specs.map(spec=>spec.printerId))].slice(0,16);
    printerRequest=true;
    try{printerMetrics=(await packageUI.preview(binding,ids)).printers||{};}
    catch{printerMetrics={};}
    finally{printerRequest=false;}
    if(generation!==editorGeneration||mode!=='layout'||$('editor-content').hidden||drag)return;
    $('core-canvas').querySelectorAll('.canvas-widget').forEach((card,index)=>{
      const widget=current().homeData[index];
      if(widget&&nativeSpec(widget)?.kind==='bambu')renderNativePreview(widget,card);
    });
    renderBambuUnfolded?.();
  }
  async function refreshPreviewMetrics(){
    if(pcRequest||drag||!current()?.homeData.some(usesPcMetrics))return;
    const generation=editorGeneration;
    try{
      const data=await readPc();
      if(generation!==editorGeneration||mode!=='layout'||$('editor-content').hidden)return;
      pcMetrics=data.metrics||{};
      if(working||drag)return;
      $('core-canvas').querySelectorAll('.canvas-widget').forEach((card,index)=>{
        const widget=current().homeData[index];
        if(!widget||!usesPcMetrics(widget))return;
        if(nativeSpec(widget))renderNativePreview(widget,card);
        else renderStockPreview(widget,card);
      });
    }catch(error){$('pc-status').textContent=error.message;}
  }
  async function refreshPc(){
    try{const data=await readPc();pcActions=data.actions||[];pcMetrics=data.metrics||{};$('pc-status').textContent=data.status+' / '+(data.native_status||'');
      const metrics=$('pc-metrics');metrics.replaceChildren();for(const [label,value] of [['CPU',data.metrics?.cpu],['RAM',data.metrics?.memory],['GPU',data.metrics?.gpu?.usage]]){const card=el('div','metric-card');card.append(el('span','muted',label),el('strong','',value==null?'Unavailable':Math.round(value)+'%'));metrics.append(card);}for(const disk of data.metrics?.disks||[]){const card=el('div','metric-card');card.append(el('span','muted',disk.name),el('strong','',Math.round(disk.percent)+'%'),el('small','muted',disk.used_gb+' / '+disk.total_gb+' GB'));metrics.append(card);}
      $('pc-actions-list').replaceChildren(el('h3','','Saved PC actions'));for(const a of pcActions){const row=el('div','pc-action-row');row.append(el('strong','',a.name),el('span','muted',a.target),button('Add to Core',()=>{showMode('layout');addPcWidget(a);}));$('pc-actions-list').append(row);}if(draft){renderActionLibrary();if(!drag){renderLibrary();renderCanvas();renderProperties();}}
    }catch(error){$('pc-status').textContent=error.message;}
  }
  function addPcWidget(a){addWidget({id:'studio_pc_'+a.id,type:'PC_CONTROL',name:a.name,icon:'resId://pc_control_def_icon',iconScale:75,param:pcParam(a)});}
  $('pc-connect').onclick=async()=>{try{await api('/api/pc/connect',{method:'POST',body:'{}'});await refreshPc();}catch(error){message(error.message,true);}};
  $('nav-editor').onclick=openEditor;$('nav-overview').onclick=overview;
  for(const m of ['layout','actions','pc'])$('mode-'+m).onclick=()=>showMode(m);
  $('library-search').oninput=renderLibrary;
  function selectEditorProfile(index){
    profileIndex=index;widgetIndex=0;backgroundIndex=-1;moduleSerial='';inputKey='';
    pcWidgetForms.clear();resetActionComposer();renderEditor();
  }
  $('edit-profile').onchange=()=>{
    if(working||actionSaving)return;
    if($('edit-profile').value!=='new'){selectEditorProfile(Number($('edit-profile').value));return;}
    $('edit-profile').value=profileIndex;
    $('new-profile-form').reset();$('new-profile-error').textContent='';
    $('new-profile-name').setCustomValidity('');
    $('new-profile-dialog').showModal();
  };
  $('new-profile-name').oninput=()=>{$('new-profile-name').setCustomValidity('');$('new-profile-error').textContent='';};
  $('new-profile-cancel').onclick=()=>$('new-profile-dialog').close();
  $('new-profile-dialog').addEventListener('cancel',event=>{if(working)event.preventDefault();});
  $('new-profile-form').onsubmit=async event=>{
    event.preventDefault();
    const input=$('new-profile-name'),name=input.value.trim();
    if(!name){input.setCustomValidity('Enter a profile name.');input.reportValidity();return;}
    await operation(async()=>{
      const profile={id:'studio_profile_'+crypto.randomUUID().replaceAll('-',''),name,
        default:false,showName:true,iconScale:100,homeData:[],module:[]};
      const controls=[input,$('new-profile-cancel'),$('new-profile-save')];
      controls.forEach(control=>control.disabled=true);
      try{await save([...draft.profiles,profile]);}
      catch(error){$('new-profile-error').textContent=error.message;return;}
      finally{controls.forEach(control=>control.disabled=false);}
      for(const previous of history)previous.profiles.push(clone(profile));
      $('new-profile-dialog').close();
      selectEditorProfile(draft.profiles.length-1);
      message('Profile saved in your Studio draft. Use Deploy to add it to Core.');
    });
    if(!$('new-profile-dialog').open)$('edit-profile').focus();
  };
  $('edit-profile-name').onchange=()=>change(()=>current().name=$('edit-profile-name').value);
  $('edit-show-names').onchange=()=>change(()=>current().showName=$('edit-show-names').checked);
  $('widget-undo').onclick=()=>{if(working||!history.length)return;Object.assign(draft,history.pop());backgroundIndex=-1;dirty=true;pcWidgetForms.clear();resetActionComposer();renderEditor();};
  $('action-undo').onclick=()=>$('widget-undo').click();
  $('draft-save').onclick=()=>operation(async()=>{await save();message('Draft saved on this PC. Core has not been changed.');});
  $('draft-deploy').onclick=()=>{if(!draft||working)return;if(draft.profiles.some(p=>p.homeData.some(w=>w._pcPending))){message('Finish the website or PC app settings and choose Apply settings before Deploy.',true);return;}const box=$('deploy-summary');box.replaceChildren();draft.profiles.forEach((p,i)=>{if(JSON.stringify(p)!==JSON.stringify(draft.base_profiles[i]))box.append(el('p','',`${p.name}: ${p.homeData.length} widgets · ${p.module.length} module configurations`));});if(Object.keys(draft.compact_profiles||{}).length)box.append(el('p','','Apply mixed widget sizes to CoreBAR.'));if(!box.children.length)box.append(el('p','','Deploy will verify and resend this layout and apply background app changes.'));box.append(el('p','','Background / Core Notifications (built in)'));for(const app of draft.background_apps||[])box.append(el('p','','Background / '+app.name+' (no bar space)'));$('deploy-dialog').showModal();};
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
      const complete=data.activated===true && data.widgets_ready===true;
      box.dataset.state=complete?'success':'error';$('deploy-progress-title').textContent=complete?'Deployment complete':data.activated?'Layout saved - widgets pending':'Layout saved - home unavailable';close.textContent='Done';
      $('deploy-progress-help').textContent='You can close this window and continue editing.';
      setTimeout(()=>{captureScreen();captureCubes();},1000);
    }catch(error){box.dataset.state='error';$('deploy-progress-title').textContent='Deployment interrupted';close.textContent='Close';$('deploy-progress-help').textContent='Review the message above before trying again.';label.textContent=error.message;message(error.message,true);}
    finally{finished=true;clearInterval(timer);spinner.hidden=true;close.disabled=false;box.setAttribute('aria-busy','false');$('deploy-progress-time').textContent=Math.floor((Date.now()-started)/1000)+' seconds elapsed';close.focus();}
  });};
  $('draft-reset').onclick=()=>{if(!confirm('Replace the local draft with current Core settings? Download the draft first if you want to keep it.'))return;operation(async()=>{const data=await (await api('/api/editor/reset',{method:'POST',body:JSON.stringify({device_id:draft.device_id,revision:draft.revision})})).json();draft=data.draft;snapshot=data.snapshot;dirty=false;history=[];render();renderEditor();message('Draft reloaded from Core.');});};
  $('draft-restore').onclick=()=>{if(!confirm('Replace this draft with the saved pre-deploy settings? Core changes only when you deploy.'))return;operation(async()=>{const data=await (await api('/api/editor/restore-draft',{method:'POST',body:JSON.stringify({device_id:draft.device_id,revision:draft.revision})})).json();draft=data.draft;snapshot=data.snapshot;dirty=false;history=[];render();renderEditor();message('Pre-deploy settings loaded as a draft. Review, then deploy to restore Core.');});};
  $('draft-export').onclick=()=>{const url=URL.createObjectURL(new Blob([JSON.stringify(draft,null,2)],{type:'application/json'}));const a=el('a');a.href=url;a.download='ultrabar-studio-draft.json';a.click();setTimeout(()=>URL.revokeObjectURL(url),1000);};
  window.addEventListener('beforeunload',event=>{if(dirty){event.preventDefault();event.returnValue='';}});
  window.studioEditor={async deployFromStore(device){
    if(!snapshot)throw new Error('Connect Core first, then choose Review & deploy on the package card. The update stays in your library.');
    if(device&&snapshot.device_id!==device)throw new Error('The selected Core changed. Review the connected device before deploying this update.');
    if(working||busy||actionSaving)throw new Error('Wait for the current operation to finish, then deploy the update.');
    await openEditor();
    if(!draft||draft.device_id!==snapshot?.device_id)throw new Error('Could not load this Core draft. Reconnect and try again.');
    $('mode-layout').click();$('draft-deploy').click();
    if(!$('deploy-dialog').open)throw new Error($('editor-notice').textContent||'Finish your draft before deploying.');
  },async saveBeforeUpdate(){
    if(working||busy)throw new Error('Wait for the current device operation to finish before updating.');
    if(!dirty)return;
    working=true;busy=true;controls();updateControls();
    try{await save();}finally{working=false;busy=false;controls();updateControls();}
  },snapshotChanged(){ $('nav-editor').disabled=!snapshot;if(draft&&draft.device_id!==snapshot?.device_id){editorGeneration++;draft=null;dirty=false;apps=[];pcActions=[];overview();}if(snapshot)api('/api/pc/connect',{method:'POST',body:'{}'}).catch(error=>message(error.message,true));},hasUnsaved(){return dirty;}};
  setInterval(()=>{
    if(!snapshot||document.hidden||$('editor-content').hidden||working)return;
    if(mode==='pc')refreshPc();
    if(mode==='layout'){refreshPreviewMetrics();refreshPrinterPreviews();}
  },5000);
setInterval(()=>{if(!working&&!drag&&draft&&document.body.classList.contains('editing')){$('core-canvas').querySelectorAll('.canvas-widget').forEach((card,i)=>{const w=current().homeData[i];if(w&&nativeSpec(w)?.kind==='clock')renderNativePreview(w,card);});}},1000);
})();
