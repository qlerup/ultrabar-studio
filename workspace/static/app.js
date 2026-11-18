'use strict';
const $ = id => document.getElementById(id);
const token = document.querySelector('meta[name="studio-token"]').content;
let snapshot = null, selectedProfile = 0, busy = false, screenUrl = null;
let hardwarePolling = false, connectionGeneration = 0;
let screenPolling = false, screenCapturedAt = null, coreScreenOff = false;
let cubeImages = {}, cubeLoading = false, screenRefreshPending = false, cubeRefreshPending = false;
let layoutDrag = null, layoutSaving = false, suppressHardwareClickUntil = 0;
const names = {DOT_KEY:'DotKey',VIVO_CUBE:'VivoCube',KNOB_KEY:'KnobKey',SENSE_CUBE:'SenseCube',MEMORY:'Memory',STORAGE:'Storage',TIME:'Clock',APPS:'App',PC_CONTROL:'PC action'};
const symbols = {DOT_KEY:'⠿',VIVO_CUBE:'▣',KNOB_KEY:'◉',SENSE_CUBE:'◇',MEMORY:'▥',STORAGE:'▤',TIME:'◷',APPS:'▦',PC_CONTROL:'↗'};
function el(tag, className, text) { const node=document.createElement(tag); if(className) node.className=className; if(text!==undefined) node.textContent=text; return node; }
function notice(text, error=false) { $('notice').textContent=text; $('connection-notice').textContent=text; $('connection-notice').classList.toggle('error',error); $('notice').classList.toggle('error',error); $('setup-error-help').hidden=!error; }
async function api(path, options={}) {
  const response=await fetch(path,{...options,headers:{'X-Studio-Token':token,...(options.body instanceof FormData?{}:{'Content-Type':'application/json'})},signal:options.signal===null?undefined:AbortSignal.timeout(65000)});
  if(!response.ok) {const data=await response.json().catch(()=>({}));throw new Error(data.error || 'The request could not be completed.');}
  return response;
}
function controls() { $('connect').disabled=busy||layoutSaving;$('discovery-connect').disabled=busy||layoutSaving||!selectedDiscoveryTarget; $('refresh').disabled=busy||layoutSaving||!snapshot; $('preview-refresh').disabled=busy||screenPolling||cubeLoading||!snapshot; $('backup').disabled=busy||!snapshot; }
async function load(connect, target=$('target').value, automatic=false) {
  if(connect&&!automatic){clearTimeout(reconnectTimer);rememberedTarget='';}
  if(window.studioEditor?.hasUnsaved()&&!confirm('There are unsaved editor changes. Save the draft before changing devices or refreshing. Continue?'))return;
  if(busy||layoutSaving||layoutDrag)return; busy=true;connectionGeneration++;clearScreen();clearCubeImages();controls();notice(connect?'Connecting and loading your setup …':'Reading your current setup …');
  const profileId=snapshot?.profiles[selectedProfile]?.id;
  try {
    const response=await api(connect?'/api/connect':'/api/refresh',{method:'POST',body:connect?JSON.stringify({target}):undefined});
    snapshot=await response.json();selectedProfile=Math.max(0,snapshot.profiles.findIndex(p=>p.id===profileId));
    connectionStatus(true); if($('connection-dialog').open)$('connection-dialog').close();
    $('empty').hidden=true;$('workspace').hidden=false;
    render();window.studioEditor?.snapshotChanged();notice('Profile loaded. A local backup has been saved.');
    try{localStorage.setItem('ultrabar-target',snapshot.target);}catch{}
  }catch(error){notice(error.message+(automatic?' Retrying automatically in 15 seconds. Use Connect device to choose another connection.':''),true);connectionStatus(false);markHardwareUnknown('Status could not be refreshed. Retrying automatically.');}
  finally{busy=false;controls();if(snapshot){captureScreen();captureCubes();}}
}
function render() {
  renderHardware();
  $('profiles').replaceChildren();
  snapshot.profiles.forEach((p,i)=>{const button=el('button','profile-button'+(i===selectedProfile?' selected':''),p.name||p.id||'Unnamed profile');button.onclick=()=>{selectedProfile=i;render();};$('profiles').append(button);});
  const p=snapshot.profiles[selectedProfile];
  $('profile-name').textContent=p?.name||'No profiles';$('profile-meta').textContent=p?(p.default?'Default profile':'Saved profile')+' · '+snapshot.model:'There are no saved profiles on this device.';
  const modules=p?.module||[],widgets=p?.homeData||[];
  $('module-count').textContent=modules.length;$('widget-count').textContent=widgets.length;
  $('read-time').textContent='Last read '+new Date(snapshot.read_at).toLocaleString('en-GB');
}
function createHardwareUnit(device=null){
  if(!device){
  const core=el('button','hardware-unit core-unit'+(snapshot.hardware?.status_error?' is-unknown':''));core.dataset.layoutKey='core';core.append(el('div','unit-screen','COREBAR'),el('span','unit-name','CoreBAR'),el('span','unit-state',snapshot.hardware?.status_error?'Connection unverified':'Connected via ADB'));
  paintCoreScreen(core.querySelector('.unit-screen'));return core;
  }
    const unit=el('button','hardware-unit '+device.type.toLowerCase()+(device.online===false?' is-offline':device.online===null?' is-unknown':''));
    unit.title=`${device.name} · ${device.serial}`;
    unit.dataset.layoutKey=device.serial;
    const face=el('div','unit-face');
    if(device.type==='KNOB_KEY'){face.append(el('span','knob-dial'));}
    else if(device.type==='DOT_KEY'){face.append(el('span','dot-button'),el('span','dot-button'),el('span','dot-slider'));}
    else if(device.type==='SENSE_CUBE'){face.append(el('span','sense-eye'));}
    else{const display=el('span','cube-screen',device.type==='VIVO_CUBE'?(cubeImages[device.serial]?.error||'Loading artwork...'):'?');if(device.type==='VIVO_CUBE')display.title=cubeImages[device.serial]?.source||cubeImages[device.serial]?.error||'Reading saved artwork';if(cubeImages[device.serial]?.url){display.textContent='';const img=el('img','cube-artwork');img.src=cubeImages[device.serial].url;img.alt='Saved VivoCube artwork';img.draggable=false;display.append(img);};face.append(display);}
    unit.append(face,el('span','unit-name',names[device.type]||device.name),el('span','unit-state',device.online===true?'Online':device.online===false?'Offline':'Unknown'));
  return unit;
}
function renderHardware() {
  if(layoutDrag)return;
  const hardware=snapshot.hardware||{},devices=hardware.devices||[];
  const online=devices.filter(d=>d.online===true).length;
  const offline=devices.filter(d=>d.online===false).length;
  const unknown=devices.length-online-offline;
  $('hardware-status').textContent=hardware.status_error||`${online} online · ${offline} offline${unknown?' · '+unknown+' unknown':''} · checked ${new Date(hardware.checked_at||snapshot.read_at).toLocaleTimeString('en-GB')} · updates every 5 seconds`;
  const strip=$('hardware-preview'),focusedKey=strip.contains(document.activeElement)?document.activeElement.dataset.layoutKey:null;
  strip.replaceChildren();
  const core=createHardwareUnit();strip.append(core);
  core.title='Refresh CoreBAR screen preview';
  core.onclick=()=>{if(Date.now()<suppressHardwareClickUntil)return;captureScreen(true);};
  for(const device of devices){
    const unit=createHardwareUnit(device);
    unit.onclick=()=>{
      if(Date.now()<suppressHardwareClickUntil)return;
      $('hardware-detail').dataset.serial=device.serial;
      $('hardware-detail').textContent=`${names[device.type]||device.name} · ${device.serial} · ${device.online===true?'CoreBAR reports online':device.online===false?'CoreBAR reports offline':'Status unknown'}`;
    };
    strip.append(unit);
  }
  for(const key of snapshot.layout_order||[]){const card=[...strip.children].find(node=>node.dataset.layoutKey===key);if(card)strip.append(card);}
  // Unseen modules go at the end; remembered modules retain their saved order.
  const known=new Set(snapshot.layout_order||[]);
  if(known.size)for(const card of [...strip.children])if(!known.has(card.dataset.layoutKey))strip.append(card);
  for(const card of strip.children){card.setAttribute('aria-keyshortcuts','Alt+ArrowLeft Alt+ArrowRight');card.setAttribute('aria-describedby','layout-help');}
  renderCoreScreen();
  centerHardware();
  if(focusedKey)[...strip.children].find(node=>node.dataset.layoutKey===focusedKey)?.focus({preventScroll:true});
  const selected=devices.find(device=>device.serial===$('hardware-detail').dataset.serial);
  if(selected)$('hardware-detail').textContent=`${names[selected.type]||selected.name} · ${selected.serial} · ${selected.online===true?'CoreBAR reports online':selected.online===false?'CoreBAR reports offline':'Status unknown'}`;
  else if($('hardware-detail').dataset.serial){delete $('hardware-detail').dataset.serial;$('hardware-detail').textContent='Select a module to see its connection status.';}
  window.dispatchEvent(new Event('studio-hardware-changed'));
}
// Balance the space around CoreBAR without changing the saved device order.
function centerHardware(strip=$('hardware-preview')){
  const cards=[...strip.children];
  const core=cards.find(card=>card.dataset.layoutKey==='core');
  if(!core||!strip.clientWidth)return;
  // Old centering padding must not hold the strip wider than a resized window.
  strip.style.paddingLeft='14px';strip.style.paddingRight='14px';
  const gap=parseFloat(getComputedStyle(strip).columnGap)||0,base=14;
  const index=cards.indexOf(core);
  const span=items=>items.reduce((width,card)=>width+card.getBoundingClientRect().width+gap,0);
  const left=span(cards.slice(0,index)),right=span(cards.slice(index+1));
  const half=(strip.clientWidth-core.getBoundingClientRect().width)/2;
  strip.style.paddingLeft=Math.max(base,half-left)+'px';
  strip.style.paddingRight=Math.max(base,half-right)+'px';
}
new ResizeObserver(()=>{if(!layoutDrag)centerHardware();}).observe($('hardware-preview'));
function visibleLayoutOrder(){return [...$('hardware-preview').children].map(card=>card.dataset.layoutKey);}
async function saveHardwareOrder(focusKey=null){
  const previous=(snapshot.layout_order||[]).slice(),visible=visibleLayoutOrder(),remaining=visible.slice();
  // Preserve absent devices' remembered positions so reconnecting keeps their place.
  const order=previous.map(key=>visible.includes(key)?remaining.shift():key).concat(remaining);
  snapshot.layout_order=order;layoutSaving=true;controls();$('layout-feedback').textContent='Saving layout…';
  try{await api('/api/layout',{method:'POST',body:JSON.stringify({device_id:snapshot.device_id,order})});$('layout-feedback').textContent='Layout saved';}
  catch(error){snapshot.layout_order=previous;$('layout-feedback').textContent='Layout was not saved. '+error.message;}
  finally{layoutSaving=false;controls();renderHardware();if(focusKey)[...$('hardware-preview').children].find(card=>card.dataset.layoutKey===focusKey)?.focus({preventScroll:true});}
}
function updateDragPosition(){
  const drag=layoutDrag;if(!drag?.active)return;
  const strip=$('hardware-preview');
  drag.ghost.style.transform=`translate(${drag.x-drag.offsetX}px,${drag.y-drag.offsetY}px)`;
  const next=[...strip.children].find(card=>card!==drag.card&&drag.x<card.getBoundingClientRect().left+card.getBoundingClientRect().width/2);
  if(next!==drag.card.nextElementSibling)strip.insertBefore(drag.card,next||null);
}
function scrollHardwareDrag(){
  if(!layoutDrag?.active)return;
  const strip=$('hardware-preview'),bounds=strip.getBoundingClientRect();
  if(layoutDrag.x<bounds.left+38)strip.scrollLeft-=12;
  else if(layoutDrag.x>bounds.right-38)strip.scrollLeft+=12;
  updateDragPosition();layoutDrag.frame=requestAnimationFrame(scrollHardwareDrag);
}
function finishHardwareDrag(cancelled=false){
  const drag=layoutDrag;if(!drag)return;
  layoutDrag=null;
  cancelAnimationFrame(drag.frame);drag.ghost?.remove();drag.card.classList.remove('is-dragging');
  const strip=$('hardware-preview');if(strip.hasPointerCapture(drag.pointerId))strip.releasePointerCapture(drag.pointerId);
  if(!drag.active)return;
  suppressHardwareClickUntil=Date.now()+400;
  if(cancelled){renderHardware();$('layout-feedback').textContent='Move cancelled';return;}
  if(JSON.stringify(visibleLayoutOrder())!==JSON.stringify(drag.initial))saveHardwareOrder(drag.card.dataset.layoutKey);
  else renderHardware();
}
$('hardware-preview').addEventListener('pointerdown',event=>{
  const card=event.target.closest('.hardware-unit');
  if(!card||event.button!==0||layoutSaving||busy||layoutDrag)return;
  const rect=card.getBoundingClientRect();
  layoutDrag={card,pointerId:event.pointerId,startX:event.clientX,startY:event.clientY,x:event.clientX,y:event.clientY,offsetX:event.clientX-rect.left,offsetY:event.clientY-rect.top,initial:visibleLayoutOrder(),active:false};
});
document.addEventListener('pointermove',event=>{
  const drag=layoutDrag;if(!drag||event.pointerId!==drag.pointerId)return;
  drag.x=event.clientX;drag.y=event.clientY;
  if(!drag.active&&Math.hypot(drag.x-drag.startX,drag.y-drag.startY)>7){
    drag.active=true;const rect=drag.card.getBoundingClientRect();drag.ghost=drag.card.cloneNode(true);
    drag.ghost.classList.add('drag-ghost');drag.ghost.setAttribute('aria-hidden','true');drag.ghost.tabIndex=-1;drag.ghost.style.width=rect.width+'px';
    document.body.append(drag.ghost);drag.card.classList.add('is-dragging');$('hardware-preview').setPointerCapture(event.pointerId);
    $('layout-feedback').textContent='Drop to save · Esc to cancel';scrollHardwareDrag();
  }
  if(drag.active){event.preventDefault();updateDragPosition();}
},{passive:false});
document.addEventListener('pointerup',event=>{if(layoutDrag?.pointerId===event.pointerId)finishHardwareDrag();});
document.addEventListener('pointercancel',()=>finishHardwareDrag(true));
window.addEventListener('blur',()=>finishHardwareDrag(true));
document.addEventListener('keydown',event=>{if(event.key==='Escape'&&layoutDrag){event.preventDefault();finishHardwareDrag(true);}});
$('hardware-preview').addEventListener('keydown',event=>{
  if(!event.altKey||!['ArrowLeft','ArrowRight'].includes(event.key)||layoutSaving||busy||layoutDrag)return;
  const card=event.target.closest('.hardware-unit');if(!card)return;
  event.preventDefault();const sibling=event.key==='ArrowLeft'?card.previousElementSibling:card.nextElementSibling;if(!sibling)return;
  $('hardware-preview').insertBefore(card,event.key==='ArrowLeft'?sibling:sibling.nextElementSibling);
  saveHardwareOrder(card.dataset.layoutKey);
});
function connectionStatus(connected) {
  $('connection-badge').textContent=connected?'Connected \u00b7 '+snapshot.target:'Not connected';
  $('connection-badge').classList.toggle('connected',connected);
  $('connection-open').textContent=connected?'Manage connection':'Connect device';
}
function openConnection(){if($('connection-dialog').open)return;clearTimeout(reconnectTimer);rememberedTarget='';$('manual-connection').open=false;$('connection-notice').textContent='';$('connection-dialog').showModal();discoverDevices();}
$('connection-open').onclick=openConnection;
function markHardwareUnknown(message) {
  connectionStatus(false);
  if(!snapshot)return;
  snapshot.hardware={...snapshot.hardware,status_error:message,devices:(snapshot.hardware?.devices||[]).map(device=>({...device,online:null}))};
  renderHardware();
}
async function pollHardware() {
  if(!snapshot||busy||hardwarePolling||document.hidden)return;
  const generation=connectionGeneration,target=snapshot.target;
  hardwarePolling=true;
  try {
    const response=await api('/api/hardware');
    const data=await response.json();
    if(generation!==connectionGeneration||target!==snapshot?.target||data.target!==target)return;
    if(data.hardware.status_error)markHardwareUnknown(data.hardware.status_error);
    else{snapshot.hardware=data.hardware;connectionStatus(true);renderHardware();}
    if(data.preview_revision&&data.preview_revision!==snapshot.preview_revision){snapshot.preview_revision=data.preview_revision;captureScreen();captureCubes();}
  }catch(error){if(generation===connectionGeneration)markHardwareUnknown('Connection lost. Module status is unknown; retrying automatically.');}
  finally{hardwarePolling=false;}
}
setInterval(pollHardware,5000);
document.addEventListener('visibilitychange',()=>{if(!document.hidden){pollHardware();if(!screenUrl)captureScreen();}});
$('connect-form').onsubmit=event=>{event.preventDefault();load(true);};$('refresh').onclick=()=>load(false);
function renderCoreScreen(){document.querySelectorAll('.core-unit .unit-screen').forEach(paintCoreScreen);}
function paintCoreScreen(face){
  if(!face)return;
  face.replaceChildren();
  if(screenUrl){const img=el('img','core-screen-image');img.src=screenUrl;img.alt='Actual CoreBAR screen';img.draggable=false;face.append(img);}
  else face.append(el('span','','COREBAR'));
  if(coreScreenOff&&screenUrl)face.append(el('span','screen-off-label','Screen is off'));
}
function clearScreen(){
  if(screenUrl)URL.revokeObjectURL(screenUrl);screenUrl=null;screenCapturedAt=null;coreScreenOff=false;
  $('screen-state').textContent='';renderCoreScreen();
}
async function captureScreen(manual=false){
  if(!snapshot||busy||document.hidden)return;
  if(screenPolling){screenRefreshPending=true;return;}
  const generation=connectionGeneration;
  screenPolling=true;controls();
  $('screen-state').textContent=screenCapturedAt?'Refreshing preview…':'Capturing screen…';
  try{
    const response=await api('/api/screen'),blob=await response.blob();
    if(generation!==connectionGeneration)return;
    const nextUrl=URL.createObjectURL(blob),previousUrl=screenUrl;
    screenUrl=nextUrl;screenCapturedAt=new Date();coreScreenOff=response.headers.get('X-Core-Screen-State')==='OFF';renderCoreScreen();
    if(previousUrl)URL.revokeObjectURL(previousUrl);
    $('screen-state').textContent=(coreScreenOff?'CoreBAR screen is off. Wake it on the device to see its content. ':'')+'Captured '+screenCapturedAt.toLocaleTimeString('en-GB')+' · saved preview; refreshed when configuration changes';
  }catch(error){
    if(generation!==connectionGeneration)return;
    $('screen-state').textContent=(screenUrl?'Showing previous preview. ':'Preview unavailable. ')+error.message;
  }finally{screenPolling=false;controls();if(screenRefreshPending){screenRefreshPending=false;captureScreen();}}
}
function clearCubeImages(){
  for(const entry of Object.values(cubeImages))if(entry.url)URL.revokeObjectURL(entry.url);
  cubeImages={};
}
async function captureCubes(){
  if(!snapshot)return;
  if(cubeLoading){cubeRefreshPending=true;return;}
  const generation=connectionGeneration;cubeLoading=true;controls();
  try{
    const response=await api('/api/cube-previews'),data=await response.json();
    if(generation!==connectionGeneration)return;
    for(const [serial,entry] of Object.entries(data.previews)){
      if(entry.image){
        const bytes=Uint8Array.from(atob(entry.image),c=>c.charCodeAt(0));
        if(cubeImages[serial]?.url)URL.revokeObjectURL(cubeImages[serial].url);
        cubeImages[serial]={url:URL.createObjectURL(new Blob([bytes],{type:'image/png'})),source:entry.source};
      }else if(!cubeImages[serial]?.url)cubeImages[serial]=entry;
    }
    renderHardware();
  }catch(error){if(generation===connectionGeneration)$('preview-help').textContent='Could not refresh cube artwork. '+error.message;}
  finally{cubeLoading=false;controls();if(cubeRefreshPending){cubeRefreshPending=false;captureCubes();}}
}
$('preview-refresh').onclick=()=>{captureScreen(true);captureCubes();};
$('backup').onclick=async()=>{
  try{const response=await api('/api/backup');const url=URL.createObjectURL(await response.blob());const a=el('a');a.href=url;a.download='ultrabar-profil-backup.xml';document.body.append(a);a.click();a.remove();setTimeout(()=>URL.revokeObjectURL(url),1000);notice('Backup is ready to download.');}catch(error){notice(error.message,true);}
};
let discovering=false,targetEdited=false;
$('target').addEventListener('input',()=>{targetEdited=true;});
let selectedDiscoveryTarget=null, discoveryGeneration=0;
function clearDiscoverySelection(){selectedDiscoveryTarget=null;$('discovery-selection').hidden=true;controls();}
async function discoverDevices(){
  if(discovering)return;
  discovering=true;const generation=++discoveryGeneration;clearDiscoverySelection();
  $('discover').disabled=true;$('discover').textContent='Searching...';
  const results=$('discovery-results');results.replaceChildren(el('p','muted','Looking for CoreBAR devices on your local network...'));
  try{
    const data=await(await api('/api/discover')).json();
    if(generation!==discoveryGeneration)return;
    results.replaceChildren();
    if(!data.devices.length)results.append(el('p','muted','No CoreBAR found. Check the network and try Find devices again, or use Manual connection below.'));
    for(const device of data.devices){
      const button=el('button','discovered-device');button.type='button';button.setAttribute('aria-pressed','false');
      button.append(el('strong','',device.name||'CoreBAR'),el('span','muted',device.ip+' / '+device.serial));
      button.onclick=()=>{
        if(busy||layoutSaving)return;
        selectedDiscoveryTarget=device.target;
        for(const item of results.querySelectorAll('.discovered-device'))item.setAttribute('aria-pressed',String(item===button));
        $('discovery-selected-name').textContent=(device.name||'CoreBAR')+' / '+device.ip;
        $('discovery-selection').hidden=false;controls();
      };results.append(button);
    }
    if(data.devices.length)results.append(el('p','muted','Select a CoreBAR, then click Connect.'));
  }catch(error){if(generation===discoveryGeneration)results.replaceChildren(el('p','error',error.message+' Use Find devices to retry, or Manual connection below.'));}
  finally{if(generation===discoveryGeneration){discovering=false;$('discover').disabled=false;$('discover').textContent='Find devices';}}
}
$('discovery-connect').onclick=()=>{if(selectedDiscoveryTarget)load(true,selectedDiscoveryTarget);};
$('connection-dialog').addEventListener('close',()=>{discoveryGeneration++;discovering=false;clearDiscoverySelection();$('discover').disabled=false;$('discover').textContent='Find devices';});
$('discover').onclick=discoverDevices;
document.querySelectorAll('.setup-guide-trigger').forEach(button=>button.addEventListener('click',()=>{if(!$('setup-guide').open)$('setup-guide').showModal();}));
$('guide-find-devices').onclick=()=>{$('setup-guide').close();openConnection();};
$('setup-guide').addEventListener('close',()=>{api('/api/setup-seen',{method:'POST'}).catch(()=>{});});
let reconnectTimer=null,rememberedTarget='';
async function reconnectRemembered(){
  if(!rememberedTarget||snapshot||targetEdited)return;
  if(!busy&&!$('connection-dialog').open)await load(true,rememberedTarget,true);
  if(rememberedTarget&&!snapshot&&!targetEdited)reconnectTimer=setTimeout(reconnectRemembered,15000);
}
const startupReady=api('/api/preferences').then(response=>response.json()).then(async data=>{
  if(busy||snapshot||targetEdited||document.activeElement===$('target')||$('connection-dialog').open)return;
  $('target').value=data.target;
  if(data.target){rememberedTarget=data.target;await reconnectRemembered();}
  else if(!data.setup_seen&&!$('setup-guide').open)$('setup-guide').showModal();
}).catch(()=>{});

