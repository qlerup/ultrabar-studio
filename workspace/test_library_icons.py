"""Core icon routing, validation and app catalog compatibility."""
import io
import unittest
from unittest.mock import Mock, patch
from PIL import Image
import library_icons
import server


def png(size=(32,32)):
    stream=io.BytesIO();Image.new('RGB',size,'#b9b2ff').save(stream,format='PNG');return stream.getvalue()


class CoreIconTests(unittest.TestCase):
    def test_reads_fixed_icon_service_and_cleans_up_forward(self):
        raw=png();adb=Mock(side_effect=['12345',''])
        with patch.object(library_icons,'build_opener') as opener:
            opener.return_value.open.return_value=io.BytesIO(raw)
            self.assertEqual(library_icons.fetch_icon('192.168.1.20:5555','app','com.test.app',adb),raw)
            request=opener.return_value.open.call_args.args[0]
            self.assertEqual(request.full_url,'http://127.0.0.1:12345/widget/icon?id=com.test.app&type=application&scheme=30')
            self.assertEqual(opener.return_value.open.call_args.kwargs['timeout'],3)
        self.assertEqual(adb.call_args_list[-1].args,('-s','192.168.1.20:5555','forward','--remove','tcp:12345'))

    def test_invalid_icon_names_do_not_open_device_connection(self):
        for kind,ident in [('url','https://example.com'),('app','../secret'),('app','com.app?target=other'),('app',''),('app','com.'+'x'*256)]:
            adb=Mock()
            with self.assertRaises(ValueError):library_icons.fetch_icon('device',kind,ident,adb)
            adb.assert_not_called()

    def test_rejects_large_non_png_and_redirects_and_always_removes_forward(self):
        for raw in [b'x'*(library_icons.MAX_BYTES+1),b'<svg></svg>',png((1025,1))]:
            adb=Mock(side_effect=['12345',''])
            with patch.object(library_icons,'build_opener') as opener:
                opener.return_value.open.return_value=io.BytesIO(raw)
                with self.assertRaises((ValueError,OSError)):library_icons.fetch_icon('device','clock','',adb)
            self.assertIn('--remove',adb.call_args.args)
        with self.assertRaises(ValueError):library_icons.NoRedirect().redirect_request(None,None,302,'',{},'http://other/icon.png')
        adb=Mock(side_effect=['12345',''])
        with patch.object(library_icons,'build_opener') as opener:
            opener.return_value.open.side_effect=OSError('Offline')
            with self.assertRaises(OSError):library_icons.fetch_icon('device','clock','',adb)
        self.assertIn('--remove',adb.call_args.args)

    def test_cache_is_separate_for_each_device_and_target(self):
        cache=library_icons.CoreIcons();adb=Mock()
        with patch.object(library_icons,'fetch_icon',side_effect=[b'one',b'two',b'three']) as fetch:
            self.assertEqual(cache.get('target','clock','',adb,'first'),b'one')
            self.assertEqual(cache.get('target','clock','',adb,'first'),b'one')
            self.assertEqual(cache.get('target','clock','',adb,'second'),b'two')
            self.assertEqual(cache.get('other','clock','',adb,'first'),b'three')
            self.assertEqual(fetch.call_count,3)


class LibraryCatalogTests(unittest.TestCase):
    def setUp(self):
        self.client=server.app.test_client()
        self.headers={'Host':'127.0.0.1:8741','X-Studio-Token':server.SESSION_TOKEN}
        self.connection=patch.dict(server.connection,target='192.168.1.20:5555',snapshot=dict(device_id='icon-test',profiles=[]))
        self.connection.start();self.addCleanup(self.connection.stop)

    def test_catalog_accepts_both_core_app_identifiers_and_preserves_names(self):
        items=[dict(application='com.test.calculator',appName='Calculator',icon='http://untrusted.example/icon'),dict(packageName='com.test.old',appName='Existing app'),dict(application='https://bad.example'),dict(application=None)]
        with patch('editor.bridge.request',return_value=items):
            response=self.client.get('/api/editor/catalog',headers=self.headers)
        self.assertEqual(response.status_code,200)
        apps=response.get_json()['apps']
        self.assertEqual([a['id'] for a in apps],['com.test.calculator','com.test.old'])
        self.assertEqual([a['name'] for a in apps],['Calculator','Existing app'])
        self.assertTrue(all('icon' not in a for a in apps))

    def test_icon_requires_session_and_uses_connected_device(self):
        with patch('editor.CoreIcons.get',return_value=png()) as get:
            self.assertEqual(self.client.get('/api/editor/icons/clock',headers={'Host':'127.0.0.1:8741'}).status_code,403)
            get.assert_not_called()
            response=self.client.get('/api/editor/icons/clock',headers=self.headers)
            self.assertEqual(response.status_code,200)
            self.assertEqual(response.mimetype,'image/png')
            self.assertEqual(response.headers['X-Content-Type-Options'],'nosniff')
            self.assertEqual(get.call_args.args,('192.168.1.20:5555','clock','',server.adb,'icon-test'))
