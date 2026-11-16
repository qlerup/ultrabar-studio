"""Build the public release-asset feed; upload it with the installer/checksums."""
import hashlib,json
from pathlib import Path
import updates


def main():
    root=Path(__file__).resolve().parent
    installer=root/'release'/f'UltraBarStudio-Setup-{updates.VERSION}.exe'
    raw=installer.read_bytes()
    sections=(root/'README.md').read_text(encoding='utf-8').split('\n## ',2)
    notes=sections[1] if len(sections)>1 else ''
    feed=dict(tag_name='v'+updates.VERSION,draft=False,prerelease=False,body=notes,
              assets=[dict(name=installer.name,state='uploaded',size=len(raw),
                           digest='sha256:'+hashlib.sha256(raw).hexdigest())])
    (installer.parent/'studio-update.json').write_text(json.dumps(feed,indent=2)+'\n',encoding='utf-8')
    (installer.parent/'SHA256SUMS.txt').write_text(hashlib.sha256(raw).hexdigest()+'  '+installer.name+'\n',encoding='utf-8')
    print('Release feed and installer checksum generated.')


if __name__=='__main__':main()
