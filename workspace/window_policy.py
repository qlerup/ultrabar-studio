"""Keep the Windows desktop maximized, including native title-bar operations."""
import ctypes
from ctypes import wintypes


def lock_maximized(window):
    # pywebview events run off the UI thread. Native hooks must be installed on it.
    from System import Action
    from System.Windows.Forms import FormWindowState

    def install():
        form = window.native
        if hasattr(form, '_studio_maximized_policy'):
            return
        comctl = ctypes.WinDLL('comctl32', use_last_error=True)
        user = ctypes.WinDLL('user32', use_last_error=True)
        callback_type = ctypes.WINFUNCTYPE(ctypes.c_ssize_t, wintypes.HWND,
            wintypes.UINT, ctypes.c_size_t, ctypes.c_ssize_t,
            ctypes.c_size_t, ctypes.c_size_t)
        comctl.SetWindowSubclass.argtypes = [wintypes.HWND, callback_type, ctypes.c_size_t, ctypes.c_size_t]
        comctl.SetWindowSubclass.restype = wintypes.BOOL
        comctl.RemoveWindowSubclass.argtypes = [wintypes.HWND, callback_type, ctypes.c_size_t]
        comctl.RemoveWindowSubclass.restype = wintypes.BOOL
        comctl.DefSubclassProc.argtypes = [wintypes.HWND, wintypes.UINT, ctypes.c_size_t, ctypes.c_ssize_t]
        comctl.DefSubclassProc.restype = ctypes.c_ssize_t
        user.ShowWindow.argtypes = [wintypes.HWND, ctypes.c_int]
        user.ShowWindow.restype = wintypes.BOOL

        @callback_type
        def procedure(hwnd, message, wparam, lparam, identity, data):
            # WM_NCLBUTTONDOWN/DBLCLK on HTCAPTION: do not enter drag-to-restore.
            if message in (0xA1, 0xA3) and wparam == 2:
                return 0
            if message == 0x112:  # WM_SYSCOMMAND
                command = wparam & 0xFFF0
                if command in (0xF000, 0xF010):  # SC_SIZE, SC_MOVE
                    return 0
                if command == 0xF120:  # SC_RESTORE, including taskbar restore
                    user.ShowWindow(hwnd, 3)  # SW_SHOWMAXIMIZED
                    return 0
            if message == 0x82:  # WM_NCDESTROY
                comctl.RemoveWindowSubclass(hwnd, procedure, identity)
            return comctl.DefSubclassProc(hwnd, message, wparam, lparam)

        def maximize_if_normal():
            if form.WindowState == FormWindowState.Normal:
                form.WindowState = FormWindowState.Maximized

        def enforce(sender, event):
            # Run after WinForms has completed its current state transition.
            if form.WindowState == FormWindowState.Normal:
                form.BeginInvoke(Action(maximize_if_normal))

        # Changing caption buttons can recreate HWND: do it before subclassing.
        form.MaximizeBox = True
        hwnd = form.Handle.ToInt64()
        if not comctl.SetWindowSubclass(hwnd, procedure, 1, 0):
            raise ctypes.WinError(ctypes.get_last_error())
        # Keep delegates alive for the entire native window lifetime.
        form._studio_maximized_policy = (procedure, enforce, comctl, user)
        form.Resize += enforce
        form.WindowState = FormWindowState.Maximized

    window.native.Invoke(Action(install))
