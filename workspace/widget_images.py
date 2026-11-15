"""PC shortcut pictures: normalized local PNGs and verified deployment to Core."""
import base64
import hashlib
import io
import os
from pathlib import Path
import re
import subprocess
import uuid
from PIL import Image, ImageDraw, ImageOps

CORE_PREFIX='/sdcard/Android/data/com.ultrabar.launch/files/studio-icons/'
MAX_UPLOAD=2*1024*1024
HEX=re.compile(r'[a-f0-9]{64}')


def picture_hash(icon):
    if not isinstance(icon,str) or not icon.startswith(CORE_PREFIX):return None
    name=icon[len(CORE_PREFIX):]
    if not re.fullmatch(r'[a-f0-9]{64}\.png',name):raise ValueError('Invalid widget picture reference.')
    return name[:-4]


def normalize(raw):
    if not raw or len(raw)>MAX_UPLOAD:raise ValueError('Choose a PNG, JPG or WebP picture up to 2 MB.')
    try:source=Image.open(io.BytesIO(raw))
    except Image.DecompressionBombError as exc:raise ValueError('This picture is too large.') from exc
    with source:
        if source.format not in ('PNG','JPEG','WEBP') or getattr(source,'n_frames',1)!=1 or source.width*source.height>16000000 or not 1<=source.width<=8192 or not 1<=source.height<=8192:
            raise ValueError('Choose a static PNG, JPG or WebP picture.')
        image=ImageOps.exif_transpose(source).convert('RGBA')
        image.thumbnail((512,512),Image.Resampling.LANCZOS)
        output=io.BytesIO();image.save(output,format='PNG',optimize=True)
        return output.getvalue()


def default_png(kind):
    if kind not in ('url','program'):raise ValueError('Unknown shortcut type.')
    im=Image.new('RGBA',(1024,1024),'#242235');d=ImageDraw.Draw(im)
    purple,white='#b9b2ff','#f4f1ff'
    if kind=='url':
        d.ellipse((180,180,844,844),outline=purple,width=38)
        d.ellipse((348,180,676,844),outline=purple,width=26)
        d.line((196,512,828,512),fill=white,width=30)
        d.arc((184,322,840,610),0,180,fill=purple,width=24)
        d.arc((184,414,840,702),180,360,fill=purple,width=24)
    else:
        d.rounded_rectangle((174,230,850,766),radius=32,outline=purple,width=36)
        d.line((192,358,832,358),fill=purple,width=26)
        for x in [236,292,348]:d.ellipse((x,278,x+24,302),fill=white)
        d.line((440,486,552,552,440,618),fill=white,width=30)
        d.line((590,620,720,620),fill=purple,width=28)
    output=io.BytesIO();im.resize((512,512),Image.Resampling.LANCZOS).save(output,format='PNG',optimize=True);return output.getvalue()


def store_picture(server,raw,source='custom'):
    data=normalize(raw);digest=hashlib.sha256(data).hexdigest()
    path=server.DATA_DIR/'widget-images'/(digest+'.png');path.parent.mkdir(parents=True,exist_ok=True)
    if not path.exists():
        temporary=path.with_name(digest+'.'+uuid.uuid4().hex+'.tmp')
        try:temporary.write_bytes(data);temporary.replace(path)
        finally:temporary.unlink(missing_ok=True)
    return dict(sha256=digest,icon=CORE_PREFIX+digest+'.png',preview='/api/pc/images/'+digest,source=source)


def read_picture(server,digest):
    if not isinstance(digest,str) or not HEX.fullmatch(digest):raise ValueError('Invalid widget picture ID.')
    raw=(server.DATA_DIR/'widget-images'/(digest+'.png')).read_bytes()
    if len(raw)>MAX_UPLOAD or hashlib.sha256(raw).hexdigest()!=digest:raise ValueError('Widget picture verification failed. Upload it again.')
    return raw


def program_png(target):
    if os.name!='nt':return None
    # The executable path is passed as data, never interpolated into PowerShell.
    script='''Add-Type -AssemblyName System.Drawing
$icon = [System.Drawing.Icon]::ExtractAssociatedIcon($env:STUDIO_ICON_PROGRAMFILE)
if ($null -eq $icon) { exit 1 }
$bitmap = $icon.ToBitmap()
$stream = New-Object System.IO.MemoryStream
try {
    $bitmap.Save($stream, [System.Drawing.Imaging.ImageFormat]::Png)
    [Convert]::ToBase64String($stream.ToArray())
} finally { $stream.Dispose(); $bitmap.Dispose(); $icon.Dispose() }
'''
    executable=Path(os.environ.get('SystemRoot','C:/Windows'))/'System32/WindowsPowerShell/v1.0/powershell.exe'
    try:
        result=subprocess.run([str(executable),'-NoProfile','-NonInteractive','-Command',script],env={**os.environ,'STUDIO_ICON_PROGRAMFILE':target},capture_output=True,timeout=8,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
        if result.returncode or len(result.stdout)>MAX_UPLOAD*2:return None
        return normalize(base64.b64decode(result.stdout.strip(),validate=True))
    except (OSError,subprocess.TimeoutExpired,ValueError):return None


def deploy_pictures(server,profiles,target):
    from editor import EditError
    digests={picture_hash(w.get('icon')) for p in profiles for w in p['homeData']}
    digests.discard(None)
    if not digests:return
    server.adb('-s',target,'shell','mkdir -p '+CORE_PREFIX.rstrip('/'))
    for digest in sorted(digests):
        try:raw=read_picture(server,digest)
        except (OSError,ValueError) as exc:raise EditError('A widget picture is missing or damaged. Upload the picture again before Deploy.') from exc
        path=CORE_PREFIX+digest+'.png'
        server.adb('-s',target,'exec-in',f'umask 077; cat > {path}.tmp',input_data=raw)
        server.adb('-s',target,'shell',f'mv {path}.tmp {path}')
        if server.adb('-s',target,'exec-out','cat',path,binary=True)!=raw:
            raise EditError('Widget picture transfer could not be verified. No layout was sent. Retry Deploy.')
