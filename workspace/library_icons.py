"""Bounded, read-only icon proxy for the currently connected CoreBAR."""
from collections import OrderedDict
import io
import re
import threading
from urllib.parse import urlencode
from urllib.request import Request, HTTPRedirectHandler, ProxyHandler, build_opener
from PIL import Image

MAX_BYTES = 262144

class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        raise ValueError('Device icon redirects are not supported.')


def fetch_icon(target, kind, ident, adb):
    # The caller validates the connected target; never use a URL from device data.
    if kind == 'clock':
        params = dict(id='time', type='TIME', scheme=20)
    elif kind == 'app' and isinstance(ident,str) and re.fullmatch(r'[A-Za-z][A-Za-z0-9_]*(?:\.[A-Za-z][A-Za-z0-9_]*)+',ident) and len(ident)<=255:
        params = dict(id=ident, type='application', scheme=30)
    else:
        raise ValueError('Unsupported device icon.')
    # Reach Core's local icon service over the existing ADB connection, including
    # devices whose HTTP port is not reachable directly from the PC network.
    port=adb('-s',target,'forward','tcp:0','tcp:8080')
    if not isinstance(port,str) or not port.isdigit() or not 1<=int(port)<=65535:
        raise ValueError('Could not open the device icon connection.')
    try:
        request=Request('http://127.0.0.1:'+port+'/widget/icon?'+urlencode(params),headers={'User-Agent':'UltraBar-Studio'})
        with build_opener(ProxyHandler({}),NoRedirect).open(request,timeout=3) as response:
            raw=response.read(MAX_BYTES+1)
    finally:
        adb('-s',target,'forward','--remove','tcp:'+port)
    if len(raw)>MAX_BYTES:
        raise ValueError('Device icon exceeds the size limit.')
    with Image.open(io.BytesIO(raw)) as image:
        if image.format!='PNG' or not 1<=image.width<=1024 or not 1<=image.height<=1024 or getattr(image,'n_frames',1)!=1:
            raise ValueError('Unsupported device icon image.')
        image.verify()
    return raw


class CoreIcons:
    def __init__(self):
        self.cache=OrderedDict()
        self.lock=threading.Lock()

    def get(self,target,kind,ident,adb,device_id):
        key=(device_id,target,kind,ident)
        with self.lock:
            if key in self.cache:
                self.cache.move_to_end(key)
                return self.cache[key]
        raw=fetch_icon(target,kind,ident,adb)
        with self.lock:
            self.cache[key]=raw
            self.cache.move_to_end(key)
            while len(self.cache)>64:self.cache.popitem(last=False)
        return raw
