"""Windows entry point; backend stays alive while Studio is in the tray."""
import ctypes
import logging
import os
from pathlib import Path
import sys
import threading


def main():
    import webview
    from waitress import create_server
    import server

    server.DATA_DIR.mkdir(parents=True, exist_ok=True)
    logging.basicConfig(filename=str(server.DATA_DIR / 'studio.log'), level=logging.WARNING,
                        format='%(asctime)s %(levelname)s %(message)s')
    kernel = ctypes.WinDLL('kernel32', use_last_error=True)
    kernel.CreateMutexW.argtypes = [ctypes.c_void_p, ctypes.c_bool, ctypes.c_wchar_p]
    kernel.CreateMutexW.restype = ctypes.c_void_p
    kernel.CloseHandle.argtypes = [ctypes.c_void_p]
    handle = kernel.CreateMutexW(None, False, 'Local\\UltraBarStudio.Desktop')
    if not handle:
        raise ctypes.WinError(ctypes.get_last_error())
    if ctypes.get_last_error() == 183:
        from tray import show_running_studio
        if not show_running_studio():ctypes.windll.user32.MessageBoxW(None, 'UltraBar Studio is already running. Open it from the icon in the notification area near the clock.', 'UltraBar Studio', 64)
        kernel.CloseHandle(handle)
        return
    http = None
    pending_update = []
    try:
        http = create_server(server.app, host='127.0.0.1', port=0, threads=4)
        port = http.effective_port
        server.app.config['ALLOWED_HOSTS'] = {f'127.0.0.1:{port}'}
        thread = threading.Thread(target=http.run, daemon=True)
        thread.start()
        webview.settings['ALLOW_DOWNLOADS'] = True
        webview.settings['ALLOW_FILE_URLS'] = False
        window = webview.create_window('UltraBar Studio', f'http://127.0.0.1:{port}',
                                      width=1440, height=960, min_size=(640, 520), maximized=True, resizable=True, background_color='#101116')
        from tray import StudioTray
        tray=StudioTray(window,server.ROOT/'assets/studio.ico')
        window.events.before_show += tray.install
        def queue_update(path):
            pending_update.append(Path(path))
            timer = threading.Timer(0.5, tray.exit)
            timer.daemon = True
            timer.start()
        server.update_launcher = queue_update
        server.program_picker = lambda: window.create_file_dialog(file_types=('Programs (*.exe)',))
        server.package_folder_picker = lambda: window.create_file_dialog(webview.FileDialog.FOLDER)
        # Used when reopening Studio after an update; normal launches still show discovery.
        if '--resume-editor' in sys.argv:
            def resume_editor():
                window.evaluate_js("api('/api/preferences').then(r=>r.json()).then(async p=>{document.getElementById('target').value=p.target;await load(true);if(snapshot)document.getElementById('nav-editor').click();}).catch(()=>{}); void 0")
            window.events.loaded += resume_editor
        # A test-only mode verifies the actual packaged WebView and clean shutdown.
        if '--smoke-test' in sys.argv:
            def smoke():
                import time
                time.sleep(2)
                try:
                    result = window.evaluate_js("document.title === 'UltraBar Studio' && !!document.getElementById('connect')")
                    if '--live-test' in sys.argv:
                        deadline = time.monotonic() + 20
                        while time.monotonic() < deadline:
                            if window.evaluate_js("!!document.querySelector('.discovered-device')"):
                                break
                            time.sleep(0.25)
                        result = result and window.evaluate_js("!!document.querySelector('.discovered-device')")
                        window.evaluate_js("document.querySelector('.discovered-device')?.click();document.querySelector('#discovery-connect')?.click()")
                        deadline = time.monotonic() + 55
                        while time.monotonic() < deadline:
                            if window.evaluate_js("document.querySelectorAll('.hardware-unit').length > 1"):
                                break
                            time.sleep(0.25)
                        result = result and window.evaluate_js("document.querySelectorAll('.hardware-unit').length === 7 && document.querySelectorAll('.module-card').length > 0")
                    (server.DATA_DIR / 'desktop-smoke.txt').write_text('PASS' if result else 'FAIL')
                finally:
                    tray.exit()
            window.events.loaded += lambda: threading.Thread(target=smoke, daemon=True).start()
        webview.start(gui='edgechromium', private_mode=False,
                      storage_path=str(server.DATA_DIR / 'webview'), icon=str(server.ROOT / 'assets' / 'studio.ico'))
    finally:
        if http:
            http.task_dispatcher.shutdown()
            server.native_widgets.stop.set()
            server.companion.stop.set()
            if server.native_widgets.thread:
                server.native_widgets.thread.join(5)
            http.close()
        kernel.CloseHandle(handle)
    if pending_update:
        # Launch only after the WebView and backend have shut down. Inno's
        # Restart Manager handles any remaining process/file handles normally.
        import hashlib
        import subprocess
        installer = pending_update[0]
        if hashlib.sha256(installer.read_bytes()).hexdigest() != server.updater.digest:
            raise RuntimeError('The downloaded installer changed after verification.')
        subprocess.Popen([str(installer)], cwd=str(installer.parent))


if __name__ == '__main__':
    try:
        main()
    except Exception:
        logging.exception('Desktop startup failed')
        ctypes.windll.user32.MessageBoxW(None,
            'UltraBar Studio could not start. Check that Microsoft Edge WebView2 is installed. See studio.log in %LOCALAPPDATA%\\UltraBar Studio.',
            'UltraBar Studio', 16)
        sys.exit(1)
