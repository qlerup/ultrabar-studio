"""Bounded asynchronous public GitHub counts. No user credentials or telemetry."""
import json,re,threading,time
from urllib.parse import quote
from urllib.request import Request,urlopen
from urllib.error import HTTPError


class GitHubCooldown(Exception):
    def __init__(self,seconds):self.seconds=seconds


def github_json(path):
    request=Request('https://api.github.com/'+path,headers={'User-Agent':'UltraBar-Studio','Accept':'application/vnd.github+json'})
    try:
        with urlopen(request,timeout=8) as response:raw=response.read(2*1024*1024+1)
    except HTTPError as exc:
        if exc.code in (403,429):
            try:seconds=max(float(exc.headers.get('Retry-After','0')),float(exc.headers.get('X-RateLimit-Reset','0'))-time.time(),60)
            except (TypeError,ValueError):seconds=900
            raise GitHubCooldown(min(3600,max(900,seconds))) from None
        raise
    if len(raw)>2*1024*1024:raise ValueError('GitHub response exceeded limit')
    return json.loads(raw)


def count(value):
    if type(value) is not int or value<0:raise ValueError('Invalid GitHub count')
    return value


class PackageStats:
    def __init__(self):
        self.lock=threading.RLock();self.packages={};self.cache={};self.responses={};self.running=False;self.cooldown_until=0
    def remember(self,packages):
        from store import package_links
        with self.lock:
            for p in packages:
                links=package_links(p)
                if not links:continue
                url=p.get('artifact',{}).get('url','')
                match=re.fullmatch(r'https://github\.com/qlerup/ultrabar-store/releases/download/([A-Za-z0-9][A-Za-z0-9_.-]*)/([A-Za-z0-9][A-Za-z0-9_.-]*)',url)
                if match:self.packages[p['id']]=(links['repository'][len('https://github.com/'):],match[1],match[2])
    def request(self,ids):
        with self.lock:
            ids=list(dict.fromkeys(ids))[:12]
            missing=[];result={};now=time.monotonic()
            for key in ids:
                identity=self.packages.get(key)
                if not identity:continue
                cached=self.cache.get(identity)
                if not cached or cached['retry_at']<=now:missing.append(identity)
                repo,tag,asset=identity
                result[key]=dict(downloads=cached['downloads'] if cached else None,issues=cached['issues'] if cached else None,loading=not cached or cached['retry_at']<=now,stale=bool(cached and cached['stale']),repository='https://github.com/'+repo,artifact='https://github.com/qlerup/ultrabar-store/releases/download/'+tag+'/'+asset)
            if missing and not self.running:
                self.running=True
                threading.Thread(target=self.refresh,args=(list(dict.fromkeys(missing)),),daemon=True,name='StudioPackageStats').start()
            return result
    def read(self,path):
        with self.lock:
            if time.monotonic()<self.cooldown_until:raise GitHubCooldown(self.cooldown_until-time.monotonic())
            cached=self.responses.get(path)
            if cached and cached[0]>time.monotonic():return cached[1]
        try:data=github_json(path)
        except Exception as exc:
            # Cache a failure briefly too; repeated render/poll must not hammer GitHub.
            with self.lock:
                if isinstance(exc,GitHubCooldown):self.cooldown_until=time.monotonic()+exc.seconds
                self.responses[path]=(time.monotonic()+300,None)
            raise
        with self.lock:
            if len(self.responses)>128:self.responses={key:value for key,value in self.responses.items() if value[0]>time.monotonic()}
            self.responses[path]=(time.monotonic()+900,data)
        return data
    def refresh(self,identities):
        try:
            for identity in identities:
                repo,tag,asset=identity
                with self.lock:old=self.cache.get(identity,{})
                values=dict(downloads=old.get('downloads'),issues=old.get('issues'));failed=False
                try:
                    data=self.read('repos/qlerup/ultrabar-store/releases/tags/'+quote(tag,safe=''))
                    row=next(a for a in data['assets'] if a['name']==asset)
                    values['downloads']=count(row['download_count'])
                except Exception:failed=True
                try:
                    data=self.read('search/issues?q='+quote('repo:'+repo+' is:issue is:open',safe='')+'&per_page=1')
                    if data.get('incomplete_results'):raise ValueError('Incomplete issue count')
                    values['issues']=count(data['total_count'])
                except Exception:failed=True
                with self.lock:self.cache[identity]=dict(values,retry_at=time.monotonic()+(300 if failed else 900),stale=failed)
        finally:
            with self.lock:self.running=False
