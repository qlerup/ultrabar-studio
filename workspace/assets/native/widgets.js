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
    let profiles = typeof studioCompactProfiles === 'undefined' ? {} : studioCompactProfiles;
    let mixedLayout = null;
    let lastLayoutError = '';
    let ready = false;
    let layoutPending = false;
    function updateLayout() {
        if (!mixedLayout && !Object.keys(profiles).length) return true;
        mixedLayout ||= Java.use('dk.ultrabarx.widgets.MixedWidgetLayout');
        const Home = Java.use('com.ultrabar.launch.ui.activity.HomeActivity');
        const Record = Java.use('android.app.ActivityThread$ActivityClientRecord');
        const activities = Java.use('android.app.ActivityThread').currentActivityThread().mActivities.value;
        let home = null;
        for (let i = 0; i < activities.size(); i++) {
            const activity = Java.cast(activities.valueAt(i), Record).activity.value;
            if (!Home.class.isInstance(activity) || activity.isFinishing() || activity.isDestroyed()) continue;
            if (activity.hasWindowFocus()) { home = activity; break; }
            if (activity.getWindow().getDecorView().isShown()) home = activity;
        }
        return mixedLayout.apply(home, JSON.stringify(profiles));
    }
    function reportReady() {
        if (updateLayout() && !ready) { ready = true; send({ready: true}); }
    }
    rpc.exports.setCompactProfiles = next => new Promise((resolve, reject) =>
        Java.perform(() => Java.scheduleOnMainThread(() => {
            try { profiles = next; resolve(updateLayout()); }
            catch (error) { reject(new Error(String(error))); }
        })));
    rpc.exports.playPrintAlert = pcm => new Promise((resolve, reject) => Java.perform(() => {
        try {
            if (typeof pcm !== 'string' || pcm.length > 25000) throw new Error('Invalid print alert audio');
            const Base64 = Java.use('android.util.Base64');
            const bytes = Base64.decode.overload('java.lang.String', 'int').call(Base64, pcm, 0);
            if (!bytes.length || bytes.length % 2) throw new Error('Invalid print alert sample count');
            const app = Java.use('android.app.ActivityThread').currentApplication();
            const audio = Java.cast(app.getSystemService('audio'), Java.use('android.media.AudioManager'));
            const Track = Java.use('android.media.AudioTrack');
            const clock = Java.use('android.os.SystemClock');
            const media = 3;
            const track = Track.$new(media, 16000, 4, 2, bytes.length, 0);
            let outputType;
            try {
                if (track.write.overload('[B', 'int', 'int').call(track, bytes, 0, bytes.length) !== bytes.length)
                    throw new Error('Could not buffer print alert');
                const original = audio.getStreamVolume(media);
                const target = Math.round(audio.getStreamMaxVolume(media) * 0.8);
                try {
                    audio.setStreamVolume(media, target, 0);
                    track.play();
                    const deadline = Number(clock.elapsedRealtime()) + 1500;
                    while (track.getPlaybackHeadPosition() < bytes.length / 2) {
                        if (Number(clock.elapsedRealtime()) >= deadline)
                            throw new Error('Print alert playback timed out');
                        clock.sleep(20);
                    }
                    const device = track.getRoutedDevice();
                    clock.sleep(70);
                    outputType = device === null ? 0 : device.getType();
                } finally {
                    if (audio.getStreamVolume(media) === target)
                        audio.setStreamVolume(media, original, 0);
                }
            } finally { track.release(); }
            resolve(outputType);
        } catch (error) { reject(error); }
    }));
    setInterval(() => {
        if (layoutPending || (!Object.keys(profiles).length && !mixedLayout)) return;
        layoutPending = true;
        Java.scheduleOnMainThread(() => {
            try { reportReady(); lastLayoutError = ''; }
            catch (error) {
                if (lastLayoutError !== String(error)) send({error: lastLayoutError = String(error)});
            } finally { layoutPending = false; }
        });
    }, 1000);
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
        reportReady();
    });
});
