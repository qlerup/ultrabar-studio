"""One-button Vivo artwork packages and matching Core input registration."""
import copy,gzip,hashlib,io,json,re,struct,tarfile,time,uuid
from urllib.parse import urlencode
from urllib.request import Request,ProxyHandler,build_opener
from PIL import Image,ImageOps,ImageEnhance,ImageDraw,ImageChops
import bridge,widget_images,screen_sync
from library_icons import NoRedirect
from editor import EditError,clean

SERIAL=re.compile(r'[0-9A-F]{16}')
ARTWORK_DIR='/data/user/0/com.ultrabar.launch/cache/tgz'
UNREGISTERED='This VivoCube is not registered on CoreBAR. Open Overview → Add modules, select the VivoCube, then retry Deploy.'
CORE_UPLOAD_TIMEOUTS = {'timeout', 'write timeout', 'write update command success,update timeout'}

def validate(screens,profiles):
    if not isinstance(screens,dict) or len(screens)>32:raise EditError('Invalid Vivo screen settings.')
    modules={m['serialNo'] for p in profiles for m in p['module'] if m.get('productId')=='VIVO_CUBE'}
    for serial,value in screens.items():
        if not isinstance(serial,str) or not SERIAL.fullmatch(serial) or serial not in modules:raise EditError('Select a configured VivoCube for its screen image, or forget the unused draft picture under Draft & recovery tools.')
        if not isinstance(value,dict) or set(value)-{'image','clear','button','source'} or type(value.get('clear')) is not bool or type(value.get('button')) is not int or not 1<=value['button']<=255:raise EditError('Invalid Vivo screen image or button ID.')
        if value.get('source') not in ('custom','action','blank'):raise EditError('Invalid Vivo picture source.')
        if value['clear'] and value.get('image') is not None:raise EditError('A blank Vivo screen cannot include a picture.')
        if not value['clear'] and not re.fullmatch(r'[a-f0-9]{64}',str(value.get('image',''))):raise EditError('Choose a valid Vivo screen picture.')
        for profile in profiles:
            for module in profile['module']:
                if module['serialNo']!=serial:continue
                for slot in module['config']:
                    active=any(isinstance(slot.get(kind),dict) and slot[kind].get('actions') for kind in ('singleClick','doubleClick','longPress'))
                    if active and (value['clear'] or slot['keyCode']!=value['button']):raise EditError('This screen uses one full-screen button. Clear other button actions before replacing or clearing its artwork.')

def configuration(button):return dict(defaultLayer=1,layers=[dict(id=1,items=[dict(id=button,type=1)])])

def image_bytes(image):
    rgb=image.convert('RGB');pixels=bytearray()
    for red,green,blue in rgb.get_flattened_data():
        value=((red>>3)<<11)|((green>>2)<<5)|(blue>>3)
        pixels.extend((value>>8,value&255,255))
    return struct.pack('<II',5|(192<<10)|(192<<21),len(pixels))+pixels

