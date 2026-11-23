"""Build the bundled Core Notifications APK with the Studio release key."""
import os
from pathlib import Path
import subprocess
import tempfile
import zipfile

ROOT = Path(__file__).resolve().parent
SDK = Path(os.environ.get('ULTRABAR_ANDROID_SDK', ROOT.parent / 'tools/android-sdk'))
TOOLS = SDK / 'android-15'
PLATFORM = SDK / 'android-35/android.jar'
EXE = '.exe' if os.name == 'nt' else ''


def run(*args):
    subprocess.run([str(arg) for arg in args], check=True, cwd=ROOT)


def main():
    signer = TOOLS / 'lib/apksigner.jar'
    keystore = Path(os.environ['CORE_NOTIFICATIONS_KEYSTORE']).resolve()
    output = ROOT.parent / 'workspace/assets/core-notifications.apk'
    with tempfile.TemporaryDirectory(prefix='core-notifications-') as directory:
        build = Path(directory)
        classes = build / 'classes'
        classes.mkdir()
        generated = build / 'generated'
        generated.mkdir()
        unsigned = build / 'unsigned.apk'
        run(TOOLS / f'aapt{EXE}', 'package', '-f', '-m', '-J', generated,
            '-M', ROOT / 'AndroidManifest.xml', '-S', ROOT / 'res',
            '-I', PLATFORM, '-F', unsigned)
        sources = sorted((ROOT / 'src').rglob('*.java')) + sorted(generated.rglob('*.java'))
        run('javac', '-encoding', 'UTF-8', '--release', '8', '-classpath', PLATFORM,
            '-d', classes, *sources)
        run('java', '-cp', TOOLS / 'lib/d8.jar', 'com.android.tools.r8.D8',
            '--lib', PLATFORM, '--min-api', '26', '--output', build,
            *sorted(classes.rglob('*.class')))
        with zipfile.ZipFile(unsigned, 'a', compression=zipfile.ZIP_DEFLATED) as apk:
            apk.write(build / 'classes.dex', 'classes.dex')
        aligned = build / 'aligned.apk'
        signed = build / 'signed.apk'
        run(TOOLS / f'zipalign{EXE}', '-f', '4', unsigned, aligned)
        run('java', '-jar', signer, 'sign', '--ks', keystore,
            '--ks-pass', 'env:CORE_NOTIFICATIONS_KEY_PASSWORD', '--v4-signing-enabled',
            'false', '--out', signed, aligned)
        run('java', '-jar', signer, 'verify', '--print-certs', signed)
        output.write_bytes(signed.read_bytes())


if __name__ == '__main__':
    main()
