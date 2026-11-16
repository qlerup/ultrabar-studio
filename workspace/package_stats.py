"""Bounded asynchronous reads of published counts. No GitHub API calls on PCs."""
import json,re,threading,time
from urllib.request import Request,urlopen

STATS_URL='https://raw.githubusercontent.com/qlerup/ultrabar-store/catalog/package-stats.json'


def published_counts():
    request=Request(STATS_URL,headers={'User-Agent':'UltraBar-Studio','Accept':'application/json'})
    with urlopen(request,timeout=8) as response:raw=response.read(1024*1024+1)
    if len(raw)>1024*1024:raise ValueError('Statistics feed exceeded limit')
    data=json.loads(raw)
    if not isinstance(data,dict) or type(data.get('schemaVersion')) is not int or data['schemaVersion']!=1 or type(data.get('generatedAt')) is not int or not isinstance(data.get('packages'),dict) or len(data['packages'])>500:
        raise ValueError('Invalid published statistics')
    return data


def valid_count(value):
    return type(value) is int and value>=0


class PackageStats:
    def __init__(self):
        self.lock=threading.RLock();self.packages={};self.versions={};self.cache={};self.running=False
        self.feed=None;self.feed_expires=0

    def remember(self,packages):
        from store import package_links,valid_version
        with self.lock:
            for p in packages:
                links=package_links(p)
                if not links:continue
                version=valid_version(p.get('version','0.0.0'))
                if self.versions.get(p['id'],(0,0,0))>version:continue
                url=p.get('artifact',{}).get('url','')
                match=re.fullmatch(r'https://github\.com/qlerup/ultrabar-store/releases/download/([A-Za-z0-9][A-Za-z0-9_.-]*)/([A-Za-z0-9][A-Za-z0-9_.-]*)',url)
                if match:
                    self.packages[p['id']]=(links['repository'][len('https://github.com/'):],match[1],match[2]);self.versions[p['id']]=version

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

    def read(self):
        with self.lock:
            if self.feed_expires>time.monotonic():
                if self.feed is None:raise ValueError('Statistics feed temporarily unavailable')
                return self.feed
        try:data=published_counts()
        except Exception:
            with self.lock:self.feed=None;self.feed_expires=time.monotonic()+300
            raise
        with self.lock:self.feed=data;self.feed_expires=time.monotonic()+900
        return data

    def refresh(self,identities):
        try:
            try:
                feed=self.read();rows=feed['packages'].values()
                aged=time.time()-feed['generatedAt']>3600 or feed['generatedAt']>time.time()+300
            except Exception:rows=[];aged=True
            for identity in identities:
                repo,tag,asset=identity
                expected_repo='https://github.com/'+repo
                expected_asset='https://github.com/qlerup/ultrabar-store/releases/download/'+tag+'/'+asset
                row=next((r for r in rows if isinstance(r,dict) and r.get('repository')==expected_repo and r.get('artifact')==expected_asset),{})
                with self.lock:old=self.cache.get(identity,{})
                failed=aged or row.get('stale',False) or not all(valid_count(row.get(k)) for k in ('downloads','issues'))
                values={k:row[k] if valid_count(row.get(k)) else old.get(k) for k in ('downloads','issues')}
                with self.lock:self.cache[identity]=dict(values,retry_at=time.monotonic()+(300 if failed else 900),stale=bool(failed))
        finally:
            with self.lock:self.running=False