def picture_canvas(raw):
    canvas=Image.new('RGB',(192,192),'black')
    if raw:
        with Image.open(io.BytesIO(raw)) as source:
            image=ImageOps.contain(source.convert('RGBA'),(192,192),Image.Resampling.LANCZOS)
            # Round the fitted image itself, including letterboxed pictures.
            # Supersampling keeps the exported RGB565 edge smooth on the Cube.
            scale=4;mask=Image.new('L',(image.width*scale,image.height*scale),0)
            ImageDraw.Draw(mask).rounded_rectangle((0,0,mask.width-1,mask.height-1),radius=min(image.size)*scale/8,fill=255)
            mask=mask.resize(image.size,Image.Resampling.LANCZOS)
            alpha=ImageChops.multiply(image.getchannel('A'),mask)
            canvas.paste(image,((192-image.width)//2,(192-image.height)//2),alpha)
    return canvas

def picture_png(raw):
    output=io.BytesIO();picture_canvas(raw).save(output,format='PNG');return output.getvalue()

def build_package(raw,button=101):
    canvas=picture_canvas(raw)
    files={'config.json':json.dumps(configuration(button),separators=(',',':')).encode(),f'com_res{button}/default.bin':image_bytes(canvas),f'com_res{button}/pressed.bin':image_bytes(ImageEnhance.Brightness(canvas).enhance(.7))}
    result=io.BytesIO()
    with tarfile.open(fileobj=result,mode='w',format=tarfile.USTAR_FORMAT) as archive:
        for name,data in files.items():
            entry=tarfile.TarInfo(name);entry.size=len(data);entry.mode=0o644;archive.addfile(entry,io.BytesIO(data))
    return gzip.compress(result.getvalue(),mtime=0)

def upload(server,target,serial,raw,stage=lambda message:None):
    port=server.adb('-s',target,'forward','tcp:0','tcp:8080')
    if not isinstance(port,str) or not port.isdigit() or not 1<=int(port)<=65535:raise EditError('Could not connect to Core’s Vivo artwork service.')
    try:
        boundary='StudioVivo'+uuid.uuid4().hex
        body=(f'--{boundary}\r\nContent-Disposition: form-data; name="file"; filename="{serial}.tgz"\r\nContent-Type: application/gzip\r\n\r\n'.encode()+raw+f'\r\n--{boundary}--\r\n'.encode())
        request=Request('http://127.0.0.1:'+port+'/upload?'+urlencode(dict(serialNo=serial)),data=body,headers={'Content-Type':'multipart/form-data; boundary='+boundary},method='POST')
        opener=build_opener(ProxyHandler({}),NoRedirect)
        for attempt in range(2):
            with opener.open(request,timeout=12) as response:
                result=json.loads(response.read(4097))
            if isinstance(result,dict) and result.get('state')==200:
                break
            reason = result.get('message') if isinstance(result,dict) else None
            if not isinstance(reason,str) or reason.strip().lower() not in CORE_UPLOAD_TIMEOUTS:
                raise EditError(f'CoreBAR rejected the screen package for VivoCube {serial[-6:]}. The CoreBAR layout was not sent.')
            if attempt:
                raise EditError(f'VivoCube {serial[-6:]} timed out twice while applying its screen package. The CoreBAR layout was not sent. Your draft is saved.')
            stage(f'VivoCube {serial[-6:]} timed out. Retrying its screen package…')
        if not cached_package_matches(server,target,serial,raw):
            raise EditError('Saved Vivo artwork could not be verified. Your draft and backup are preserved.')
    except EditError:raise
    except (OSError,ValueError) as exc:raise EditError('Vivo screen update could not be confirmed. Its screen may already have changed; your draft and backup are preserved. Reconnect and retry Deploy.') from exc
    finally:server.adb('-s',target,'forward','--remove','tcp:'+port)

def cached_package_matches(server,target,serial,raw):
    for name in (serial.lower(),serial):
        path=ARTWORK_DIR+'/'+name+'.tgz'
        size=server.adb('-s',target,'shell',f'if [ -f {path} ]; then stat -c %s {path}; else echo 0; fi')
        if size==str(len(raw)) and server.adb('-s',target,'exec-out','cat',path,binary=True)==raw:return True
    return False


def deploy(server,profiles,screens,target,stage=lambda message:None,persist=lambda:None,previous_screens=None):
    # Avoid device access for ordinary deployments with no Vivo actions/artwork.
    modules=[m for p in profiles for m in p['module'] if m.get('productId')=='VIVO_CUBE']
    if not modules and not screens:return
    saved=server.adb('-s',target,'exec-out','cat',server.PREFERENCES,binary=True)
    data=server.parse_profiles(saved)
    backup=server.DATA_DIR/'backups'/(hashlib.sha256(saved).hexdigest()+'.xml');backup.parent.mkdir(parents=True,exist_ok=True)
    if not backup.exists():backup.write_bytes(saved)
    original=data.get('configuration',{});updated=clean(copy.deepcopy(original));endpoints={}
    for gateway in ('canGateway','meshGateway'):
        for endpoint in updated.get(gateway,{}).get('endpoints',[]):
            if endpoint.get('productId')=='VIVO_CUBE':endpoints[endpoint['serialNumber']]=endpoint
    for module in modules:
        serial=module['serialNo'];endpoint=endpoints.get(serial)
        slots=[slot for slot in module['config'] if any(isinstance(slot.get(kind),dict) and slot[kind].get('actions') for kind in ('singleClick','doubleClick','longPress'))]
        if endpoint is None and (serial in screens or slots):raise EditError(UNREGISTERED)
        if serial in screens or endpoint is None:continue
        has_layout=(endpoint.get('extraConfig') or {}).get('dataConfig')
        if has_layout:
            paths=[ARTWORK_DIR+'/'+serial+'.tgz',ARTWORK_DIR+'/'+serial.lower()+'.tgz']
            exists=server.adb('-s',target,'shell',f'if [ -f {paths[0]} ] || [ -f {paths[1]} ]; then echo yes; else echo no; fi')
            if exists=='yes':continue
        if len(slots)==1:
            picture=widget_images.store_picture(server,widget_images.default_png('url'),source='default')
            screens[serial]=dict(image=picture['sha256'],clear=False,button=slots[0]['keyCode'],source='action')
    validate(screens,profiles)
    if not screens:return
    packages={}
    for serial,value in screens.items():
        if serial not in endpoints:raise EditError(UNREGISTERED)
        try:raw=None if value['clear'] else widget_images.read_picture(server,value['image'])
        except (OSError,ValueError) as exc:raise EditError('Vivo picture is missing. Upload it again before Deploy.') from exc
        package=build_package(raw,value['button'])
        # A completed deployment already confirmed this artwork. Ordinary layout
        # edits must not restart the Cube's resource loader, especially on wake.
        # Also verify Core's registration and cached bytes: another client may
        # have replaced either since our last completed deployment.
        if previous_screens is not None and previous_screens.get(serial)==value and (endpoints[serial].get('extraConfig') or {}).get('dataConfig')==configuration(value['button']) and cached_package_matches(server,target,serial,package):continue
        packages[serial]=package
        extra=endpoints[serial].get('extraConfig') or {};extra['dataConfig']=configuration(value['button']);endpoints[serial]['extraConfig']=extra
        # Back up existing archives before vendor upload replaces its cache file.
        for name in (serial,serial.lower()):
            path=ARTWORK_DIR+'/'+name+'.tgz'
            size=server.adb('-s',target,'shell',f'if [ -f {path} ]; then stat -c %s {path}; else echo 0; fi')
            if isinstance(size,str) and size.isdigit() and 0<int(size)<=8*1024*1024:
                old=server.adb('-s',target,'exec-out','cat',path,binary=True)
                backup=server.DATA_DIR/'backups'/('vivo-'+serial+'-'+hashlib.sha256(old).hexdigest()+'.tgz');backup.parent.mkdir(parents=True,exist_ok=True)
                if not backup.exists():backup.write_bytes(old)
    persist()
    if updated!=clean(original):
        stage('Registering Vivo screen buttons on Core…')
        bridge.request(target,server.adb,server.ROOT,30300,updated)
        actual=server.parse_profiles(server.adb('-s',target,'exec-out','cat',server.PREFERENCES,binary=True)).get('configuration')
        if clean(actual)!=updated:raise EditError('Core did not save the Vivo button registration. No artwork was sent; retry Deploy.')
        # LineOS deliberately defers initEndpoints by 2000 ms after 30300.
        time.sleep(2.1)
        with bridge.Stream(target,server.adb,server.ROOT) as stream:
            for attempt in range(12):
                states=stream.query(30730,[])
                online={item['serialNo'] for item in states if item.get('online') is True}
                if set(screens)<=online:break
                if attempt==11:raise EditError('VivoCube did not reconnect after registering its button. Retry Deploy when it is online.')
                time.sleep(.3)
    if not packages:return
    with screen_sync.pause_for_artwork(server,target):
        for serial,raw in packages.items():
            stage('Sending screen image to VivoCube '+serial[-6:]+'…')
            upload(server,target,serial,raw,stage)
