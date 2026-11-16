'use strict';
Java.perform(function () {
    // Keep the class in the application's loader across PC reconnects.
    // A fresh child DexClassLoader would duplicate the class and its data reader.
    try { Java.use('dk.ultrabarx.widgets.StudioCard'); }
    catch (_) {
        const loader = Java.cast(Java.classFactory.loader, Java.use('dalvik.system.BaseDexClassLoader'));
        loader.addDexPath.overload('java.lang.String').call(loader, '/data/local/tmp/studio-widgets.dex');
    }
    const Card = Java.use('dk.ultrabarx.widgets.StudioCard');
    const Bambu = Java.use('dk.ultrabarx.widgets.BambuTile');
    setInterval(function () {
        Java.perform(function () {
            for (const event of JSON.parse(String(Bambu.drainActions()))) send({bambuAction: event});
        });
    }, 250);
    const Holder = Java.use('com.ultrabar.launch.common.adapter.holder.PcControlHolder');
    Holder.updateUI.implementation = function () {
        this.updateUI();
        try {
            const data = this.mData.value;
            Card.bind(this.itemView.value, data.getId(), data.getName());
        } catch (error) { send({error: String(error)}); }
    };
    Java.scheduleOnMainThread(function () {
        const Group = Java.use('android.view.ViewGroup');
        const Recycler = Java.use('androidx.recyclerview.widget.RecyclerView');
        function visit(view) {
            if (Recycler.class.isInstance(view)) {
                const adapter = Java.cast(view, Recycler).getAdapter();
                if (adapter !== null) adapter.notifyDataSetChanged();
            } else if (Group.class.isInstance(view)) {
                const group = Java.cast(view, Group);
                for (let i=0; i<group.getChildCount(); i++) visit(group.getChildAt(i));
            }
        }
        const roots = Java.use('android.view.WindowManagerGlobal').getInstance().mViews.value;
        for (let i=0; i<roots.size(); i++) visit(roots.get(i));
        send({ready: true});
    });
});
