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
    const cache=new Map(),loading=new Set();
    const identity=b=>b.packageId+'/'+b.widgetKey;
    const endpoint=(b,op)=>'/api/studio/integrations/'+encodeURIComponent(b.packageId)+'/'+encodeURIComponent(b.widgetKey)+'/'+op;
    const call=async(b,op,body)=>{const response=await api(endpoint(b,op),op==='list'?{}:{method:'POST',body:JSON.stringify(body||{})});return response.json();};
    const remember=(b,data)=>{if(data.items)cache.set(identity(b),data.items);};
    async function load(b){
      const key=identity(b);if(loading.has(key))return;loading.add(key);
      try{remember(b,await call(b,'list'));onConnectionsChange();}catch(e){onError(e.message);}finally{loading.delete(key);}
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
      const notice=node('p','muted');notice.setAttribute('role','status');
      const list=node('div','studio-connection-list'),form=node('form','studio-connection-form');
      dialog.append(heading,node('p','muted','Connections belong to this app on this PC. Access codes are protected by your Windows account and are never sent to Core.'),notice,list,form);
      let editing=null,pending=null,saving=false,polling=false,timer=null;
      const message=(text,error=false)=>{notice.textContent=text;notice.classList.toggle('error',error);};
      const items=()=>cache.get(identity(b))||[];
      const status=item=>item.host+' · '+(item.status?.connection||'Not connected');
      async function refresh(live=false){
        const data=await call(b,'list');if(!dialog.open||(live&&saving))return;remember(b,data);
        const rows=[...list.querySelectorAll('.studio-connection-row')];
        if(!live||rows.length!==items().length||rows.some(row=>!items().some(item=>item.id===row.dataset.connectionId)))renderList();
        else for(const row of rows){const item=items().find(item=>item.id===row.dataset.connectionId);row.querySelector('.studio-connection-status').textContent=status(item);}
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
          const row=node('section','studio-connection-row');row.dataset.connectionId=item.id;row.append(node('strong','',item.name),node('p','muted studio-connection-status',status(item)));
          const actions=node('div','property-moves');actions.append(button('Edit',()=>edit(item)),button('Reconnect',async()=>{
            try{remember(b,await call(b,'reconnect',{id:item.id}));if(dialog.open){renderList();message('Reconnect requested. Status updates automatically.');}}catch(e){if(dialog.open)message(e.message,true);}
          }),button('Remove',async()=>{
            if(!confirm('Remove '+item.name+'? Widgets using this connection will need another selection.'))return;
            try{remember(b,await call(b,'remove',{id:item.id}));if(dialog.open){if(editing?.id===item.id)edit(null);renderList();}}catch(e){if(dialog.open)message(e.message,true);}
          },'danger-quiet'));row.append(actions);list.append(row);
        }
        list.append(button('Add '+config.itemLabel,()=>edit(null)),button('Refresh status',async()=>{try{await refresh();}catch(e){message(e.message,true);}}));
      }
      function edit(item){
        if(saving)return;editing=item;pending=null;message('');form.replaceChildren(node('h4','',(item?'Edit ':'Add ')+config.itemLabel));
        const inputs={};
        for(const field of config.fields){
          const wrap=node('label','property-field',field.label),input=node('input');input.dataset.connectionField=field.key;input.id='connection-'+field.key;
          input.type=field.type==='secret'?'password':field.type==='boolean'?'checkbox':'text';
          if(field.type==='boolean')input.checked=!!item?.[field.key];else input.value=field.type==='secret'?'':item?.[field.key]||'';
          input.required=!!field.required&&!(field.type==='secret'&&item);input.autocomplete='off';if(field.maxLength)input.maxLength=field.maxLength;
          wrap.append(input);if(field.type==='secret'&&item)wrap.append(node('small','muted','Leave blank to keep the saved value.'));if(field.help)wrap.append(node('small','muted',field.help));form.append(wrap);inputs[field.key]=input;
        }
        if(config.setupHelp)form.append(node('p','muted',config.setupHelp));
        const results=node('div','studio-search-results'),search=button('Search local network',async()=>{
          search.disabled=true;results.replaceChildren();
          try{
            const data=await call(b,'discover');if(!dialog.open)return;
            if(!data.items?.length)results.append(node('p','muted','No devices found. Enter the address and serial manually; multicast may be blocked.'));
            for(const found of data.items||[])results.append(button(found.name+' · '+found.host,()=>{
              for(const field of config.fields)if(field.type==='string'&&found[field.key]!==undefined&&(field.key!=='name'||!inputs.name.value))inputs[field.key].value=found[field.key];
              pending=null;approval.hidden=true;submit.textContent='Check connection';results.replaceChildren();
            }));
          }catch(e){if(dialog.open)message(e.message,true);}finally{search.disabled=false;}
        });form.append(search,results);
        const approval=node('section','studio-certificate');approval.hidden=true;const submit=node('button','primary','Check connection');submit.type='submit';form.append(approval,submit);
        for(const input of Object.values(inputs))input.addEventListener('input',()=>{pending=null;approval.hidden=true;submit.textContent='Check connection';});
        form.onsubmit=async event=>{
          event.preventDefault();if(saving)return;saving=true;submit.disabled=true;search.disabled=true;message('');
          const candidate=Object.fromEntries(config.fields.map(field=>[field.key,field.type==='boolean'?inputs[field.key].checked:field.type==='secret'?inputs[field.key].value:inputs[field.key].value.trim()]));if(editing)candidate.id=editing.id;
          for(const input of Object.values(inputs))input.disabled=true;
          try{
            if(!pending){
              const result=await call(b,'probe',{host:candidate.host});if(!dialog.open)return;
              pending={...candidate,pin:result.pin};approval.replaceChildren(node('strong','','Approve device certificate'),node('p','muted','No access code has been sent to the device. Compare this SHA-256 fingerprint with a trusted connection before approving.'),node('code','studio-fingerprint',result.pin));approval.hidden=false;submit.textContent='Trust certificate & save';
            }else{
              const result=await call(b,'save',pending);remember(b,result);if(!dialog.open)return;
              for(const field of config.fields)if(field.type==='secret')inputs[field.key].value='';pending=null;renderList();saving=false;edit(null);message('Connection saved. Choose it for a widget, then Save and Deploy.');
            }
          }catch(e){if(dialog.open)message(e.message,true);}
          finally{saving=false;submit.disabled=false;search.disabled=false;for(const input of Object.values(inputs))input.disabled=false;}
        };
      }
      renderList();edit(null);document.body.append(dialog);
      dialog.addEventListener('close',()=>{clearTimeout(timer);pending=null;form.replaceChildren();dialog.remove();onConnectionsChange();});dialog.showModal();poll();
    }
    return {picker,clear:()=>cache.clear()};
  }
  return {fields,create};
})();