let savedStartup=false;
$('settings-open').onclick=async()=>{
  $('settings-dialog').showModal();$('start-with-windows').disabled=true;$('settings-status').textContent='Loading settings...';
  try{
    const data=await(await api('/api/settings')).json();savedStartup=data.start_with_windows;
    $('start-with-windows').checked=savedStartup;$('start-with-windows').disabled=!data.startup_supported;
    $('settings-status').textContent=data.startup_supported?'Changes are saved automatically.':'Available in the installed Windows app.';
  }catch(error){$('settings-status').textContent=error.message;}
};
$('start-with-windows').onchange=async()=>{
  const input=$('start-with-windows');input.disabled=true;$('settings-status').textContent='Saving...';
  try{
    const data=await(await api('/api/settings',{method:'POST',body:JSON.stringify({start_with_windows:input.checked})})).json();
    savedStartup=data.start_with_windows;input.checked=savedStartup;$('settings-status').textContent='Settings saved.';
  }catch(error){input.checked=savedStartup;$('settings-status').textContent=error.message;}
  finally{input.disabled=false;}
};

let updateJob={state:'idle'}, updateCheck=null, startupUpdatePending=false, updateStartupReady=false;
function showStartupUpdate(){
  if(!startupUpdatePending||!updateStartupReady||document.querySelector('dialog[open]'))return;
  startupUpdatePending=false;
  $('updates-dialog').showModal();
}
document.addEventListener('close',()=>{queueMicrotask(showStartupUpdate);},true);
startupReady.finally(()=>{updateStartupReady=true;showStartupUpdate();});
function showUpdateJob(job){
  updateJob=job;
  const active=job.state==='downloading';
  $('updates-check').disabled=active;
  $('updates-download').disabled=active;
  $('updates-install').hidden=job.state!=='ready';
  if(job.state!=='idle'){
    $('updates-status').textContent=job.message+(active&&job.total?' '+Math.floor(100*job.received/job.total)+'%':'');
    $('updates-download').hidden=!['error'].includes(job.state);
  }
}
function checkUpdates(startup=false,force=false){
  if(updateCheck)return updateCheck;
  updateCheck=runUpdateCheck(startup,force).finally(()=>{updateCheck=null;});
  return updateCheck;
}
async function runUpdateCheck(startup,force){
  $('updates-check').disabled=true;$('updates-download').hidden=true;$('updates-install').hidden=true;
  $('updates-status').textContent='Checking for updates...';
  $('updates-notes').hidden=true;
  try{
    const job=await(await api('/api/updates/status')).json();
    const active=['downloading','ready','launched'].includes(job.state);
    if(active)showUpdateJob(job);
    const data=await(await api('/api/updates',force?{method:'POST'}:{})).json();
    const button=$('updates-open');
    button.textContent=data.update_available?`Update available: ${data.latest_version}`:'Check for updates';
    button.classList.toggle('update-available',data.update_available);
    button.title=data.update_available?`Studio ${data.latest_version} is available. Installed: ${data.current_version}.`:'Check for updates';
    if(startup&&data.update_available&&!$('updates-dialog').open)startupUpdatePending=true;
    if(!data.update_available)startupUpdatePending=false;
    $('updates-notes-title').textContent=`Release notes / ${data.latest_version}`;
    $('updates-notes-body').textContent=data.release_notes||'No release notes were provided for this release.';
    $('updates-notes').hidden=false;
    if(active){showStartupUpdate();return;}
    $('updates-status').textContent=data.update_available?`Version ${data.latest_version} is available. You have ${data.current_version}.`+(data.download_available?'':' A verified installer is not available yet.'):`You are up to date. Installed version: ${data.current_version}.`;
    $('updates-download').hidden=!data.update_available||!data.download_available;
    $('updates-download').disabled=false;
    showStartupUpdate();
  }catch(error){$('updates-status').textContent=error.message;}
  finally{$('updates-check').disabled=updateJob.state==='downloading';}
}
$('updates-open').onclick=()=>{startupUpdatePending=false;if(!$('updates-dialog').open)$('updates-dialog').showModal();checkUpdates(false,true);};
$('updates-check').onclick=()=>checkUpdates(false,true);
checkUpdates(true);
$('updates-download').onclick=async()=>{
  $('updates-download').disabled=true;
  try{showUpdateJob(await(await api('/api/updates/download',{method:'POST'})).json());}
  catch(error){$('updates-status').textContent=error.message;$('updates-download').disabled=false;}
};
$('updates-install').onclick=async()=>{
  if(!confirm('Save your draft and close Studio to install the update? Your saved data will be kept.'))return;
  $('updates-install').disabled=true;
  try{await window.studioEditor?.saveBeforeUpdate();showUpdateJob(await(await api('/api/updates/install',{method:'POST'})).json());}
  catch(error){$('updates-status').textContent=error.message;}
  finally{$('updates-install').disabled=false;}
};
setInterval(async()=>{
  if(updateJob.state!=='downloading')return;
  try{showUpdateJob(await(await api('/api/updates/status')).json());}
  catch(error){$('updates-status').textContent=error.message;}
},1000);
