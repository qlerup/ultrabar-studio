"""Offline protocol, Windows storage and Studio transport regression checks."""
import base64
import copy
import hashlib
import json
import os
from pathlib import Path
import socket
import ssl
import struct
import subprocess
import tempfile
import threading
import time
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch
import bambu
from editor import EditError
from native_widgets import NativeWidgets
import server


def profile(key='a'):
    return dict(id=key*32, name='Workshop '+key, host='192.168.1.30', serial='SERIAL123'+key,
                code='LAN12345', pin='b'*64, controls=False)


class ProtocolTests(unittest.TestCase):
    def test_discovery_uses_peer_and_never_follows_advertised_urls(self):
        raw=b'HTTP/1.1 200 OK\r\nST: urn:bambulab-com:device:3dprinter:1\r\nUSN: SERIAL123\r\nDevName.bambu.com: Workshop\r\nLOCATION: http://127.0.0.1/private\r\n\r\n'
        found=bambu.announcement(raw,'192.168.1.20')
        self.assertEqual(found,dict(host='192.168.1.20',name='Workshop',serial='SERIAL123'))
        self.assertIsNone(bambu.announcement(raw,'8.8.8.8'))
        self.assertIsNone(bambu.announcement(raw+b'USN: DIFFERENT123\r\n','192.168.1.20'))
        self.assertIsNone(bambu.announcement(b'x'*8193,'192.168.1.20'))

    def test_framing_bounds_and_partial_reads(self):
        class Stream:
            def __init__(self, raw): self.raw=bytearray(raw)
            def recv(self, size):
                result=bytes(self.raw[:min(size,2)]);del self.raw[:len(result)];return result
        output=Mock();bambu.write(output,0x32,b'hello'*50)
        raw=output.sendall.call_args.args[0]
        self.assertEqual(bambu.read(Stream(raw)),(0x32,b'hello'*50))
        for raw in (b'',b'\x30\xff\xff\xff\xff',b'\x30\x03x'):
            with self.assertRaises((ValueError,OSError)):bambu.read(Stream(raw))

    def test_state_freshness_packed_temperatures_and_command_confirmation(self):
        state=bambu.State()
        state.accept(dict(print=dict(command='push_status',gcode_state='RUNNING',fun='0',device=dict(
            bed=dict(info=dict(temp=(70<<16)|60)),ctc=dict(info=dict(temp=(40<<16)|35)),
            extruder=dict(state=16,info=[dict(id=0,temp=(220<<16)|210),dict(id=1,temp=(230<<16)|225)])))),10)
        self.assertTrue(state.allows('pause',11));self.assertEqual(state.data['nozzle_temper'],225)
        self.assertEqual(state.data['bed_temper'],60);self.assertEqual(state.data['chamber_temper'],35)
        self.assertFalse(state.allows('pause',41))
        state.accept(dict(print=dict(command='push_status',mc_percent=80)),42)
        self.assertTrue(state.fresh(42));self.assertFalse(state.allows('pause',42))
        self.assertFalse(state.confirmed('pause',dict(mc_percent=80)))
        self.assertTrue(state.confirmed('pause',dict(gcode_state='PAUSE')))
        state.accept(dict(print=dict(command='push_status',gcode_state='RUNNING',fun='20000000')),43)
        self.assertFalse(state.allows('pause',43))

    def test_link_commands_require_live_status_and_explicit_enable(self):
        data=profile();link=bambu.Link(data);link.connected=True
        link.state.accept(dict(print=dict(command='push_status',gcode_state='RUNNING')),time.monotonic())
        self.assertFalse(link.request('pause'));data['controls']=True
        self.assertTrue(link.request('pause'));self.assertFalse(link.request('pause'))
        snapshot=json.dumps(link.snapshot())
        for value in (data['code'],data['serial'],data['host'],data['pin']):self.assertNotIn(value,snapshot)
        link.close();self.assertFalse(link.request('pause'))


