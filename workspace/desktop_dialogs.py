"""Owned Windows dialogs run on Studio's UI thread and always release the owner."""
import threading

_folder_dialog_lock = threading.Lock()


def pick_package_folder(window):
    from System import Action
    from System.Windows.Forms import DialogResult, FolderBrowserDialog

    if not _folder_dialog_lock.acquire(blocking=False):
        raise OSError('A folder chooser is already open.')
    selected, errors = [], []
    owner = window.native

    def show():
        dialog = None
        enabled = owner.Enabled
        try:
            dialog = FolderBrowserDialog()
            dialog.Description = 'Choose the folder containing your app or widget package'
            dialog.ShowNewFolderButton = False
            if dialog.ShowDialog(owner) == DialogResult.OK:
                selected.append(str(dialog.SelectedPath))
        except Exception as exc:
            errors.append(exc)
        finally:
            try:
                if dialog is not None:
                    dialog.Dispose()
            finally:
                if not owner.IsDisposed:
                    owner.Enabled = enabled
                    owner.Activate()

    try:
        if owner.InvokeRequired:
            owner.Invoke(Action(show))
        else:
            show()
        if errors:
            raise OSError('The folder chooser could not open. Paste the folder path instead.') from errors[0]
        return selected or None
    finally:
        _folder_dialog_lock.release()
