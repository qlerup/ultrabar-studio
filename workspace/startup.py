"""Per-user Windows login startup for installed Studio builds."""
import os
import subprocess
import sys

RUN_KEY = r'Software\Microsoft\Windows\CurrentVersion\Run'
VALUE_NAME = 'UltraBar Studio'


def supported():
    return os.name == 'nt' and bool(getattr(sys, 'frozen', False))


def command():
    return subprocess.list2cmdline([sys.executable])


def enabled():
    if not supported():
        return False
    import winreg
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY) as key:
            value, kind = winreg.QueryValueEx(key, VALUE_NAME)
            return kind == winreg.REG_SZ and value == command()
    except FileNotFoundError:
        return False


def set_enabled(value):
    if not supported():
        raise OSError('Install the Windows app to enable startup with Windows.')
    import winreg
    with winreg.CreateKeyEx(winreg.HKEY_CURRENT_USER, RUN_KEY, 0, winreg.KEY_SET_VALUE) as key:
        if value:
            winreg.SetValueEx(key, VALUE_NAME, 0, winreg.REG_SZ, command())
        else:
            try:
                winreg.DeleteValue(key, VALUE_NAME)
            except FileNotFoundError:
                pass