class PrinterTests(unittest.TestCase):
    def setUp(self):
        temp=tempfile.TemporaryDirectory();self.addCleanup(temp.cleanup)
        self.root=Path(temp.name);self.context=SimpleNamespace(DATA_DIR=self.root)
        self.manager=bambu.Printers(self.context)
        self.start=patch.object(bambu.Link,'start').start();self.addCleanup(patch.stopall)

    @unittest.skipUnless(os.name=='nt','Windows DPAPI')
    def test_encrypted_connections_edit_remove_and_independent_live_links(self):
        one=profile('a');two=profile('c');two['host']='192.168.1.31'
        first=self.manager.save({k:v for k,v in one.items() if k!='id'})
        second=self.manager.save({k:v for k,v in two.items() if k!='id'})
        saved=(self.root/'bambu-connections.json').read_text()
        for value in (one['host'],one['serial'],one['code'],one['pin']):self.assertNotIn(value,saved)
        reloaded=bambu.Printers(self.context)
        self.assertEqual(len(reloaded.listing()),2)
        self.assertNotIn('code',json.dumps(reloaded.listing()))
        reloaded.configure({'widget1':dict(kind='bambu',printerId=first),'widget2':dict(kind='bambu',printerId=second)})
        self.assertEqual(set(reloaded.sample()),{first,second})
        edited=dict(one,id=first,code='',name='New name')
        self.manager.save(edited)
        self.assertEqual(self.manager.read()[0]['code'],one['code'])
        with self.assertRaises(EditError):self.manager.save(dict(edited,host='192.168.1.32'))
        self.manager.remove(first)
        self.assertEqual([p['id'] for p in self.manager.read()],[second])
        self.assertFalse(self.manager.links.get(first))
        reloaded.configure({});self.assertEqual(reloaded.sample(),{})

    def test_reject_invalid_addresses_codes_and_duplicate_profiles(self):
        for host in ('127.0.0.1','8.8.8.8','169.254.1.1','192.168.1.0','192.168.1.255','192.168.001.20','printer.local','10.0.0.1;id',None):
            with self.subTest(host=host),self.assertRaises(EditError):bambu.private_host(host)
        for change in (dict(code='x'),dict(pin=''),dict(controls='yes'),dict(serial='../'),dict(id='a'*32),dict(script='exec')):
            data=profile();data.pop('id');data.update(change)
            with self.assertRaises(EditError):self.manager.save(data)
        self.start.assert_not_called()

    def test_local_api_requires_session_and_does_not_export_secrets(self):
        client=server.app.test_client();headers={'Host':'127.0.0.1:8741','X-Studio-Token':server.SESSION_TOKEN}
        with patch.object(server,'bambu',self.manager):
            self.assertEqual(client.get('/api/bambu/printers',headers={'Host':headers['Host']}).status_code,403)
            self.assertEqual(client.post('/api/bambu/probe',headers=headers,json=dict(host='127.0.0.1')).status_code,400)
            self.assertEqual(client.post('/api/bambu/printers',headers=headers,json=['bad']).status_code,400)
            self.assertEqual(client.get('/api/bambu/printers',headers=headers).json,dict(printers=[]))

    def test_core_action_routing_freshness_deduplication_and_widget_binding(self):
        link=Mock();self.manager.links['a'*32]=link
        context=SimpleNamespace(bambu=self.manager)
        native=NativeWidgets(context)
        native.specs={'studio_native_'+ 'b'*32:dict(kind='bambu',printerId='a'*32,showControls=True)}
        event=dict(id='c'*32,widgetId='studio_native_'+'b'*32,printerId='a'*32,action='pause',createdAt=time.time()*1000)
        native.printer_action(event);native.printer_action(event)
        link.request.assert_called_once_with('pause')
        for change in (dict(printerId='d'*32),dict(createdAt=0),dict(action='heater'),dict(widgetId='wrong')):
            native.printer_action(dict(event,id='e'*32,**change))
        self.assertEqual(link.request.call_count,1)
        native.specs[event['widgetId']]['showControls']=False
        native.printer_action(dict(event,id='f'*32));self.assertEqual(link.request.call_count,1)


OPENSSL=Path('C:/Program Files/Git/usr/bin/openssl.exe')

