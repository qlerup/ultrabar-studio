'use strict';
(()=>{
  let packages=[],installed=[],job=null,pending=null,loading=false,opened=false;
  const iconCache=new Map();
  const statsCache=new Map(),visibleStats=new Set(),statsPackages=new Map();let fetchingStats=false;
  const statsKey=p=>p.id+'|'+p.artifact?.url+'|'+p.links?.repository;
  const needsStats=p=>{const value=statsCache.get(statsKey(p));return !value||value.loading||Date.now()-value.checked>60000;};
  function paintStats(){for(const box of document.querySelectorAll('.store-badges')){const p=statsPackages.get(box.dataset.id);if(!p)continue;const value=statsCache.get(statsKey(p));for(const [kind,label] of [['downloads','Downloads'],['issues','Open issues']]){const badge=box.querySelector('[data-stat="'+kind+'"]');const number=value?.[kind];badge.textContent=label+' '+(Number.isInteger(number)?number.toLocaleString():'—');badge.title=kind==='downloads'?'GitHub downloads of the currently published package file; includes repeat and automated downloads.':'Open GitHub issues in this app’s repository; pull requests are excluded.';if(!value||value.loading)badge.title+=' Loading counts…';else if(value.stale)badge.title+=' GitHub is currently unavailable; showing the last known count when available.';}}}
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
  function record(p){return installed.find(i=>i.id===p.id&&(p.type!=='corebar-app'||i.device_id===snapshot?.device_id));}
  function render(){
    $('store-device').textContent=snapshot?`Selected CoreBAR: ${snapshot.model} / ${snapshot.target}`:'No CoreBAR connected. Studio plugins can still be installed on this PC.';
    const box=$('store-packages');statsObserver.disconnect();visibleStats.clear();statsPackages.clear();box.replaceChildren();
    const query=$('store-search').value.trim().toLowerCase(),filter=$('store-filter').value;
    const all=packages.slice();for(const p of installed){if(!all.some(x=>x.id===p.id)&&(p.type!=='corebar-app'||p.device_id===snapshot?.device_id))all.push({...p,description:p.origin==='local'?'Local development package. Select its folder again to install a new build.':'Installed package is no longer listed in the current catalog.',unlisted:true});}
    const visible=all.filter(p=>(p.name+' '+p.description).toLowerCase().includes(query)&&(filter==='all'||filter===p.type||filter==='installed'&&record(p)));
    $('store-local-folder').disabled=job?.state==='running';
    for(const p of visible){
      const card=el('article','store-card'),saved=record(p),active=job?.state==='running';
      const heading=el('div','store-card-heading'),icon=el('div','store-card-icon',p.name.slice(0,1).toUpperCase()),title=el('div','store-card-title');
      title.append(el('span','eyebrow',p.type==='corebar-app'?'CORE APP':p.type==='studio-plugin'?'PRESET':'CORE WIDGET'),el('h2','',p.name));heading.append(icon,title);
      title.append(el('p','muted store-publisher',p.origin==='local'?'LOCAL DEVELOPMENT / Not Store reviewed':p.publisher?'Uploaded by @'+p.publisher:'Uploader unavailable'));
      card.append(heading,el('p','store-card-description',p.description),el('p','muted',`Version ${p.version}${saved?' / Installed: '+saved.version:''}`));
      let badges=null;if(p.links?.repository&&p.artifact?.url){badges=el('div','store-badges');badges.dataset.id=p.id;badges.setAttribute('aria-live','polite');for(const kind of ['downloads','issues']){const badge=el('span','store-stat');badge.dataset.stat=kind;badges.append(badge);}statsPackages.set(p.id,p);card.append(badges);}
      if(p.license)card.append(el('p','muted','License: '+p.license));
      if(p.compatibility)card.append(el('p','muted',`Requires Studio ${p.compatibility.minStudioVersion}+${p.compatibility.models?.length?' / '+p.compatibility.models.join(', '):''}`));
      const tools=el('div','editor-buttons');
      if(!p.unlisted){
        const b=el('button','primary',saved?(newer(p.version,saved.version)?'Update':p.type==='corebar-app'?'Reinstall':'Installed'):'Install');
        b.disabled=active||Boolean(saved&&p.type!=='corebar-app'&&!newer(p.version,saved.version))||p.type==='corebar-app'&&!snapshot;
        if(p.type==='corebar-app'&&!snapshot)b.textContent='Connect CoreBAR to install';
        b.onclick=()=>confirmInstall(p);tools.append(b);
      }
      if(saved&&p.type!=='corebar-app'){
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
  async function local(){const d=await(await api('/api/store/installed')).json();installed=d.installed||[];job=d.job;render();}
  async function refresh(){
    if(loading)return;loading=true;$('store-refresh').disabled=true;
    if(job?.state!=='running')status('Refreshing approved catalog...');
    try{const d=await(await api('/api/store')).json();packages=d.packages||[];installed=d.installed||[];job=d.job;render();status(job?.state==='running'?job.message:'Catalog up to date.');}
    catch(e){try{await local();}catch(_){}status(e.message+' Previously loaded packages are retained.',true);}
    finally{loading=false;$('store-refresh').disabled=false;}
  }
  function confirmInstall(p){
    pending={id:p.id,version:p.version,sha256:p.artifact.sha256,device_id:p.type==='corebar-app'?snapshot?.device_id:null};
    if(p.localToken){pending.token=p.localToken;pending.local=true;}
    const box=$('store-install-summary');box.replaceChildren(el('p','',p.name+' '+p.version),el('p','',p.type==='corebar-app'?`Install on CoreBAR ${snapshot?.target}.`:p.type==='corebar-widget'?'Add this package to Studio & App Store. Drag a widget onto the bar, edit its settings, then Deploy to activate it on Core.':'Install widget presets on this PC.'),el('p','',p.permissions.length?'Permissions: '+p.permissions.join(', '):'Permissions: none'),el('p','muted','License: '+p.license));
    if(p.origin==='local')box.prepend(el('p','','Local development package. This folder has not been reviewed by the Store. Local widgets use a separate library identity; an APK updates the same Android app if already installed.'));
    if(p.id==='studio.vivo.screensync')box.append(el('p','', 'Setup uses root ADB to copy your existing approved Studio bridge credential into this app\'s private storage and configure all currently online VivoCubes. Choose Follow Core in the app to enable it. Reinstall refreshes the cube list and preserves your settings.'));
    $('store-install-dialog').showModal();
  }
  $('store-install-confirm').onclick=async()=>{const body=pending;if(!body)return;pending=null;$('store-install-dialog').close();try{job=await(await api(body.local?'/api/store/local/install':'/api/store/install',{method:'POST',body:JSON.stringify(body)})).json();status(job.message);render();}catch(e){status(e.message,true);}};
  $('store-local-folder').onclick=async()=>{const button=$('store-local-folder');button.disabled=true;status('Choose a package folder...');try{const d=await(await api('/api/store/local/preview',{method:'POST',signal:null})).json();if(d.cancelled){status('Folder selection cancelled.');return;}if(d.package.type==='corebar-app'&&!snapshot){status('Connect CoreBAR before installing a local APK.',true);return;}confirmInstall({...d.package,localToken:d.token});}catch(e){status(e.message,true);}finally{button.disabled=job?.state==='running';}};
  $('store-install-cancel').onclick=()=>{pending=null;$('store-install-dialog').close();};
  $('store-refresh').onclick=refresh;$('store-search').oninput=render;$('store-filter').onchange=render;
  $('nav-store').onclick=()=>{opened=true;document.body.classList.remove('editing');document.body.classList.add('store-open');$('store-content').hidden=false;for(const id of ['nav-overview','nav-editor']){$(id).classList.remove('nav-active');$(id).setAttribute('aria-pressed','false');}$('nav-store').classList.add('nav-active');$('nav-store').setAttribute('aria-pressed','true');refresh();};
  window.studioStore={leave(){opened=false;document.body.classList.remove('store-open');$('store-content').hidden=true;$('nav-store').classList.remove('nav-active');$('nav-store').setAttribute('aria-pressed','false');}};
  setInterval(async()=>{
    if(!opened||document.hidden||job?.state!=='running')return;
    try{const d=await(await api('/api/store/job')).json();job=d.job;status(job?.message||'',job?.state==='error');if(job?.state!=='running'){await local();window.dispatchEvent(new Event('studio-store-changed'));render();}}catch(e){status(e.message,true);}
  },1000);
  setInterval(()=>{if(opened&&!document.hidden&&job?.state!=='running')refresh();},60000);
  setInterval(loadStats,3000);
})();
