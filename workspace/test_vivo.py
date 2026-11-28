import copy,io,json,tarfile,tempfile,unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock,patch
from PIL import Image
import vivo,previews,widget_images
from editor import EditError

SERIAL='0000000000ABCDEF'
def profiles():return [dict(module=[dict(serialNo=SERIAL,productId='VIVO_CUBE',config=[dict(keyCode=101,widgetType=1,singleClick=dict(actions=[dict(type='PC_CONTROL')]))])])]

class VivoTests(unittest.TestCase):
    def test_compiled_picture_matches_cube_rgb565_archive(self):
        png=io.BytesIO();Image.new('RGBA',(256,128),'red').save(png,format='PNG')
        raw=vivo.build_package(png.getvalue());image=Image.open(io.BytesIO(previews.package_image(raw)))
        self.assertEqual(image.size,(192,192));self.assertEqual(image.getpixel((96,96)),(255,0,0,255));self.assertEqual(image.getpixel((0,0)),(0,0,0,255))
        self.assertEqual(image.getpixel((0,48)),(0,0,0,255))  # Fitted picture corner, not just screen corner.
        self.assertEqual(image.getpixel((96,48)),(255,0,0,255))
        square=io.BytesIO();Image.new('RGBA',(192,192),'white').save(square,format='PNG')
        package=vivo.build_package(square.getvalue());normal=Image.open(io.BytesIO(previews.package_image(package)))
        self.assertEqual(normal.getpixel((0,0)),(0,0,0,255));self.assertEqual(normal.getpixel((96,96)),(255,255,255,255))
        with tarfile.open(fileobj=io.BytesIO(package),mode='r:gz') as archive:
            pressed=Image.open(io.BytesIO(previews.decode_image(archive.extractfile('com_res101/pressed.bin').read())))
        self.assertEqual(pressed.getpixel((0,0)),(0,0,0,255));self.assertLess(pressed.getpixel((96,96))[0],255)
        preview=Image.open(io.BytesIO(vivo.picture_png(square.getvalue())))
        self.assertEqual(preview.getpixel((0,0)),(0,0,0));self.assertEqual(preview.getpixel((96,96)),(255,255,255))
        black=Image.open(io.BytesIO(previews.package_image(vivo.build_package(None))))
        self.assertEqual(black.convert('RGB').getextrema(),((0,0),(0,0),(0,0)))
    def test_clear_screen_requires_clearing_actions_and_rejects_other_buttons(self):
        value=dict(image=None,clear=True,button=101,source='blank');data=profiles()
        with self.assertRaises(EditError):vivo.validate({SERIAL:value},data)
        data[0]['module'][0]['config'][0]['singleClick']['actions']=[];vivo.validate({SERIAL:value},data)
        value.update(clear=False,image='a'*64,source='custom');data[0]['module'][0]['config'].append(dict(keyCode=102,singleClick=dict(actions=[{}])))
        with self.assertRaises(EditError):vivo.validate({SERIAL:value},data)
    def test_missing_registration_is_repaired_without_changing_other_endpoints_or_network(self):
        with tempfile.TemporaryDirectory() as tmp:
            original=dict(canGateway=dict(endpoints=[dict(serialNumber=SERIAL,productId='VIVO_CUBE',extraConfig=dict(netConfig=dict(ssid='fixture',password='fixture'))),dict(serialNumber='unrelated',productId='KNOB_KEY',extraConfig=dict(keep=True))]),meshGateway=dict(endpoints=[]))
            state=copy.deepcopy(original)
            def adb(*args,**kwargs):
                if 'exec-out' in args:return json.dumps(dict(configuration=state)).encode()
                return '0'
            def request(target,adb,root,action,data):
                self.assertEqual(action,30300);state.clear();state.update(data)
            server=SimpleNamespace(DATA_DIR=Path(tmp),ROOT=Path(tmp),PREFERENCES='/prefs',adb=Mock(side_effect=adb),parse_profiles=lambda raw:json.loads(raw))
            stream=Mock();stream.query.return_value=[dict(serialNo=SERIAL,online=True)];context=Mock();context.__enter__=Mock(return_value=stream);context.__exit__=Mock(return_value=None)
            screens={}
            with patch.object(vivo.bridge,'request',side_effect=request),patch.object(vivo.bridge,'Stream',return_value=context),patch.object(vivo,'upload') as upload,patch.object(vivo.time,'sleep'):
                vivo.deploy(server,profiles(),screens,'target')
            self.assertEqual(state['canGateway']['endpoints'][1],original['canGateway']['endpoints'][1])
            self.assertEqual(state['canGateway']['endpoints'][0]['extraConfig']['netConfig'],original['canGateway']['endpoints'][0]['extraConfig']['netConfig'])
            self.assertEqual(state['canGateway']['endpoints'][0]['extraConfig']['dataConfig'],vivo.configuration(101))
            self.assertEqual(screens[SERIAL]['button'],101);upload.assert_called_once()
    def test_upload_requires_firmware_ack_and_matching_saved_bytes(self):
        raw=vivo.build_package(None)
        def adb(*args,**kwargs):
            if 'forward' in args:return '50000'
            if 'exec-out' in args:return raw
            return str(len(raw))
        server=SimpleNamespace(adb=Mock(side_effect=adb));opener=Mock();opener.open.return_value=io.BytesIO(b'{"state":200}')
        with patch.object(vivo,'build_opener',return_value=opener):vivo.upload(server,'target',SERIAL,raw)
        self.assertIn('serialNo='+SERIAL,opener.open.call_args.args[0].full_url)
        self.assertEqual(server.adb.call_args.args,('-s','target','forward','--remove','tcp:50000'))
        opener.open.return_value=io.BytesIO(b'{"state":-1}')
        with patch.object(vivo,'build_opener',return_value=opener),self.assertRaises(EditError):vivo.upload(server,'target',SERIAL,raw)

    def test_confirmed_firmware_timeout_retries_the_same_archive_once(self):
        raw = vivo.build_package(None)
        def adb(*args, **kwargs):
            if 'forward' in args:return '50000'
            return raw if kwargs.get('binary') else str(len(raw))
        server = SimpleNamespace(adb=Mock(side_effect=adb))
        response = b'{"state":-1,"message":"timeout"}'
        for second in (b'{"state":200}', response):
            with self.subTest(second=second):
                opener, stage = Mock(), Mock()
                opener.open.side_effect = [io.BytesIO(response), io.BytesIO(second)]
                with patch.object(vivo, 'build_opener', return_value=opener):
                    if second == response:
                        with self.assertRaisesRegex(EditError, 'timed out twice'):
                            vivo.upload(server, 'target', SERIAL, raw, stage)
                    else:
                        vivo.upload(server, 'target', SERIAL, raw, stage)
                self.assertEqual(opener.open.call_count, 2)
                self.assertIs(opener.open.call_args_list[0].args[0], opener.open.call_args_list[1].args[0])
                stage.assert_called_once()
    def test_deploy_serializes_artwork_with_sync_and_restores_after_failure(self):
        for fail in (False,True):
            with self.subTest(failed_upload=fail),tempfile.TemporaryDirectory() as tmp:
                running=True;events=[]
                config=dict(canGateway=dict(endpoints=[dict(serialNumber=SERIAL,productId='VIVO_CUBE',extraConfig=dict(dataConfig=vivo.configuration(101)))]))
                def adb(*args,**kwargs):
                    nonlocal running
                    if 'dumpsys' in args:return 'ServiceRecord{fixture u0 '+vivo.screen_sync.PACKAGE_ID+'/.SyncService}'
                    if 'force-stop' in args:running=False;events.append('pause');return ''
                    if 'start-foreground-service' in args:
                        self.assertNotIn('-a',args)  # Preserve the user's saved mode.
                        running=True;events.append('resume');return 'Starting service'
                    if 'exec-out' in args:return json.dumps(dict(configuration=config)).encode()
                    return '0'
                def upload(*args):
                    self.assertFalse(running,'Background property commands must not overlap artwork')
                    events.append('upload')
                    if fail:raise EditError('firmware timeout')
                server=SimpleNamespace(DATA_DIR=Path(tmp),PREFERENCES='/prefs',adb=adb,parse_profiles=lambda raw:json.loads(raw))
                data=profiles();data[0]['module'][0]['config'][0]['singleClick']['actions']=[]
                screens={SERIAL:dict(image=None,clear=True,button=101,source='blank')}
                with patch.object(vivo,'upload',side_effect=upload):
                    if fail:
                        with self.assertRaisesRegex(EditError,'firmware timeout'):vivo.deploy(server,data,screens,'target')
                    else:vivo.deploy(server,data,screens,'target')
                self.assertTrue(running);self.assertEqual(events,['pause','upload','resume'])
    def test_latest_artwork_cache_case_is_used(self):
        raw=vivo.build_package(None);paths=[]
        def adb(*args,**kwargs):
            if 'stat' in args:return str(len(raw))+(' 20' if args[-1].endswith(SERIAL.lower()+'.tgz') else ' 10')
            paths.append(args[-1]);return raw
        result=previews.cube_previews([dict(serial=SERIAL,type='VIVO_CUBE')],'target',adb)
        self.assertIn('image',result[SERIAL]);self.assertTrue(paths[0].endswith(SERIAL.lower()+'.tgz'))

    def test_only_previously_confirmed_unchanged_artwork_is_skipped(self):
        for mode in ('unchanged','different-cache','different-picture','unconfirmed'):
            with self.subTest(mode=mode),tempfile.TemporaryDirectory() as tmp:
                value=dict(image=None,clear=True,button=101,source='blank')
                screens={SERIAL:value};previous=copy.deepcopy(screens)
                if mode=='different-picture':previous[SERIAL]['source']='custom'
                if mode=='unconfirmed':previous={}
                config=dict(canGateway=dict(endpoints=[dict(serialNumber=SERIAL,productId='VIVO_CUBE',extraConfig=dict(dataConfig=vivo.configuration(101)))]))
                saved=json.dumps(dict(configuration=config)).encode();package=vivo.build_package(None)
                cached=package if mode!='different-cache' else bytes([package[0]^1])+package[1:]
                def adb(*args,**kwargs):
                    if 'exec-out' in args:return saved if args[-1]=='/prefs' else cached
                    if 'stat -c' in args[-1]:return str(len(cached))
                    return ''
                server=SimpleNamespace(DATA_DIR=Path(tmp),PREFERENCES='/prefs',adb=Mock(side_effect=adb),parse_profiles=lambda raw:json.loads(raw))
                data=profiles();data[0]['module'][0]['config'][0]['singleClick']['actions']=[]
                with patch.object(vivo,'upload') as upload,patch.object(vivo.screen_sync,'pause_for_artwork') as pause:
                    vivo.deploy(server,data,screens,'target',previous_screens=previous)
                    if mode=='unchanged':upload.assert_not_called();pause.assert_not_called()
                    else:upload.assert_called_once();pause.assert_called_once()