@unittest.skipUnless(OPENSSL.is_file(),'OpenSSL for ephemeral fake-printer TLS certificates')
class TlsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp=tempfile.TemporaryDirectory();root=Path(cls.temp.name)
        cls.cert=root/'test-cert.pem';cls.key=root/'test-key.pem'
        subprocess.run([str(OPENSSL),'req','-x509','-newkey','rsa:2048','-nodes','-keyout',str(cls.key),'-out',str(cls.cert),'-days','1','-subj','/CN=offline-test-printer'],check=True,capture_output=True)
        cls.pin=hashlib.sha256(ssl.PEM_cert_to_DER_cert(cls.cert.read_text())).hexdigest()

    @classmethod
    def tearDownClass(cls):cls.temp.cleanup()

    def printer(self, handler):
        listener=socket.socket();listener.bind(('127.0.0.1',0));listener.listen(1);listener.settimeout(8)
        self.addCleanup(listener.close)
        errors=[]
        def run():
            try:
                context=ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER);context.maximum_version=ssl.TLSVersion.TLSv1_2;context.load_cert_chain(self.cert,self.key)
                client,_=listener.accept()
                with context.wrap_socket(client,server_side=True) as stream:
                    stream.settimeout(8);handler(stream)
            except Exception as exc:errors.append(exc)
        thread=threading.Thread(target=run,daemon=True);thread.start()
        original=socket.create_connection
        target=('127.0.0.1',listener.getsockname()[1])
        return patch.object(bambu.socket,'create_connection',side_effect=lambda *a,**k:original(target,timeout=6)),thread,errors

    def test_probe_and_changed_pin_never_send_credentials(self):
        for pin in (None,'0'*64):
            received=[]
            def receive(stream):
                try:received.append(stream.recv(4096))
                except (ConnectionResetError,ConnectionAbortedError):received.append(b'')
            redirect,thread,errors=self.printer(receive)
            with redirect:
                if pin is None:
                    stream,actual=bambu.tls('192.168.1.30');self.assertEqual(actual,self.pin);stream.close()
                else:
                    with self.assertRaises(EditError):bambu.tls('192.168.1.30',pin)
            thread.join(9);self.assertFalse(thread.is_alive());self.assertFalse(errors,errors);self.assertEqual(received,[b''])

    def test_actual_tls_mqtt_status_and_confirmed_command(self):
        ready=threading.Event();finish=threading.Event();observed=[]
        def printer(stream):
            header,body=bambu.read(stream);self.assertEqual(header,0x10);self.assertIn(b'LAN12345',body)
            bambu.write(stream,0x20,b'\x00\x00')
            header,body=bambu.read(stream);self.assertEqual(header,0x82)
            bambu.write(stream,0x90,b'\x00\x01\x01')
            header,body=bambu.read(stream);self.assertIn(b'pushall',body)
            topic=bambu.utf('device/SERIAL123a/report')
            bambu.write(stream,0x30,topic+json.dumps(dict(print=dict(command='push_status',gcode_state='RUNNING',mc_percent=42))).encode())
            ready.set()
            header,body=bambu.read(stream);self.assertEqual(header,0x32);observed.append(body)
            # PUBACK alone must not confirm a command.
            offset=2+struct.unpack('!H',body[:2])[0];bambu.write(stream,0x40,body[offset:offset+2])
            time.sleep(.15)
            bambu.write(stream,0x30,topic+json.dumps(dict(print=dict(command='push_status',gcode_state='PAUSE'))).encode())
            finish.wait(5)
        redirect,thread,errors=self.printer(printer)
        data=profile();data.update(pin=self.pin,controls=True)
        link=bambu.Link(data)
        try:
            with redirect:
                link.start();self.assertTrue(ready.wait(8))
                deadline=time.monotonic()+5
                while not link.snapshot()['fresh'] and time.monotonic()<deadline:time.sleep(.02)
                self.assertEqual(link.snapshot()['mc_percent'],42);self.assertTrue(link.request('pause'))
                while link.snapshot()['busy'] and time.monotonic()<deadline:time.sleep(.02)
                self.assertEqual(link.snapshot()['detail'],'Confirmed by printer')
                self.assertIn(b'pause',observed[0]);self.assertFalse(link.request('pause'))
        finally:
            finish.set();link.close();thread.join(9)
        self.assertFalse(thread.is_alive());self.assertFalse(errors,errors);self.assertFalse(link.snapshot()['fresh'])
