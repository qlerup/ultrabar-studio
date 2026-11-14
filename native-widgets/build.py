from pathlib import Path
import subprocess
ROOT=Path(__file__).resolve().parent
SDK=ROOT.parent/'tools/android-sdk'
BUILD=ROOT/'build'
CLASSES=BUILD/'classes'
CLASSES.mkdir(parents=True,exist_ok=True)
for p in CLASSES.rglob('*.class'):p.unlink()
def run(*args):subprocess.run([str(a) for a in args],check=True,cwd=ROOT)
TESTS=BUILD/'tests'
TESTS.mkdir(parents=True,exist_ok=True)
run('javac','-d',TESTS,ROOT/'src/dk/ultrabarx/widgets/DrivePage.java',ROOT/'tests/DrivePageTest.java')
run('java','-cp',TESTS,'DrivePageTest')
run('javac','-encoding','UTF-8','-source','8','-target','8','-classpath',SDK/'android-35/android.jar','-d',CLASSES,*ROOT.glob('src/**/*.java'))
run('java','-cp',SDK/'android-15/lib/d8.jar','com.android.tools.r8.D8','--lib',SDK/'android-35/android.jar','--min-api','26','--output',BUILD,*CLASSES.rglob('*.class'))
(ROOT.parent/'workspace/assets/native/studio-widgets.dex').write_bytes((BUILD/'classes.dex').read_bytes())
