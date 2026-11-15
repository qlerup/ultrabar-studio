import tempfile,time,threading,json
from pathlib import Path
import sys,shutil
# .NET Framework cannot load these assemblies from the network workspace.
local_modules=tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
site=Path(sys.executable).parent.parent/'Lib/site-packages'
for name in ('pythonnet','clr_loader','webview'):shutil.copytree(site/name,Path(local_modules.name)/name)
sys.path.insert(0,local_modules.name)
sys.path.insert(0,str(Path(__file__).resolve().parent))
import webview
from window_policy import lock_maximized
result=[]
with tempfile.TemporaryDirectory() as storage:
 w=webview.create_window('Studio isolated window test',html='<html><title>Test</title></html>',maximized=True,resizable=False,hidden=True)
 w.events.before_show += lambda: lock_maximized(w)
 def check():
  try:
   w.events.loaded.wait(15)
   def state():return str(w.native.WindowState)
   def wait_for(expected):
    deadline=time.monotonic()+3
    while state()!=expected and time.monotonic()<deadline:time.sleep(.05)
    assert state()==expected,(state(),expected)
   from System import Action
   def make_transparent():w.native.Opacity=0
   w.native.Invoke(Action(make_transparent));w.show()
   print('initial',state(),flush=True);w.maximize();wait_for('Maximized');print('maximized',state(),flush=True)
   assert w.native.MaximizeBox
   assert w.native.MinimizeBox
   assert str(w.native.FormBorderStyle)=='FixedSingle'
   w.restore();wait_for('Maximized');print('restored',state(),flush=True)
   import ctypes
   user=ctypes.WinDLL('user32');user.SendMessageW.argtypes=[ctypes.c_void_p,ctypes.c_uint,ctypes.c_size_t,ctypes.c_ssize_t];user.SendMessageW.restype=ctypes.c_ssize_t
   hwnd=w.native.Handle.ToInt64()
   for message,value in ((0xA1,2),(0xA3,2),(0x112,0xF010),(0x112,0xF000),(0x112,0xF120)):
    user.SendMessageW(hwnd,message,value,0);wait_for('Maximized')
   from System.Windows.Forms import FormWindowState
   w.native.Invoke(Action(lambda: setattr(w.native,'WindowState',FormWindowState.Normal)))
   wait_for('Maximized')
   print('native drag, double-click, move, size and restore blocked',flush=True)
   w.minimize();wait_for('Minimized');print('minimized',state(),flush=True)
   w.restore();wait_for('Maximized');print('restored',state(),flush=True)
   result.append('PASS: native caption drag/double-click and system move/size/restore stay maximized; direct restore recovers; minimize works')
  except Exception as exc:result.append('FAIL: '+repr(exc))
  finally:w.destroy()
 webview.start(check,gui='edgechromium',private_mode=True,storage_path=storage)
print(result)
assert result and result[0].startswith('PASS'),result
