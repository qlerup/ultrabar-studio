"""Cancellation is accepted only before the verified library commit."""
import copy,threading,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
import server,store
from test_store import fixture


class CancellationTests(unittest.TestCase):
    def setUp(self):
        temp=tempfile.TemporaryDirectory();self.addCleanup(temp.cleanup)
        context=patch.object(server,'DATA_DIR',Path(temp.name));context.start();self.addCleanup(context.stop)
        self.service=store.Store(server);self.package,self.raw=fixture()
        self.old=copy.deepcopy(self.package);self.package['version']='1.0.1'
        self.service.save({self.old['id']+':pc':self.old})
        self.before=(Path(temp.name)/'store/installed.json').read_bytes()

    def exercise(self,stage):
        entered=threading.Event();release=threading.Event();done=threading.Event()
        original=self.service.install
        def worker(*args):
            try:return original(*args)
            finally:done.set()
        def catalog():
            if stage=='catalog':
                entered.set()
                if not release.wait(3):raise AssertionError('Catalog test gate timed out')
            return [self.package]
        def download(url,limit,destination):
            if stage=='download':
                entered.set()
                if not release.wait(3):raise AssertionError('Download test gate timed out')
            destination.write(self.raw);return len(self.raw)
        body=dict(id=self.package['id'],version=self.package['version'],sha256=self.package['artifact']['sha256'])
        with patch.object(self.service,'install',side_effect=worker),patch.object(store,'catalog',side_effect=catalog),patch.object(store,'fetch',side_effect=download),patch.object(server,'adb') as adb:
            try:
                job=self.service.start(body);self.assertTrue(entered.wait(3))
                cancelled=self.service.cancel(dict(request_id=job['request_id']))
                self.assertTrue(cancelled['cancel_requested']);self.assertEqual(cancelled['state'],'running')
            finally:release.set();self.assertTrue(done.wait(3))
            self.assertEqual(self.service.status()['state'],'cancelled');adb.assert_not_called()
        self.assertEqual(self.service.records(),{self.old['id']+':pc':self.old})
        self.assertEqual((server.DATA_DIR/'store/installed.json').read_bytes(),self.before)

    def test_cancel_while_checking_approved_catalog(self):self.exercise('catalog')
    def test_cancel_during_download_keeps_original_library(self):self.exercise('download')

    def test_stale_cancellation_cannot_cancel_another_job_or_a_commit(self):
        self.service.cancel_event=threading.Event()
        self.service.job=dict(state='running',request_id='new',can_cancel=True)
        with self.assertRaises(store.StoreError):self.service.cancel(dict(request_id='old'))
        self.assertFalse(self.service.cancel_event.is_set())
        self.service.job['can_cancel']=False
        with self.assertRaises(store.StoreError):self.service.cancel(dict(request_id='new'))
        self.assertFalse(self.service.cancel_event.is_set())

    def test_cancel_endpoint_requires_session_and_current_request(self):
        client=server.app.test_client();headers={'Host':'127.0.0.1:8741','X-Studio-Token':server.SESSION_TOKEN}
        self.assertEqual(client.post('/api/store/cancel',headers={'Host':headers['Host']},json={}).status_code,403)
        with patch.object(server.store,'cancel',side_effect=store.StoreError('This update changed.')):
            self.assertEqual(client.post('/api/store/cancel',headers=headers,json=dict(request_id='old')).status_code,400)
