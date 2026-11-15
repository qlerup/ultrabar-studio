"""Isolated native Cancel/Close regression check; never controls installed Studio."""
import ctypes
from ctypes import wintypes
import os
from pathlib import Path
import shutil
import sys
import tempfile
import threading
import time

local_modules=tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
site=Path(sys.executable).parent.parent/'Lib/site-packages'
for name in ('pythonnet','clr_loader','webview'):
    shutil.copytree(site/name,Path(local_modules.name)/name)
sys.path.insert(0,local_modules.name)
import webview
from desktop_dialogs import pick_package_folder

user=ctypes.WinDLL('user32',use_last_error=True)
callback=ctypes.WINFUNCTYPE(wintypes.BOOL,wintypes.HWND,wintypes.LPARAM)
user.EnumWindows.argtypes=[callback,wintypes.LPARAM]
user.GetWindowThreadProcessId.argtypes=[wintypes.HWND,ctypes.POINTER(wintypes.DWORD)]
user.GetClassNameW.argtypes=[wintypes.HWND,wintypes.LPWSTR,ctypes.c_int]
user.IsWindowEnabled.argtypes=[wintypes.HWND];user.IsWindowEnabled.restype=wintypes.BOOL
user.PostMessageW.argtypes=[wintypes.HWND,wintypes.UINT,wintypes.WPARAM,wintypes.LPARAM]
user.ShowWindow.argtypes=[wintypes.HWND,ctypes.c_int]
results=[]
window=webview.create_window('Studio isolated folder chooser check',html='<html><body><button id="alive" onclick="this.textContent=\'Working\'">Check</button></body></html>',hidden=True)


def check():
    from System import Action
    try:
        assert window.events.loaded.wait(20)
        window.native.Invoke(Action(lambda:setattr(window.native,'Opacity',0)))
        window.show()
        for mode in ('cancel','close'):
            found=threading.Event()
            def dismiss():
                deadline=time.monotonic()+10
                while not found.is_set() and time.monotonic()<deadline:
                    @callback
                    def visit(hwnd,_):
                        pid=wintypes.DWORD();user.GetWindowThreadProcessId(hwnd,ctypes.byref(pid))
                        name=ctypes.create_unicode_buffer(100);user.GetClassNameW(hwnd,name,100)
                        if pid.value==os.getpid() and name.value=='#32770':
                            user.ShowWindow(hwnd,0)
                            user.PostMessageW(hwnd,0x111 if mode=='cancel' else 0x10,2 if mode=='cancel' else 0,0)
                            found.set()
                        return True
                    user.EnumWindows(visit,0)
                    time.sleep(.05)
            closer=threading.Thread(target=dismiss,daemon=True);closer.start()
            selected=window.create_file_dialog(webview.FileDialog.FOLDER) if '--legacy' in sys.argv else pick_package_folder(window)
            assert found.wait(2),'Folder dialog did not appear'
            assert not selected,'Cancellation unexpectedly selected a folder'
            enabled=[]
            window.native.Invoke(Action(lambda:enabled.append(bool(window.native.Enabled) and bool(user.IsWindowEnabled(window.native.Handle.ToInt64())))))
            assert enabled==[True],mode+' left the Studio window disabled'
            assert window.evaluate_js("document.getElementById('alive').click();document.getElementById('alive').textContent")=='Working'
        results.append('PASS: Cancel and Close return, owner remains enabled, WebView responds and the chooser reopens.')
    except Exception as exc:
        results.append('FAIL: '+repr(exc))
    finally:
        window.destroy()


with tempfile.TemporaryDirectory() as storage:
    webview.start(check,gui='edgechromium',private_mode=True,storage_path=storage)
print(results)
assert results and results[0].startswith('PASS'),results
