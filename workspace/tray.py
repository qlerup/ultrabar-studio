"""Windows notification-area lifetime: close hides, explicit Exit shuts down."""
import ctypes
from ctypes import wintypes

SHOW_MESSAGE='UltraBarStudio.ShowMainWindow'


def show_running_studio(title='UltraBar Studio'):
    user=ctypes.WinDLL('user32',use_last_error=True)
    user.FindWindowW.argtypes=[wintypes.LPCWSTR,wintypes.LPCWSTR];user.FindWindowW.restype=wintypes.HWND
    user.RegisterWindowMessageW.argtypes=[wintypes.LPCWSTR];user.RegisterWindowMessageW.restype=wintypes.UINT
    user.PostMessageW.argtypes=[wintypes.HWND,wintypes.UINT,ctypes.c_size_t,ctypes.c_ssize_t];user.PostMessageW.restype=wintypes.BOOL
    user.GetWindowThreadProcessId.argtypes=[wintypes.HWND,ctypes.POINTER(wintypes.DWORD)]
    user.AllowSetForegroundWindow.argtypes=[wintypes.DWORD]
    hwnd=user.FindWindowW(None,title)
    if not hwnd:return False
    process=wintypes.DWORD();user.GetWindowThreadProcessId(hwnd,ctypes.byref(process));user.AllowSetForegroundWindow(process.value)
    return bool(user.PostMessageW(hwnd,user.RegisterWindowMessageW(SHOW_MESSAGE),0,0))


class StudioTray:
    def __init__(self,window,icon_path):
        self.window=window;self.icon_path=icon_path;self.exiting=False;self.disposed=False;self.notice_shown=False;self.form=None
    def install(self):
        from System import Action
        from System.Drawing import Icon
        from System.Windows.Forms import NotifyIcon,ContextMenuStrip,ToolStripMenuItem
        def setup():
            self.form=self.window.native
            self.icon=Icon(str(self.icon_path));self.menu=ContextMenuStrip()
            self.open_item=ToolStripMenuItem('Open Studio');self.exit_item=ToolStripMenuItem('Exit')
            self.open_item.Click+=lambda sender,event:self.show()
            self.exit_item.Click+=lambda sender,event:self.exit()
            self.menu.Items.Add(self.open_item);self.menu.Items.Add(self.exit_item)
            self.notify=NotifyIcon();self.notify.Icon=self.icon;self.notify.Text='UltraBar Studio';self.notify.ContextMenuStrip=self.menu
            self.notify.DoubleClick+=lambda sender,event:self.show()
            self.notify.Visible=True
            self.form.FormClosing+=self.on_closing
            self.form.FormClosed+=lambda sender,event:self.dispose_native()
            self.install_show_message()
        self.window.native.Invoke(Action(setup))
    def install_show_message(self):
        user=ctypes.WinDLL('user32');user.RegisterWindowMessageW.argtypes=[wintypes.LPCWSTR];user.RegisterWindowMessageW.restype=wintypes.UINT
        self.show_message=user.RegisterWindowMessageW(SHOW_MESSAGE)
        self.comctl=ctypes.WinDLL('comctl32',use_last_error=True)
        callback_type=ctypes.WINFUNCTYPE(ctypes.c_ssize_t,wintypes.HWND,wintypes.UINT,ctypes.c_size_t,ctypes.c_ssize_t,ctypes.c_size_t,ctypes.c_size_t)
        self.comctl.SetWindowSubclass.argtypes=[wintypes.HWND,callback_type,ctypes.c_size_t,ctypes.c_size_t];self.comctl.SetWindowSubclass.restype=wintypes.BOOL
        self.comctl.RemoveWindowSubclass.argtypes=[wintypes.HWND,callback_type,ctypes.c_size_t];self.comctl.RemoveWindowSubclass.restype=wintypes.BOOL
        self.comctl.DefSubclassProc.argtypes=[wintypes.HWND,wintypes.UINT,ctypes.c_size_t,ctypes.c_ssize_t];self.comctl.DefSubclassProc.restype=ctypes.c_ssize_t
        @callback_type
        def procedure(hwnd,message,wparam,lparam,identity,data):
            if message==self.show_message:
                self.show();return 0
            if message==0x82:self.comctl.RemoveWindowSubclass(hwnd,procedure,identity)
            return self.comctl.DefSubclassProc(hwnd,message,wparam,lparam)
        self.procedure=procedure
        if not self.comctl.SetWindowSubclass(self.form.Handle.ToInt64(),procedure,2,0):raise ctypes.WinError(ctypes.get_last_error())
    def on_closing(self,sender,event):
        from System.Windows.Forms import CloseReason,ToolTipIcon
        if not self.exiting and event.CloseReason==CloseReason.UserClosing:
            event.Cancel=True;self.form.Hide()
            if not self.notice_shown:
                self.notify.ShowBalloonTip(4000,'UltraBar Studio','Studio is running in the background. Double-click this icon to reopen it, or choose Exit to quit.',ToolTipIcon.Info)
                self.notice_shown=True
        else:
            self.exiting=True;self.dispose_native()
    def show(self):
        from System import Action
        from System.Windows.Forms import FormWindowState
        def open_window():
            if self.exiting or self.form.IsDisposed:return
            self.form.Show();self.form.WindowState=FormWindowState.Maximized;self.form.Activate();self.form.BringToFront()
        if self.form.InvokeRequired:self.form.Invoke(Action(open_window))
        else:open_window()
    def exit(self):
        from System import Action
        def close():
            if self.form.IsDisposed:return
            self.exiting=True;self.form.Close()
        if self.form.InvokeRequired:self.form.Invoke(Action(close))
        else:close()
    def dispose_native(self):
        if self.disposed:return
        self.disposed=True
        self.notify.Visible=False;self.notify.Dispose();self.menu.Dispose();self.icon.Dispose()
