'use strict';
// Opt-in read-only-layout probe. Adds a temporary expansion layer, never a profile.
let Tile, source, host, spec,cardSources=[];
function mainThread(fn) {
    return new Promise((resolve,reject)=>Java.perform(()=>Java.scheduleOnMainThread(()=>{
        try { resolve(fn()); } catch(error) { reject(new Error(String(error.stack||error))); }
    })));
}
rpc.exports = {
    prepare() { return mainThread(()=>{
        const loader=Java.cast(Java.classFactory.loader,Java.use('dalvik.system.BaseDexClassLoader'));
        loader.addDexPath.overload('java.lang.String').call(loader,'/data/local/tmp/bambu-widget-review.dex');
        Tile=Java.use('dk.ultrabarx.widgets.BambuTile');
        const Group=Java.use('android.view.ViewGroup'),Frame=Java.use('android.widget.FrameLayout');
        const roots=Java.use('android.view.WindowManagerGlobal').getInstance().mViews.value;
        const cards=[];
        function visit(v){
            v=Java.cast(v,Java.use('android.view.View'));
            if(!v.isShown())return;
            const cardId=v.getResources().getIdentifier('card','id','com.ultrabar.launch');
            if(v.getId()===cardId&&Frame.class.isInstance(v))cards.push(Java.retain(v));
            if(Group.class.isInstance(v)){const g=Java.cast(v,Group);for(let i=0;i<g.getChildCount();i++)visit(g.getChildAt(i));}
        }
        for(let i=0;i<roots.size();i++)visit(roots.get(i));
        if(!cards.length)throw new Error('No visible Core card; open Core home first');
        source=cards[Math.min(1,cards.length-1)];
        cardSources=cards;
        const reply=source.getContext().getContentResolver().call(Java.use('android.net.Uri').parse('content://dk.ultrabar.bambu.status'),'snapshot',null,null);
        const json=reply.getString('json','{}');
        Tile.data.value=Java.use('org.json.JSONObject').$new(json);
        Tile.received.value=Java.use('android.os.SystemClock').elapsedRealtime();
        return {cards:cards.length,sourceWidth:source.getWidth(),sourceHeight:source.getHeight(),trustedLauncherIpc:json.indexOf('"fresh"')!==-1};
    });},
    select(index){return mainThread(()=>{source=cardSources[index];return true;});},
    expand(slots,motion){return mainThread(()=>{
        spec=Java.use('org.json.JSONObject').$new(JSON.stringify({kind:'bambu',expandedSlots:slots,liquidMotion:motion,background:'#14202b',textColor:'#eff6fa',accent:'#86e4c3'}));
        Tile.expand(source,spec);return true;
    });},
    status(){return mainThread(()=>{
        const layer=Tile.expanded.value;if(layer===null)return {open:false};
        const rect=layer.current.value;
        const position=Java.array('int',[0,0]);layer.getLocationOnScreen(position);
        return {open:true,left:rect.left.value,right:rect.right.value,width:rect.width(),hostWidth:layer.getWidth(),hostHeight:layer.getHeight(),screenX:position[0],screenY:position[1]};
    });},
    close(){return mainThread(()=>{const layer=Tile.expanded.value;if(layer!==null)layer.close();return true;});}
};
