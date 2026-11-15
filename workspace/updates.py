"""Verified release downloads and explicit installer launch."""
import json
import re
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

VERSION = '0.42.0'
REPOSITORY = 'qlerup/ultrabar-studio'
RELEASES_URL = f'https://github.com/{REPOSITORY}/releases'

class UpdateError(Exception):
    pass

def version_tuple(value):
    if not isinstance(value, str) or not re.fullmatch(r'v?(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)', value):
        raise UpdateError('The release has an unsupported version number.')
    return tuple(map(int, value.removeprefix('v').split('.')))

def check_latest():
    request = Request(f'https://api.github.com/repos/{REPOSITORY}/releases/latest', headers={
        'Accept': 'application/vnd.github+json', 'User-Agent': f'UltraBar-Studio/{VERSION}',
        'X-GitHub-Api-Version': '2026-03-10'})
    try:
        with urlopen(request, timeout=10) as response:
            raw = response.read(1024 * 1024 + 1)
        if len(raw) > 1024 * 1024:
            raise UpdateError('The release response is too large. Try again later.')
        release = json.loads(raw)
    except HTTPError as exc:
        if exc.code == 404:
            raise UpdateError('No public release is available yet. Try again later.') from exc
        if exc.code in (403, 429):
            raise UpdateError('GitHub is limiting update checks. Try again later.') from exc
        raise UpdateError('GitHub could not be reached. Try again later.') from exc
    except (URLError, OSError, ValueError) as exc:
        raise UpdateError('Could not check for updates. Check your internet connection and try again.') from exc
    if not isinstance(release, dict) or release.get('draft') or release.get('prerelease'):
        raise UpdateError('No stable release is available.')
    latest = release.get('tag_name')
    newer = version_tuple(latest) > version_tuple(VERSION)
    version = latest.removeprefix('v')
    expected = f'UltraBarStudio-Setup-{version}.exe'
    assets = release.get('assets', [])
    if not isinstance(assets, list):
        raise UpdateError('The release information is incomplete.')
    installer = any(isinstance(a, dict) and a.get('name') == expected and a.get('state') == 'uploaded' for a in assets)
    asset = next((a for a in assets if isinstance(a,dict) and a.get('name')==expected and a.get('state')=='uploaded'), {})
    digest = asset.get('digest','')
    size = asset.get('size',0)
    downloadable = isinstance(digest,str) and bool(re.fullmatch(r'sha256:[a-f0-9]{64}',digest)) and type(size) is int and 0<size<=256*1024*1024
    # Construct URLs locally, never execute URLs or paths supplied by clients.
    url = f'{RELEASES_URL}/tag/{latest}'
    notes = release.get('body')
    notes = notes.strip() if isinstance(notes, str) else ''
    return dict(current_version=VERSION, latest_version=version, update_available=newer,
                release_notes=notes,
                installer_available=installer, release_url=url, download_available=bool(installer and downloadable),
                download_url=f'{RELEASES_URL}/download/{latest}/{expected}', sha256=digest[7:] if downloadable else None, size=size if downloadable else 0)


import hashlib
import subprocess
import threading
import time
from pathlib import Path
from urllib.parse import urlsplit
from urllib.request import HTTPRedirectHandler, build_opener

class ReleaseRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        u=urlsplit(newurl)
        if u.scheme!='https' or u.hostname not in ('github.com','release-assets.githubusercontent.com','objects.githubusercontent.com') or u.username or u.password:
            raise UpdateError('The update redirected outside GitHub download hosts.')
        return super().redirect_request(req,fp,code,msg,headers,newurl)

class Updater:
    def __init__(self):
        self.lock=threading.RLock()
        self.job={'state':'idle'}
        self.path=None
        self.digest=None
    def status(self):
        with self.lock:return dict(self.job)
    def set(self,**values):
        with self.lock:self.job.update(values)
    def start(self,folder):
        with self.lock:
            if self.job['state'] in ('downloading','launching'):
                raise UpdateError('An update is already in progress.')
            self.path=None
            self.job=dict(state='downloading',message='Checking latest release...',received=0,total=0)
        threading.Thread(target=self.download,args=(Path(folder),),daemon=True).start()
        return self.status()
    def download(self,folder):
        partial=None
        try:
            release=check_latest()
            if not release['update_available'] or not release['download_available']:
                raise UpdateError('No newer installer with a verified checksum is available.')
            folder.mkdir(parents=True,exist_ok=True)
            destination=folder/('UltraBarStudio-Setup-'+release['latest_version']+'.exe')
            partial=destination.with_suffix('.part')
            self.set(total=release['size'],message='Downloading Studio '+release['latest_version']+'...')
            digest=hashlib.sha256();received=0;started=time.monotonic()
            req=Request(release['download_url'],headers={'User-Agent':'UltraBar-Studio/'+VERSION})
            with build_opener(ReleaseRedirect).open(req,timeout=15) as response, partial.open('wb') as output:
                while True:
                    chunk=response.read(65536)
                    if not chunk:break
                    received+=len(chunk)
                    if received>release['size'] or time.monotonic()-started>300:
                        raise UpdateError('The update exceeded its download size or time limit.')
                    output.write(chunk);digest.update(chunk);self.set(received=received)
            if received!=release['size'] or digest.hexdigest()!=release['sha256']:
                raise UpdateError('Update verification failed. The installer was not started. Try downloading again.')
            partial.replace(destination)
            with self.lock:self.path=destination;self.digest=release['sha256']
            self.set(state='ready',message='Download verified. Save any draft changes, then start the installer.')
        except Exception as exc:
            if partial:partial.unlink(missing_ok=True)
            self.set(state='error',message=str(exc) if isinstance(exc,UpdateError) else 'Download failed. Check your connection and try again.')
    def launch(self, launcher=None):
        with self.lock:
            if self.job['state']!='ready' or not self.path:raise UpdateError('Download and verify the update first.')
            if not self.path.is_file() or hashlib.sha256(self.path.read_bytes()).hexdigest()!=self.digest:
                self.job=dict(state='error',message='Downloaded installer changed. Download it again.')
                raise UpdateError(self.job['message'])
            try:
                if launcher:launcher(self.path)
                else:subprocess.Popen([str(self.path)],cwd=str(self.path.parent))
            except OSError as exc:raise UpdateError('Could not start the installer. Try again.') from exc
            self.job=dict(state='launched',message='Closing Studio to install the update. Your saved data is kept.' if launcher else 'Installer opened. Use its option to close Studio automatically.')
            return dict(self.job)
