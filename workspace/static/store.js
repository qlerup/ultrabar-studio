'use strict';
(()=>{
  let packages=[],installed=[],manualPackages=[],job=null,pending=null,loading=false,opened=false;
  let manualPreview=null,manualBusy=false,manualGeneration=0;
  let pendingDeploy={},pendingInfo=null,progressId=null,progressDevice=null,pollingJob=false;
  const dismissedJobs=new Set();
  const iconCache=new Map();
  const statsCache=new Map(),visibleStats=new Set(),statsPackages=new Map();let fetchingStats=false;
  const statsKey=p=>p.id+'|'+p.artifact?.url+'|'+p.links?.repository;
  const needsStats=p=>{const value=statsCache.get(statsKey(p));return !value||value.loading||Date.now()-value.checked>60000;};
  function paintStats(){for(const box of document.querySelectorAll('.store-badges')){const p=statsPackages.get(box.dataset.id);if(!p)continue;const value=statsCache.get(statsKey(p));for(const [kind,label] of [['downloads','Downloads'],['issues','Open issues']]){const badge=box.querySelector('[data-stat="'+kind+'"]');const number=value?.[kind];badge.textContent=label+' '+(Number.isInteger(number)?number.toLocaleString():'—');badge.title=kind==='downloads'?'GitHub downloads of the currently published package file; includes repeat and automated downloads.':'Open GitHub issues in this app’s repository; pull requests are excluded.';if(!value||value.loading)badge.title+=' Loading counts…';else if(value.stale)badge.title+=' Published counts are temporarily unavailable or delayed; showing the last known count when available.';}}}
  async function loadStats(){if(fetchingStats||!opened||document.hidden)return;const ids=[...visibleStats].filter(id=>statsPackages.has(id)&&needsStats(statsPackages.get(id))).slice(0,12);if(!ids.length)return;fetchingStats=true;try{const data=await(await api('/api/store/stats?ids='+encodeURIComponent(ids.join(',')))).json();for(const [id,value] of Object.entries(data.packages||{})){statsCache.set(id+'|'+value.artifact+'|'+value.repository,{...value,checked:Date.now()});}paintStats();}catch(_){/* Counts must never block installing or browsing packages. */}finally{fetchingStats=false;}}
  const statsObserver=new IntersectionObserver(entries=>{for(const entry of entries){if(entry.isIntersecting)visibleStats.add(entry.target.dataset.id);else visibleStats.delete(entry.target.dataset.id);}loadStats();},{rootMargin:'100px'});
  async function showIcon(p,box){
    if(!p.icon?.sha256)return;
    const hash=p.icon.sha256;
    try{if(!iconCache.has(hash))iconCache.set(hash,api('/api/store/icons/'+hash).then(r=>r.blob()).then(b=>URL.createObjectURL(b)).catch(e=>{iconCache.delete(hash);throw e;}));const url=await iconCache.get(hash);if(!box.isConnected)return;const img=el('img','');img.src=url;img.alt='';img.width=72;img.height=72;box.replaceChildren(img);}
    catch(_){box.title='Icon unavailable';}
  }
  const status=(text,error=false)=>{$('store-status').textContent=text;$('store-status').classList.toggle('error',error);};
  const version=v=>v.split('.').map(Number);
  const newer=(a,b)=>{a=version(a);b=version(b);for(let i=0;i<3;i++){if(a[i]!==b[i])return a[i]>b[i];}return false;};
  function record(p){return installed.find(i=>i.id===p.id&&!i.device_id)||installed.find(i=>p.id==='studio.bambu'&&i.id==='studio.bambu.widget'&&!i.device_id&&i.type==='corebar-widget'&&i.source?.startsWith('https://github.com/qlerup/ultrabar-bambu/blob/'));}
  function render(){
    $('store-device').textContent=snapshot?`Selected CoreBAR: ${snapshot.model} / ${snapshot.target}`:'No CoreBAR connected. Apps and widgets can still be installed into your library on this PC.';
    const box=$('store-packages');statsObserver.disconnect();visibleStats.clear();statsPackages.clear();box.replaceChildren();
    const query=$('store-search').value.trim().toLowerCase(),filter=$('store-filter').value;
    const all=[...new Map([...packages,...manualPackages].map(p=>[p.id,p])).values()];for(const p of installed){if(p.id==='studio.bambu.widget'&&all.some(x=>x.id==='studio.bambu')&&p.source?.startsWith('https://github.com/qlerup/ultrabar-bambu/blob/'))continue;if(!p.device_id&&!all.some(x=>x.id===p.id))all.push({...p,description:p.origin==='local'?'Local development package. Select its folder again to install a new build.':'Installed package is no longer listed in the current catalog.',unlisted:true});}
    const visible=all.filter(p=>(p.name+' '+p.description).toLowerCase().includes(query)&&(filter==='all'||filter===p.type||filter==='installed'&&record(p)));
    $('store-local-folder').disabled=job?.state==='running';
    for(const p of visible){
      const card=el('article','store-card'),saved=record(p),active=job?.state==='running';
      card.dataset.packageId=p.id;
      const heading=el('div','store-card-heading'),icon=el('div','store-card-icon',p.name.slice(0,1).toUpperCase()),title=el('div','store-card-title');
      title.append(el('span','eyebrow',p.type==='corebar-app'?'CORE APP':p.type==='studio-plugin'?'PRESET':'CORE WIDGET'),el('h2','',p.name));heading.append(icon,title);
      title.append(el('p','muted store-publisher',p.origin==='local'?'MANUAL APP / Not Store reviewed':p.publisher?'Uploaded by @'+p.publisher:'Uploader unavailable'));
      card.append(heading,el('p','store-card-description',p.description),el('p','muted',`Version ${p.version}${saved?' / In library: '+saved.version:''}`));
      if(pendingDeploy[p.id]){const notice=el('p','store-deploy-notice','Available in your library. Deploy required on Core.');notice.setAttribute('role','status');card.append(notice);}
      if(p.type==='corebar-app')card.append(el('p','muted','Install into your library. Add the app to your Core layout, then Deploy to install it on CoreBAR.'));
      let badges=null;if(p.links?.repository&&p.artifact?.url){badges=el('div','store-badges');badges.dataset.id=p.id;badges.setAttribute('aria-live','polite');for(const kind of ['downloads','issues']){const badge=el('span','store-stat');badge.dataset.stat=kind;badges.append(badge);}statsPackages.set(p.id,p);card.append(badges);}
      if(p.license)card.append(el('p','muted','License: '+p.license));
      if(p.compatibility)card.append(el('p','muted',`Requires Studio ${p.compatibility.minStudioVersion}+${p.compatibility.models?.length?' / '+p.compatibility.models.join(', '):''}`));
      const tools=el('div','editor-buttons');
      if(!p.unlisted){
        const b=el('button','primary',saved?(newer(p.version,saved.version)?'Update':'Installed'):'Install');
        b.disabled=active||Boolean(saved&&!newer(p.version,saved.version));
        b.title='Installs or updates the library on this PC. Deploy applies it to Core.';
        b.onclick=()=>confirmInstall(p);tools.append(b);
      }
      if(saved){
        if(pendingDeploy[p.id]){const deploy=el('button','','Review & deploy');deploy.disabled=active;deploy.onclick=()=>openDeploy(snapshot?.device_id);tools.append(deploy);}
        const remove=el('button','','Remove from library');remove.disabled=active;
        remove.onclick=async()=>{if(!confirm('Remove this package from the library? Existing draft and deployed widgets are kept. Remove them from your layout and Deploy to remove them from Core.'))return;try{await api('/api/store/remove-plugin',{method:'POST',body:JSON.stringify({id:p.id})});await local();window.dispatchEvent(new Event('studio-store-changed'));status('Package removed from library.');}catch(e){status(e.message,true);}};tools.append(remove);
      }
      card.append(tools);
      if(p.links?.repository){const links=el('nav','store-links');links.setAttribute('aria-label',p.name+' on GitHub');for(const [kind,label] of [['repository','Repository'],['issues','Issues'],['pulls','Pull requests']]){if(!p.links[kind])continue;const a=el('a','',label);a.href=p.links[kind];a.target='_blank';a.rel='noopener noreferrer';a.onclick=async e=>{e.preventDefault();try{await api('/api/store/open-link',{method:'POST',body:JSON.stringify({id:p.id,kind})});}catch(error){status(error.message,true);}};links.append(a);}card.append(links);}
      box.append(card);showIcon(p,icon);if(badges)statsObserver.observe(badges);
    }
    if(!visible.length)box.append(el('p','store-empty',packages.length?'No matching packages.':'No approved packages yet. New submissions appear here after the owner merges them into the store catalog.'));
    paintStats();
  }
  async function local(){const d=await(await api('/api/store/installed')).json();installed=d.installed||[];manualPackages=d.manual||[];job=d.job;pendingDeploy=d.pending_deploy||{};render();}
  async function refresh(){
    if(loading)return;loading=true;$('store-refresh').disabled=true;
    if(job?.state!=='running')status('Refreshing approved catalog...');
    try{const d=await(await api('/api/store')).json();packages=d.packages||[];installed=d.installed||[];manualPackages=d.manual||[];job=d.job;pendingDeploy=d.pending_deploy||{};render();if(job?.state==='running'&&job.is_update)showUpdate(job);status(job?.state==='running'?job.message:Object.keys(pendingDeploy).length?'Library packages are waiting for Deploy on this Core.':'Catalog up to date.');}
    catch(e){try{await local();}catch(_){}status(e.message+' Previously loaded packages are retained.',true);}
    finally{loading=false;$('store-refresh').disabled=false;}
  }
  function confirmInstall(p){
    pendingInfo={name:p.name,version:p.version,is_update:Boolean(record(p)&&newer(p.version,record(p).version))};
    pending={id:p.id,version:p.version,sha256:p.artifact.sha256};
    if(p.origin==='local')pending.local=true;
    if(p.localToken){pending.token=p.localToken;pending.local=true;}
    const box=$('store-install-summary');box.replaceChildren(el('p','',p.name+' '+p.version),el('p','',p.type==='corebar-app'?'Add this app to your Studio library on this PC. No CoreBAR connection is needed. Add its widget to your layout and Deploy to install the app on Core.':p.type==='corebar-widget'?'Add this package to Studio & App Store. Drag a widget onto the bar, edit its settings, then Deploy to activate it on Core.':'Install widget presets on this PC.'),el('p','',p.permissions.length?'Permissions on Core during Deploy: '+p.permissions.join(', '):'Permissions: none'),el('p','muted','License: '+p.license));
    if(p.origin==='local')box.prepend(el('p','','Local development package. This folder has not been reviewed by the Store. Local widgets use a separate library identity; an APK updates the same Android app if already installed.'));
    if(p.id==='studio.vivo.screensync'||p.original_id==='studio.vivo.screensync')box.append(el('p','', 'During Deploy, setup uses root ADB and your existing approved Studio bridge connection to configure online VivoCubes. Existing app preferences are preserved. Open the widget and choose Follow Core to enable syncing.'));
    $('store-install-title').textContent=pendingInfo.is_update?'Update package?':'Install package?';$('store-install-confirm').textContent=pendingInfo.is_update?'Update':'Install';
    $('store-install-dialog').showModal();
  }
  function showUpdate(value){
    const id=value.request_id||progressId;
    if(id&&dismissedJobs.has(id))return;
    if(id&&progressId!==id){progressId=id;progressDevice=snapshot?.device_id||null;}
    const box=$('store-progress'),running=value.state==='running',failed=value.state==='error';
    box.dataset.state=running?'running':failed?'error':'success';box.setAttribute('aria-busy',String(running));
    $('store-progress-title').textContent=running?'Updating package':failed?'Update interrupted':'Update ready to deploy';
    $('store-progress-package').textContent=[value.name,value.version].filter(Boolean).join(' · ');
    $('store-progress-message').textContent=running?value.message:failed?value.message:'The update is ready in your library on this PC. Core has not been updated yet.';
    $('store-progress-help').textContent=running?'Downloading and checking the package. Keep Studio open.':failed?'The update was not confirmed. Check the message and retry.':'Deploy to apply the update to Core. New settings may only work on the device after Deploy. Existing widget settings are preserved. If the package is not in your layout yet, add it first. Deploy now opens your draft for review.';
    $('store-progress-spinner').hidden=!running;$('store-progress-later').disabled=running;$('store-progress-later').textContent=running?'Updating…':failed?'Close':'Later';
    $('store-progress-deploy').hidden=running||failed;
    if(!box.open)box.showModal();
  }
  async function openDeploy(device,reopen=false){
    try{await window.studioEditor.deployFromStore(device);}
    catch(error){status(error.message,true);if(reopen&&progressId&&job?.state==='complete'){$('store-progress').showModal();$('store-progress-message').textContent=error.message;}}
  }
  $('store-progress').addEventListener('cancel',event=>{if($('store-progress-later').disabled)event.preventDefault();});
  $('store-progress').addEventListener('close',()=>{if(progressId)dismissedJobs.add(progressId);});
  $('store-progress-later').onclick=()=>$('store-progress').close();
  $('store-progress-deploy').onclick=()=>{$('store-progress').close();openDeploy(progressDevice,true);};
  $('store-install-confirm').onclick=async()=>{const body=pending,info=pendingInfo;if(!body)return;pending=null;pendingInfo=null;$('store-install-dialog').close();
    if(info?.is_update){progressId=null;progressDevice=snapshot?.device_id||null;showUpdate({...info,state:'running',message:'Starting update…'});}
    try{job=await(await api(body.local?'/api/store/local/install':'/api/store/install',{method:'POST',body:JSON.stringify(body)})).json();status(job.message);render();if(info?.is_update)showUpdate({...info,...job});if(job?.state!=='running'){await local();window.dispatchEvent(new Event('studio-store-changed'));}}
    catch(e){status(e.message,true);if(info?.is_update)showUpdate({...info,state:'error',message:e.message});}
  };
  function manualControls(){
    $('manual-folder-browse').disabled=manualBusy;$('manual-folder-path').disabled=manualBusy;
    $('manual-folder-check').disabled=manualBusy||!$('manual-folder-path').value.trim();
    $('manual-app-add').disabled=manualBusy||!manualPreview;
  }
  function clearManualPreview(text,error=false){manualPreview=null;$('manual-app-results').hidden=true;$('manual-app-status').textContent=text;$('manual-app-status').classList.toggle('error',error);manualControls();}
  $('store-local-folder').onclick=()=>{
    manualGeneration++;manualBusy=false;$('manual-folder-path').value='';$('manual-app-add').textContent='Add manual app';
    clearManualPreview('Choose a folder to get started.');$('manual-app-dialog').showModal();
  };
  $('manual-app-dialog').addEventListener('close',()=>{manualGeneration++;manualBusy=false;manualPreview=null;});
  $('manual-folder-path').oninput=()=>{clearManualPreview('Check this folder before adding the package.');};
  async function checkManualFolder(browse=false){
    if(manualBusy)return;
    const generation=++manualGeneration;manualBusy=true;clearManualPreview(browse?'Choose a package folder…':'Checking package files…');
    try{
      const body=browse?{}:{folder:$('manual-folder-path').value.trim()};
      const data=await(await api('/api/store/local/preview',{method:'POST',body:JSON.stringify(body),signal:null})).json();
      if(generation!==manualGeneration)return;
      if(data.cancelled){clearManualPreview('Folder selection cancelled. You can choose another folder.');return;}
      manualPreview=data;
      $('manual-package-title').textContent=data.package.name;
      $('manual-package-kind').textContent=data.package.type==='corebar-app'?'CORE APP':data.package.type==='corebar-widget'?'CORE WIDGET':'PRESET';
      $('manual-package-version').textContent='Version '+data.package.version+' · '+data.folder_name;
      const checks=$('manual-app-checks');checks.replaceChildren();
      for(const check of data.checks||[]){const item=el('li',''),icon=el('span','manual-check-icon','✓'),copy=el('div','');icon.setAttribute('aria-hidden','true');copy.append(el('strong','',check.label),el('p','muted',check.detail));item.append(icon,copy);checks.append(item);}
      const c=data.package.compatibility;
      $('manual-app-requirements').textContent='Core requirements'+(c.models?.length?': '+c.models.join(', '):'')+(c.lineosVersions?.length?' · LineOS '+c.lineosVersions.join(' / '):'')+'. Device compatibility is verified during Deploy; CoreBAR is not needed to add this package.';
      $('manual-app-status').textContent='Checks passed. Ready to add to your manual apps.';
      $('manual-app-results').hidden=false;
      $('manual-app-add').textContent=data.package.type==='corebar-widget'?'Add manual widget':data.package.type==='studio-plugin'?'Add manual preset':'Add manual app';
    }catch(error){if(generation===manualGeneration)clearManualPreview(error.message,true);}
    finally{if(generation===manualGeneration){manualBusy=false;manualControls();}}
  }
  $('manual-folder-browse').onclick=()=>checkManualFolder(true);
  $('manual-folder-form').onsubmit=event=>{event.preventDefault();checkManualFolder();};
  $('manual-app-add').onclick=async()=>{
    if(manualBusy||!manualPreview)return;
    const generation=manualGeneration,preview=manualPreview;manualBusy=true;manualControls();$('manual-app-status').textContent='Adding manual app…';
    try{
      await api('/api/store/local/add',{method:'POST',body:JSON.stringify({token:preview.token})});
      if(generation!==manualGeneration)return;
      $('store-filter').value='all';$('store-search').value='';await local();$('manual-app-dialog').close();
      status('Manual app added. Choose Install on its card to add it to your library.');
      [...document.querySelectorAll('.store-card')].find(card=>card.dataset.packageId===preview.package.id)?.scrollIntoView({block:'center',behavior:'smooth'});
    }catch(error){if(generation===manualGeneration)clearManualPreview(error.message,true);}
    finally{if(generation===manualGeneration){manualBusy=false;manualControls();}}
  };
  $('store-install-cancel').onclick=()=>{pending=null;$('store-install-dialog').close();};
  $('store-refresh').onclick=refresh;$('store-search').oninput=render;$('store-filter').onchange=render;
  $('nav-store').onclick=()=>{opened=true;document.body.classList.remove('editing');document.body.classList.add('store-open');$('store-content').hidden=false;for(const id of ['nav-overview','nav-editor']){$(id).classList.remove('nav-active');$(id).setAttribute('aria-pressed','false');}$('nav-store').classList.add('nav-active');$('nav-store').setAttribute('aria-pressed','true');refresh();};
  window.studioStore={leave(){opened=false;document.body.classList.remove('store-open');$('store-content').hidden=true;$('nav-store').classList.remove('nav-active');$('nav-store').setAttribute('aria-pressed','false');}};
  setInterval(async()=>{
    if(!opened||document.hidden||job?.state!=='running'||pollingJob)return;pollingJob=true;
    try{const d=await(await api('/api/store/job')).json();job=d.job;status(job?.message||'',job?.state==='error');if(job?.is_update)showUpdate(job);if(job?.state!=='running'){await local();window.dispatchEvent(new Event('studio-store-changed'));render();}}catch(e){status(e.message,true);if($('store-progress').open){$('store-progress-message').textContent='Update status is unavailable. The update may still be running. Studio will keep checking.';$('store-progress-later').disabled=false;$('store-progress-later').textContent='Close';}}finally{pollingJob=false;}
  },1000);
  setInterval(()=>{if(opened&&!document.hidden&&job?.state!=='running')refresh();},60000);
  setInterval(loadStats,3000);
})();
