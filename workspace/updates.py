"""Manual release checks. No credentials, downloads or automatic installation."""
import json
import re
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

VERSION = '0.18.0'
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
    # Construct our own repository URL; never open a URL supplied in release metadata.
    url = f'{RELEASES_URL}/tag/{latest}'
    return dict(current_version=VERSION, latest_version=version, update_available=newer,
                installer_available=installer, release_url=url)
