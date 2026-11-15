"""Count published Studio installers, not checksums, source archives or users."""
from datetime import datetime,timezone
import json,os,re,subprocess


def installer_downloads(releases):
    total=0
    for release in releases:
        if release.get('draft'):continue
        for asset in release.get('assets',[]):
            if not re.fullmatch(r'UltraBarStudio-Setup-\d+\.\d+\.\d+\.exe',asset.get('name','')):continue
            value=asset['download_count']
            if type(value) is not int or value<0:raise ValueError('Invalid download count')
            total+=value
    return total


def badge(total):
    right=max(44,len(str(total))*7+18);width=118+right;center=118+right/2
    return f'''<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="20" role="img" aria-label="Installer downloads: {total}"><title>Studio installer downloads: {total}</title><rect width="118" height="20" fill="#292c38"/><rect x="118" width="{right}" height="20" fill="#b8adff"/><g font-family="Verdana,Arial,sans-serif" font-size="11" text-anchor="middle"><text x="59" y="14" fill="#fff">Installer downloads</text><text x="{center}" y="14" fill="#171923">{total}</text></g></svg>'''


def main():
    repo=os.environ['GITHUB_REPOSITORY']
    def api(path,method='GET',body=None,optional=False,pages=False):
        args=['gh','api','repos/'+repo+path,'--method',method]
        if body is not None:args+=['--input','-']
        if pages:args+=['--paginate','--slurp']
        result=subprocess.run(args,input=json.dumps(body).encode() if body is not None else None,capture_output=True)
        if result.returncode:
            if optional and b'HTTP 404' in result.stderr:return None
            raise RuntimeError('Could not update Studio download badge: '+result.stderr.decode(errors='replace'))
        return json.loads(result.stdout)
    releases=[r for page in api('/releases?per_page=100',pages=True) for r in page]
    total=installer_downloads(releases)
    metadata=dict(installerDownloads=total,updatedAt=datetime.now(timezone.utc).isoformat(),scope='Published UltraBarStudio-Setup-*.exe assets across releases; not unique users or installations.')
    ref=api('/git/ref/heads/stats',optional=True)
    tree=api('/git/trees','POST',dict(tree=[dict(path='downloads.svg',mode='100644',type='blob',content=badge(total)),dict(path='downloads.json',mode='100644',type='blob',content=json.dumps(metadata,indent=2)+'\n')]))
    commit=api('/git/commits','POST',dict(message='Refresh Studio installer downloads: '+str(total),tree=tree['sha'],parents=[ref['object']['sha']] if ref else []))
    if ref:api('/git/refs/heads/stats','PATCH',dict(sha=commit['sha'],force=False))
    else:api('/git/refs','POST',dict(ref='refs/heads/stats',sha=commit['sha']))
    print('Published Studio installer download count: '+str(total))


if __name__=='__main__':main()
