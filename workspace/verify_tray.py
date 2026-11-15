"""Isolated native Windows regression test; never controls the installed app."""
import shutil,sys,tempfile,threading,time
from pathlib import Path
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
from urllib.request import urlopen

local_modules=tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
site=Path(sys.executable).parent.parent/'Lib/site-packages'
for name in ('pythonnet','clr_loader','webview'):shutil.copytree(site/name,Path(local_modules.name)/name)
sys.path.insert(0,local_modules.name)
import webview
from tray import StudioTray,show_running_studio

class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200);self.end_headers();self.wfile.write(b'<html><title>Tray test</title>Backend is alive</html>')
    def log_message(self,*args):pass

http=ThreadingHTTPServer(('127.0.0.1',0),Handler)
threading.Thread(target=http.serve_forever,daemon=True).start()
result=[]
with tempfile.TemporaryDirectory() as storage:
    title='UltraBar Studio isolated tray test'
    w=webview.create_window(title,url='http://127.0.0.1:'+str(http.server_port),hidden=True,maximized=True,resizable=True)
    tray=StudioTray(w,Path(__file__).parent/'assets/studio.ico')
    w.events.before_show+=tray.install
    def check():
        from System import Action
        try:
            assert w.events.loaded.wait(20)
            def wait(predicate):
                deadline=time.monotonic()+4
                while not predicate() and time.monotonic()<deadline:time.sleep(.05)
                assert predicate()
            w.native.Invoke(Action(lambda:setattr(w.native,'Opacity',0)))
            w.native.Invoke(Action(lambda:setattr(tray.notify,'Text','Studio isolated tray test')))
            assert tray.notify.Visible
            w.show();wait(lambda:w.native.Visible)
            assert w.native.MaximizeBox
            assert str(w.native.FormBorderStyle)=='Sizable'
            w.maximize();wait(lambda:str(w.native.WindowState)=='Maximized')
            w.restore();wait(lambda:str(w.native.WindowState)=='Normal')
            w.resize(900,600);w.move(80,70)
            time.sleep(.2)
            assert str(w.native.WindowState)=='Normal'
            size=(w.native.Width,w.native.Height)
            assert w.native.Left>=0 and w.native.Top>=0
            w.destroy();wait(lambda:not w.native.Visible)
            assert not w.events.closed.is_set()
            assert b'Backend is alive' in urlopen('http://127.0.0.1:'+str(http.server_port),timeout=3).read()
            w.native.Invoke(Action(lambda:tray.open_item.PerformClick()))
            wait(lambda:w.native.Visible and str(w.native.WindowState)=='Normal')
            assert (w.native.Width,w.native.Height)==size
            w.destroy();wait(lambda:not w.native.Visible)
            assert show_running_studio(title)
            wait(lambda:w.native.Visible and str(w.native.WindowState)=='Normal')
            w.minimize();wait(lambda:str(w.native.WindowState)=='Minimized')
            tray.show();wait(lambda:str(w.native.WindowState)=='Normal')
            assert (w.native.Width,w.native.Height)==size
            w.maximize();wait(lambda:str(w.native.WindowState)=='Maximized')
            w.minimize();wait(lambda:str(w.native.WindowState)=='Minimized')
            tray.show();wait(lambda:str(w.native.WindowState)=='Maximized')
            w.native.Invoke(Action(lambda:tray.exit_item.PerformClick()))
            assert w.events.closed.wait(4);assert tray.disposed
            result.append('PASS: normal resize/move/restore work; close keeps backend alive; tray/second launch preserve normal size; minimized normal/maximized states restore; Exit closes.')
        except Exception as exc:result.append('FAIL: '+repr(exc))
        finally:
            if not w.events.closed.is_set():tray.exit()
    webview.start(check,gui='edgechromium',private_mode=True,storage_path=storage)
http.shutdown();http.server_close()
print(result)
assert result and result[0].startswith('PASS'),result
