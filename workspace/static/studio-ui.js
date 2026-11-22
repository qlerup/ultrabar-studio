'use strict';
// Reviewed packages own descriptions; Studio owns DOM, transport and lifecycle.
window.studioPackageUI=(()=>{
  const node=(tag,cls,text)=>{const n=document.createElement(tag);if(cls)n.className=cls;if(text!==undefined)n.textContent=text;return n;};
  const button=(label,run,cls='')=>{const b=node('button',cls,label);b.type='button';b.onclick=run;return b;};
  const option=(select,value,label)=>{const o=node('option','',label);o.value=value;select.append(o);};
  function fields(panel,schema,values,changed,{sources={},metrics={},prefix='setting'}={}){
    for(const field of schema.fields){
      const value=values[field.key]??field.default;
      const source=sources[field.key],choices=source==='pc.drives'?[{value:'all',label:'All drives (2 at a time)'},...[...new Set([...(metrics.disks||[]).map(d=>d.name),value].filter(v=>v&&v!=='all'))].map(value=>({value,label:value.slice(0,2)}))]:field.options;
      const wrap=node('label','property-field'+(field.type==='boolean'?' app-setting-toggle':''),field.label),input=node(choices?'select':'input');
      input.id=prefix+'-'+field.key;input.dataset.setting=field.key;if(prefix==='app-setting')input.dataset.appSetting=field.key;
      if(choices){for(const choice of choices)option(input,choice.value,choice.label);input.value=value;}
      else if(field.type==='boolean'){input.type='checkbox';input.checked=value;}
      else{input.type=['integer','number'].includes(field.type)?'number':field.type==='url'?'url':'text';input.value=value;if(field.maxLength)input.maxLength=field.maxLength;if(field.min!=null){input.min=field.min;input.max=field.max;input.step=field.step;input.required=true;}}
      input.onchange=()=>{if(!input.checkValidity()){input.reportValidity();return;}changed(field.key,field.type==='boolean'?input.checked:['integer','number'].includes(field.type)?Number(input.value):input.value);};
      wrap.append(input);if(field.help)wrap.append(node('small','muted',field.help));panel.append(wrap);
    }
  }
  function create({api,onConnectionsChange,onError}){
    const cache=new Map(),loading=new Set(),previewRequests=new Set(),thumbnails=new Map();
    // Connection records are owned/shared by the trusted provider, not a widget.
    // Requests still authenticate the installed package/widget at the endpoint.
    const identity=b=>b.descriptor.connection.provider;
    const endpoint=(b,op)=>'/api/studio/integrations/'+encodeURIComponent(b.packageId)+'/'+encodeURIComponent(b.widgetKey)+'/'+op;
    const call=async(b,op,body)=>{const response=await api(endpoint(b,op),op==='list'?{}:{method:'POST',body:JSON.stringify(body||{})});return response.json();};
    const remember=(b,data)=>{if(data.items)cache.set(identity(b),data.items);};
    async function load(b,background=false){
      const key=identity(b);if(loading.has(key))return;loading.add(key);
      try{remember(b,await call(b,'list'));onConnectionsChange();}catch(e){if(!background)onError(e.message);}finally{loading.delete(key);}
    }
    function picker(panel,b,values,changed){
      const config=b.descriptor.connection,key=identity(b),items=cache.get(key)||[];
      const wrap=node('label','property-field',config.label),select=node('select');select.dataset.connectionKey=config.key;
      option(select,'','Choose a '+config.itemLabel);for(const item of items)option(select,item.id,item.name);
      if(values[config.key]&&!items.some(item=>item.id===values[config.key]))option(select,values[config.key],'Unavailable '+config.itemLabel+' - choose another');
      select.value=values[config.key]||'';select.onchange=()=>changed(config.key,select.value);wrap.append(select);panel.append(wrap,button(config.manageLabel,()=>manage(b),'studio-manage-connections'));
      if(!cache.has(key)&&!loading.has(key))load(b);
    }
    function manage(b){
      const config=b.descriptor.connection,dialog=node('dialog','studio-connections-dialog');dialog.id='studio-connections';
      const heading=node('div','studio-connections-heading');heading.append(node('h3','',config.title),button('Close',()=>dialog.close()));
      const notice=node('p','muted studio-connection-notice');notice.setAttribute('role','status');
      const list=node('div','studio-connection-list'),form=node('form','studio-connection-form');
      dialog.append(heading,node('p','muted','Connections belong to this app on this PC. Access codes are protected by your Windows account and are never sent to Core.'),notice,list,form);
      let editing=null,pending=null,saving=false,polling=false,timer=null;
      const message=(text,error=false)=>{notice.textContent=text;notice.classList.toggle('error',error);};
      const items=()=>cache.get(identity(b))||[];
      function updateRowStatus(row,item){
        const status=row.querySelector('.studio-connection-status');
        status.textContent=item.status?.connection||'Not connected';
        status.classList.toggle('is-connected',status.textContent==='Connected');
        row.querySelector('.studio-connection-host').textContent=item.host;
      }
      async function refresh(live=false){
        const previous=cache.get(identity(b));
        const data=await call(b,'list');if(!dialog.open||(live&&(saving||previous!==cache.get(identity(b)))))return;remember(b,data);
        const rows=[...list.querySelectorAll('.studio-connection-row')];
        if(!live||rows.length!==items().length||rows.some(row=>!items().some(item=>item.id===row.dataset.connectionId)))renderList();
        else for(const row of rows)updateRowStatus(row,items().find(item=>item.id===row.dataset.connectionId));
      }
      async function poll(){
        if(polling)return;polling=true;
        try{if(dialog.open&&!saving)await refresh(true);}catch(e){if(dialog.open)message(e.message,true);}
        finally{polling=false;if(dialog.open)timer=setTimeout(poll,2000);}
      }
      function renderList(){
        list.replaceChildren();
        if(!items().length)list.append(node('p','muted','No connections yet. Add your first '+config.itemLabel+' below.'));
        for(const item of items()){
          const row=node('section','studio-connection-row');row.dataset.connectionId=item.id;
          const summary=node('div','studio-connection-summary');
          summary.append(node('strong','',item.name),node('span','studio-connection-status'),node('span','muted studio-connection-host'));
          row.append(summary);updateRowStatus(row,item);
          const actions=node('div','studio-connection-actions');actions.append(button('Edit',()=>edit(item)),button('Reconnect',async()=>{
            try{remember(b,await call(b,'reconnect',{id:item.id}));if(dialog.open){renderList();message('Reconnect requested. Status updates automatically.');}}catch(e){if(dialog.open)message(e.message,true);}
          }),button('Remove',async()=>{
            if(!confirm('Remove '+item.name+'? Widgets using this connection will need another selection.'))return;
            try{remember(b,await call(b,'remove',{id:item.id}));if(dialog.open){if(editing?.id===item.id)edit(null);renderList();}}catch(e){if(dialog.open)message(e.message,true);}
          },'danger-quiet'));row.append(actions);list.append(row);
        }
        const tools=node('div','studio-connection-tools');
        tools.append(button('Add '+config.itemLabel,()=>edit(null)),button('Refresh status',async()=>{try{await refresh();}catch(e){message(e.message,true);}}));
        list.append(tools);
      }
      function edit(item){
        if(saving)return;editing=item;pending=null;message('');form.replaceChildren(node('h4','',(item?'Edit ':'Add ')+config.itemLabel));
        const inputs={};
        const discoveryKeys=new Set(['name','host','serial']);
        const fields=[...config.fields.filter(field=>discoveryKeys.has(field.key)),...config.fields.filter(field=>!discoveryKeys.has(field.key))];
        for(const field of fields){
          const wrap=node('label','property-field',field.label),input=node(field.type==='choice'?'select':'input');input.dataset.connectionField=field.key;input.id='connection-'+field.key;
          const printerModel=config.provider==='bambu-lan'&&field.key==='model';
          if(field.type==='choice'){
            if(printerModel)option(input,'','Choose a printer model');
            for(const choice of field.options)if(!printerModel||choice.value!=='generic')option(input,choice.value,choice.label);
          }
          else input.type=field.type==='secret'?'password':field.type==='boolean'?'checkbox':'text';
          if(field.type==='boolean')input.checked=!!item?.[field.key];
          else if(field.type==='choice')input.value=[...input.options].some(o=>o.value===item?.[field.key])?item[field.key]:input.options[0].value;
          else input.value=field.type==='secret'?'':item?.[field.key]||'';
          input.required=(printerModel||!!field.required)&&!(field.type==='secret'&&item);input.autocomplete='off';if(field.maxLength)input.maxLength=field.maxLength;
          wrap.append(input);if(field.type==='secret'&&item)wrap.append(node('small','muted','Leave blank to keep the saved value.'));if(field.help)wrap.append(node('small','muted',field.help));form.append(wrap);inputs[field.key]=input;
        }
        if(config.setupHelp)form.append(node('p','muted',config.setupHelp));
        const discovery=node('div','studio-connection-discovery');
        const search=button('Search local network',async()=>{
          const picker=node('dialog','studio-connections-dialog studio-discovery-dialog');
          const title=node('h3','','Search local network');title.id='studio-discovery-title';
          picker.setAttribute('aria-labelledby',title.id);
          const state=node('p','muted','Searching local network…');state.setAttribute('role','status');
          const results=node('div','studio-search-results');
          let selected=null;
          const add=button('Use printer',()=>{
            for(const key of discoveryKeys)if(inputs[key]&&typeof selected[key]==='string')inputs[key].value=selected[key];
            resetApproval();picker.close();
          },'primary');
          add.disabled=true;
          const actions=node('div','studio-discovery-actions');
          actions.append(button('Cancel',()=>picker.close()),add);
          picker.append(title,state,results,actions);
          picker.addEventListener('close',()=>picker.remove(),{once:true});
          dialog.append(picker);picker.showModal();
          try{
            const data=await call(b,'discover');if(!picker.open)return;
            state.textContent=data.items?.length?'':'No devices found. You can enter the address and serial manually.';
            for(const found of data.items||[]){
              const choice=node('label','studio-discovery-choice'),radio=node('input');
              radio.type='radio';radio.name='studio-discovered-device';
              radio.onchange=()=>{selected=found;add.disabled=false;};
              const details=node('span','studio-discovery-details');
              details.append(node('strong','',found.name),node('span','muted',found.host+' · '+found.serial));
              choice.append(radio,details);results.append(choice);
            }
          }catch(e){if(picker.open)state.textContent=e.message;}
        });
        search.setAttribute('aria-haspopup','dialog');
        discovery.append(search);form.insertBefore(discovery,form.children[1]||null);
        const submitLabel=item?'Save changes':'Add';
        const approval=node('section','studio-certificate');approval.hidden=true;const submit=node('button','primary',submitLabel);submit.type='submit';form.append(approval,submit);
        function updateSubmit(){submit.disabled=saving||Object.values(inputs).some(input=>input.tagName==='SELECT'&&input.required&&!input.value);}
        function resetApproval(){pending=null;approval.hidden=true;submit.textContent=submitLabel;updateSubmit();}
        for(const input of Object.values(inputs))input.addEventListener('input',resetApproval);
        updateSubmit();
        form.onsubmit=async event=>{
          event.preventDefault();if(saving)return;saving=true;submit.disabled=true;search.disabled=true;message('');
          const candidate=Object.fromEntries(config.fields.map(field=>[field.key,field.type==='boolean'?inputs[field.key].checked:field.type==='secret'?inputs[field.key].value:inputs[field.key].value.trim()]));if(editing)candidate.id=editing.id;
          for(const input of Object.values(inputs))input.disabled=true;
          try{
            const keepConnection=config.provider==='bambu-lan'&&item&&candidate.host===item.host&&candidate.serial===item.serial&&!candidate.code;
            if(!pending&&!keepConnection){
              const result=await call(b,'probe',{host:candidate.host});if(!dialog.open)return;
              pending={...candidate,pin:result.pin};approval.replaceChildren(node('strong','','Approve device certificate'),node('p','muted','Compare this SHA-256 fingerprint with a trusted connection before sending the access code.'),node('code','studio-fingerprint',result.pin));approval.hidden=false;submit.textContent=item?'Trust certificate & save':'Trust certificate & add';
            }else{
              const result=await call(b,'save',pending||candidate);remember(b,result);if(!dialog.open)return;
              for(const field of config.fields)if(field.type==='secret')inputs[field.key].value='';pending=null;renderList();saving=false;edit(null);message('Connection saved. Choose it for a widget, then Save and Deploy.');
            }
          }catch(e){if(dialog.open)message(e.message,true);}
          finally{saving=false;search.disabled=false;for(const input of Object.values(inputs))input.disabled=false;updateSubmit();}
        };
      }
      renderList();edit(null);document.body.append(dialog);
      dialog.addEventListener('close',()=>{clearTimeout(timer);pending=null;form.replaceChildren();dialog.remove();onConnectionsChange();});dialog.showModal();poll();
    }
    function presentation(binding,values){
      const config=binding?.descriptor?.presentation;if(!config)return {};
      const source=config.source,connection=binding.descriptor.connection;
      if(source.scope==='setting')return config.presets.find(preset=>preset.value===values[source.key])||{};
      const key=identity(binding),items=cache.get(key);
      if(!items&&values[connection.key]&&!previewRequests.has(key)){
        previewRequests.add(key);load(binding,true);
      }
      const device=items?.find(item=>item.id===values[connection.key]);
      const preset=config.presets.find(preset=>preset.value===device?.[source.key]);
      const preview={...preset,connectionName:device?.name};
      const thumbnail=device?.thumbnail;
      if(!preset||!thumbnail||!/^[A-Za-z0-9+/]{1,8192}={0,2}$/.test(thumbnail)||thumbnail.length%4)return preview;
      if(!thumbnails.has(thumbnail)){
        const bytes=Uint8Array.from(atob(thumbnail),character=>character.charCodeAt(0));
        thumbnails.set(thumbnail,URL.createObjectURL(new Blob([bytes],{type:'image/png'})));
      }
      return {...preview,imageUrl:thumbnails.get(thumbnail)};
    }
    return {picker,presentation,preview:(binding,ids)=>call(binding,'preview',{ids}),clear:()=>{
      cache.clear();previewRequests.clear();
      for(const url of thumbnails.values())URL.revokeObjectURL(url);
      thumbnails.clear();
    }};
  }
  function artwork(parent,shapes){
    if(!shapes?.length)return;
    const ns='http://www.w3.org/2000/svg',svg=document.createElementNS(ns,'svg');svg.setAttribute('viewBox','0 0 100 100');svg.setAttribute('aria-hidden','true');svg.classList.add('package-artwork');
    for(const shape of shapes){const p=shape.points,node=document.createElementNS(ns,shape.type==='polygon'?'polygon':shape.type==='oval'?'ellipse':'rect');
      node.setAttribute('fill',shape.fill==='accent'?'var(--widget-accent)':shape.fill);
      const attrs=shape.type==='polygon'?{points:p.reduce((s,v,i)=>s+(i?' ':'')+v,'')}:shape.type==='oval'?{cx:(p[0]+p[2])/2,cy:(p[1]+p[3])/2,rx:(p[2]-p[0])/2,ry:(p[3]-p[1])/2}:{x:p[0],y:p[1],width:p[2]-p[0],height:p[3]-p[1],...(shape.type==='roundRect'?{rx:p[4],ry:p[5]}:{})};
      for(const [key,value] of Object.entries(attrs))node.setAttribute(key,String(value));svg.append(node);
    }parent.append(svg);
  }
  return {fields,create,artwork};
})();
