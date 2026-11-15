"""Opt-in physical LineOS expansion probe. No profile, layout or printer writes.

Requires existing trusted Studio runtime / token and reviewed companion APK.
Adds a temporary layer at an existing card, then removes it in finally.
"""
import argparse,json,subprocess,time
from pathlib import Path
import frida

ROOT=Path(__file__).resolve().parents[2]

def main():
    p=argparse.ArgumentParser();p.add_argument('--adb',required=True);p.add_argument('--serial',required=True);p.add_argument('--output',required=True,type=Path);args=p.parse_args()
    adb=[args.adb,'-s',args.serial]
    def call(*parts):return subprocess.check_output(adb+list(parts),timeout=20)
    args.output.mkdir(parents=True,exist_ok=True)
    call('push',str(ROOT/'workspace/assets/native/studio-widgets.dex'),'/data/local/tmp/bambu-widget-review.dex')
    call('shell','chmod','644','/data/local/tmp/bambu-widget-review.dex')
    pid=int(call('shell','pidof','com.ultrabar.launch').split()[0])
    token=call('shell','cat','/data/local/tmp/studio-runtime-token').decode().strip()
    port=call('forward','tcp:0','tcp:27042').decode().strip()
    manager=frida.get_device_manager();remote=None;session=None;script=None
    def collapsed(api):
        for _ in range(20):
            if not api.status()['open']:return
            time.sleep(.1)
        raise AssertionError('Layer did not collapse: '+str(api.status()))
    try:
        remote=manager.add_remote_device('127.0.0.1:'+port,token=token)
        session=remote.attach(pid);script=session.create_script((Path(__file__).with_suffix('.js')).read_text())
        script.load();api=script.exports_sync;info=api.prepare();assert info['trustedLauncherIpc'];original=api.geometry();print('Physical host:',json.dumps(info))
        call('shell','input','keyevent','224')
        for slots in range(2,6):
            api.expand(slots,True);time.sleep(.85);state=api.status();assert state['open'] and state['left']>=0 and state['right']<=state['hostWidth']+2
            assert round(state['width'])==261*slots+20*(slots-1)
            assert state['radius']==60
            assert any(abs(t)>1 for t in state['neighborTranslations']),'Neighbors must move rather than be covered'
            (args.output/f'lineos-expanded-{slots}.png').write_bytes(call('exec-out','screencap','-p'))
            print('Expanded',slots,'slots: width',round(state['width']))
            call('shell','input','keyevent','4');collapsed(api)
        api.expand(3,False);time.sleep(.25);assert api.status()['open'];api.close();collapsed(api)
        for index in (0,info['cards']-1):
            api.select(index);api.expand(2,True);time.sleep(.85);state=api.status();assert state['left']>=0 and state['right']<=state['hostWidth']+2
            outside_x=state['left']/2 if state['left']>40 else (state['right']+state['hostWidth'])/2
            call('shell','input','tap',str(int(state['screenX']+outside_x)),str(int(state['screenY']+state['hostHeight']/2)))
            collapsed(api)
        api.expand(3,True);api.expand(3,True);collapsed(api)
        assert api.geometry()==original,'Every neighbor position and source opacity must be restored'
        print('PASS: actual LineOS host, trusted IPC, 2/3/4/5 slot bounds, both edges, outside tap, Back, rapid taps and reduced motion; no saved layout changes')
    finally:
        if script:
            try:script.exports_sync.close();time.sleep(.5)
            except Exception:pass
            script.unload()
        if session:session.detach()
        if remote:manager.remove_remote_device('127.0.0.1:'+port)
        call('forward','--remove','tcp:'+port)
        call('shell','rm','-f','/data/local/tmp/bambu-widget-review.dex')

if __name__=='__main__':main()
