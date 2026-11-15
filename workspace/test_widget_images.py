"""Shortcut image normalization, icon extraction boundaries and deploy transfers."""
import hashlib
import io
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import Mock,patch
from PIL import Image
import editor,server,widget_images


def png(color='#b9b2ff',size=(80,60)):
    out=io.BytesIO();Image.new('RGBA',size,color).save(out,format='PNG');return out.getvalue()


class ShortcutImageTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.server=SimpleNamespace(DATA_DIR=Path(self.temp.name),adb=Mock())

    def test_upload_normalizes_and_retrieves_by_verified_hash(self):
        image=widget_images.store_picture(self.server,png(size=(1024,768)))
        raw=widget_images.read_picture(self.server,image['sha256'])
        self.assertEqual(hashlib.sha256(raw).hexdigest(),image['sha256'])
        self.assertEqual(Image.open(io.BytesIO(raw)).size,(512,384))
        self.assertEqual(widget_images.picture_hash(image['icon']),image['sha256'])
        self.assertEqual(image['source'],'custom')
        path=self.server.DATA_DIR/'widget-images'/(image['sha256']+'.png');path.write_bytes(b'changed')
        with self.assertRaises(ValueError):widget_images.read_picture(self.server,image['sha256'])

    def test_rejects_non_images_oversized_uploads_and_path_traversal(self):
        for raw in [b'<svg></svg>',b'x'*(widget_images.MAX_UPLOAD+1),png(size=(8193,1))]:
            with self.assertRaises((ValueError,OSError)):widget_images.normalize(raw)
        with self.assertRaises(ValueError):widget_images.read_picture(self.server,'../other')
        with self.assertRaises(ValueError):widget_images.picture_hash(widget_images.CORE_PREFIX+'../other.png')

    def test_default_icons_are_distinct_pngs(self):
        website=widget_images.default_png('url');program=widget_images.default_png('program')
        self.assertNotEqual(website,program)
        self.assertEqual(Image.open(io.BytesIO(website)).size,(512,512))
        self.assertEqual(Image.open(io.BytesIO(program)).format,'PNG')

    def test_deploy_transfers_and_verifies_exact_picture_bytes(self):
        image=widget_images.store_picture(self.server,png());raw=widget_images.read_picture(self.server,image['sha256'])
        self.server.adb.return_value=raw
        profiles=[dict(homeData=[dict(icon=image['icon']),dict(icon=image['icon'])])]
        widget_images.deploy_pictures(self.server,profiles,'core')
        writes=[c for c in self.server.adb.call_args_list if c.kwargs.get('input_data') is not None]
        self.assertEqual(len(writes),1);self.assertIn('exec-in',writes[0].args);self.assertEqual(writes[0].kwargs['input_data'],raw)
        self.assertTrue(any('mv ' in str(c.args) for c in self.server.adb.call_args_list))
        self.server.adb.return_value=b'wrong'
        with self.assertRaisesRegex(editor.EditError,'verified'):widget_images.deploy_pictures(self.server,profiles,'core')

    def test_no_images_do_not_access_device_and_missing_images_stop_deploy(self):
        widget_images.deploy_pictures(self.server,[dict(homeData=[dict(icon='resId://pc_control_def_icon')])],'core')
        self.server.adb.assert_not_called()
        with self.assertRaisesRegex(editor.EditError,'missing'):widget_images.deploy_pictures(self.server,[dict(homeData=[dict(icon=widget_images.CORE_PREFIX+'a'*64+'.png')])],'core')


class ShortcutImageRouteTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name);p=patch.object(server,'DATA_DIR',self.root);p.start();self.addCleanup(p.stop)
        self.client=server.app.test_client();self.headers={'Host':'127.0.0.1:8741','X-Studio-Token':server.SESSION_TOKEN}

    def test_upload_requires_token_and_returns_persistent_png(self):
        self.assertEqual(self.client.post('/api/pc/images',headers={'Host':'127.0.0.1:8741'}).status_code,403)
        response=self.client.post('/api/pc/images',headers=self.headers,data={'image':(io.BytesIO(png()),'photo.png')})
        self.assertEqual(response.status_code,200)
        image=response.json['image'];response=self.client.get(image['preview'],headers=self.headers)
        self.assertEqual(response.status_code,200);self.assertEqual(response.mimetype,'image/png')
        self.assertEqual(self.client.post('/api/pc/images',headers=self.headers,data={'image':(io.BytesIO(b'bad'),'image.png')}).status_code,400)

    def test_program_icon_only_reads_validated_exe_and_falls_back_cleanly(self):
        path=self.root/'App.exe';path.write_bytes(b'fixture')
        with patch.object(widget_images,'program_png',return_value=png()) as read:
            response=self.client.post('/api/pc/program-icon',headers=self.headers,json=dict(target=str(path)))
            self.assertEqual(response.status_code,200);self.assertEqual(response.json['image']['source'],'program')
            read.assert_called_once_with(str(path.resolve()))
        with patch.object(widget_images,'program_png',return_value=None):
            response=self.client.post('/api/pc/program-icon',headers=self.headers,json=dict(target=str(path)))
            self.assertEqual(response.json['image']['source'],'default')
        with patch.object(widget_images,'program_png') as read:
            self.assertEqual(self.client.post('/api/pc/program-icon',headers=self.headers,json=dict(target=str(self.root/'bad.txt'))).status_code,400)
            read.assert_not_called()
        self.assertFalse((self.root/'pc-actions.json').exists())
