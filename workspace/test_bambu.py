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
from native_widgets import NativeWidgets, alert_options, alert_pcm
import server


def profile(key='a'):
    return dict(id=key*32, name='Workshop '+key, host='192.168.1.30', serial='SERIAL123'+key,
                code='LAN12345', pin='b'*64, controls=False)


class ProtocolTests(unittest.TestCase):
    def test_print_alerts_follow_live_transitions_and_ignore_repeated_reports(self):
        state = bambu.State()

        def report(now, **values):
            state.accept(dict(print=dict(command='push_status', **values)), now)

        report(10, gcode_state='FINISH')
        report(11, gcode_state='RUNNING', print_error=0)
        report(12, gcode_state='PAUSE', print_error=0x03008005)
        report(13, print_error=0x03008005)
        report(14, gcode_state='RUNNING', print_error=0)
        report(15, gcode_state='FINISH')
        report(16, gcode_state='FINISH')
        self.assertEqual(list(state.alerts), [('error', 12), ('success', 15)])

    def test_print_alerts_ignore_programmed_pause_cancel_and_stale_transitions(self):
        state = bambu.State()
        for now, status, error in [
            (10, 'RUNNING', 0), (11, 'PAUSE', 0x03008013),
            (12, 'FAILED', 0x0300400C), (13, 'PREPARE', 0),
            (50, 'FINISH', 0), (51, 'RUNNING', 0), (52, 'FAILED', 0),
        ]:
            state.accept(dict(print=dict(command='push_status', gcode_state=status, print_error=error)), now)
        self.assertEqual(list(state.alerts), [('error', 52)])

    def test_print_alert_delivery_is_per_printer_and_expires(self):
        printers = bambu.Printers(None)
        one, two = 'a' * 32, 'b' * 32
        printers.active = {one, two}
        for key in printers.active:
            printers.links[key] = bambu.Link(profile(key[0]))
            printers.links[key].state.alerts.extend([('success', 90), ('error', 99)])
        specs = {
            'quiet': dict(kind='bambu', printerId=one, printAlerts=True, wakeOnAlert=False),
            'wake': dict(kind='bambu', printerId=one, printAlerts=True),
            'off': dict(kind='bambu', printerId=two),
        }
        options = alert_options(specs)
        self.assertEqual(options, {one: True})
        with patch.object(bambu.time, 'monotonic', return_value=100):
            self.assertEqual(printers.take_alerts(options), [('error', 99, one)])
            self.assertEqual(printers.take_alerts(options), [])
        self.assertNotEqual(alert_pcm('success'), alert_pcm('error'))
        self.assertLessEqual(len(alert_pcm('success')), 25000)

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

    def test_h3c_publishes_all_nine_printtools_to_core_across_swaps(self):
        printer = dict(profile(), model='h3c')
        manager = bambu.Printers(None)
        link = manager.links[printer['id']] = bambu.Link(printer)
        link.connected = True
        rack = [dict(id=16 + slot, addr_id=slot, temp=30 + slot) for slot in range(1, 9)]
        mounted = dict(id=0, addr_id=0, temp=(220 << 16) | 218)

        def accept(now, **devices):
            link.state.accept(dict(print=dict(command='push_status', device=devices)), now)

        accept(100, extruder=dict(info=[dict(id=0, temp=mounted['temp'])]), nozzle=dict(info=[mounted, *rack]))
        temperatures = [218, *range(31, 39)]
        with patch.object(bambu.time, 'monotonic', return_value=105):
            payload = manager.sample()[printer['id']]
            self.assertTrue(payload['fresh'])
            self.assertEqual(payload['nozzle_readings'], [
                dict(tool=slot, temperature=value) for slot, value in enumerate(temperatures)
            ])
            self.assertEqual(payload['nozzle_temper'], 218)

            accept(102, nozzle=dict(info=[dict(id=16, addr_id=0, temp=175), dict(id=0, addr_id=8, temp=195)]))
            accept(103, nozzle=dict(info=[dict(id=0, addr_id=8), dict(id=16, addr_id=8, temp=1), None]))
            temperatures[0], temperatures[8] = 175, 195
            self.assertEqual(manager.sample()[printer['id']]['nozzle_readings'], [
                dict(tool=slot, temperature=value) for slot, value in enumerate(temperatures)
            ])

    def test_h2c_keeps_mounted_nozzle_readings_when_rack_has_no_temperatures(self):
        link = bambu.Link(dict(profile(), model='h2c'))
        link.state.accept(dict(print=dict(command='push_status', device=dict(
            extruder=dict(info=[dict(id=0, temp=44), dict(id=1, temp=40)]),
            nozzle=dict(info=[dict(id=0), dict(id=1), dict(id=16), dict(id=17)]),
        ))), 100)
        self.assertEqual(link.snapshot()['nozzle_readings'], [
            dict(tool=0, temperature=44), dict(tool=1, temperature=40),
        ])

    def test_signed_print_mode_keeps_known_lights_available_and_hides_print_controls(self):
        for flags in ('27FF1AFFF9CB7', 0x20000000):
            with self.subTest(flags=flags):
                data=profile();data['controls']=True;link=bambu.Link(data);link.connected=True
                now=time.monotonic()
                link.state.accept(dict(print=dict(command='push_status',gcode_state='RUNNING',fun=flags,lights_report=[dict(node='chamber_light',mode='on')])),now)
                status=link.snapshot()
                self.assertTrue(status['fresh']);self.assertTrue(status['can_light_off'])
                self.assertFalse(status['can_pause']);self.assertFalse(status['can_stop'])
                self.assertFalse(status['print_controls_available'])
                self.assertIn('Developer Mode',status['control_reason'])
                self.assertFalse(link.request('pause'));self.assertTrue(link.request('light_off'))
                self.assertFalse(link.snapshot()['can_light_off']) # pending command gate still applies
                link.close()

    def test_developer_mode_state_and_enable_switch_are_separate_from_job_state(self):
        data=profile();data['controls']=True;link=bambu.Link(data);link.connected=True
        now=time.monotonic()
        link.state.accept(dict(print=dict(command='push_status',gcode_state='IDLE',fun=0,lights_report=[dict(node='chamber_light',mode='off')])),now)
        self.assertTrue(link.snapshot()['print_controls_available'])
        self.assertFalse(link.snapshot()['can_pause']);self.assertTrue(link.snapshot()['can_light_on'])
        data['controls']=False
        self.assertFalse(link.snapshot()['print_controls_available']);self.assertFalse(link.snapshot()['can_light_on'])
        self.assertEqual(link.snapshot()['control_reason'],'Enable controls in Studio')
        link.close()

    def test_unknown_lights_and_stale_state_do_not_enable_commands(self):
        data=profile();data['controls']=True;link=bambu.Link(data);link.connected=True
        now=time.monotonic()
        link.state.accept(dict(print=dict(command='push_status',gcode_state='RUNNING',fun='0')),now)
        self.assertFalse(link.snapshot()['can_light_on']);self.assertTrue(link.snapshot()['can_pause'])
        link.state.report_at=now-31
        self.assertFalse(link.snapshot()['print_controls_available']);self.assertFalse(link.request('pause'))
        link.close()


class PrinterTests(unittest.TestCase):
    def test_models_preserve_legacy_credentials_and_roundtrip_without_leaking_secrets(self):
        old=profile();self.manager.store([old])
        self.assertEqual(self.manager.read(),[old])
        self.assertEqual(self.manager.listing()[0]['model'],'generic')
        self.manager.preview([old['id']])
        link=self.manager.links[old['id']]
        editable={key:value for key,value in old.items() if key not in ('pin','code')}
        self.manager.save(dict(editable,model='h2d',code=''))
        saved=self.manager.read()[0]
        self.assertEqual(saved['model'],'h2d');self.assertEqual(saved['code'],old['code'])
        self.assertEqual(saved['pin'],old['pin'])
        self.assertIs(self.manager.links[old['id']],link)
        self.verify.assert_not_called()
        self.start.assert_called_once()
        self.assertEqual(self.manager.listing()[0]['model'],'h2d')
        self.assertEqual(self.manager.links[old['id']].snapshot()['model'],'h2d')
        for change in (dict(host='192.168.1.32'),dict(serial='NEWSERIAL'),dict(code='NEW12345')):
            with self.subTest(change=change),self.assertRaisesRegex(EditError,'Approve the printer certificate'):
                self.manager.save(dict(editable,**change))
        self.manager.save(dict(old,code=''))
        self.assertEqual(self.manager.read()[0]['model'],'h2d')
        for model in ('not/a/model', {}, None):
            with self.subTest(model=model),self.assertRaises(EditError):self.manager.save(dict(old,model=model))
        self.assertEqual(self.manager.read()[0]['model'],'h2d')

    def setUp(self):
        temp=tempfile.TemporaryDirectory();self.addCleanup(temp.cleanup)
        self.root=Path(temp.name);self.context=SimpleNamespace(DATA_DIR=self.root)
        self.manager=bambu.Printers(self.context)
        self.start=patch.object(bambu.Link,'start').start();self.addCleanup(patch.stopall)
        self.verify=patch.object(bambu,'verify_connection').start()

    def test_reject_failed_connection_before_writing_or_replacing_a_saved_printer(self):
        original=profile();self.manager.store([original])
        self.verify.side_effect=EditError('The printer rejected the LAN access code.')
        with self.assertRaisesRegex(EditError, 'rejected'):
            self.manager.save(dict(original,code='WRONG123'))
        self.assertEqual(self.manager.read(),[original])
        self.start.assert_not_called()

    def test_preview_connects_only_selected_saved_printers(self):
        one,two=profile('a'),profile('b')
        self.manager.store([one,two])
        result=self.manager.preview([two['id'],'c'*32])
        self.assertEqual(set(result),{two['id']})
        self.assertNotIn('code',result[two['id']])
        self.assertNotIn('pin',result[two['id']])
        self.manager.preview([two['id']])
        self.start.assert_called_once()

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
        with self.assertRaises(EditError):self.manager.validate({'widget':dict(kind='bambu')})
        with self.assertRaises(EditError):self.manager.validate({'widget':dict(kind='bambu',printerId='a'*32)})
        self.manager.validate({'widget':dict(kind='cpu')})
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

    def test_verify_connection_requires_login_and_accepted_report_subscription(self):
        data=dict(profile(),pin=self.pin)
        for accepted,subscribed in ((True,True),(True,False),(False,False)):
            with self.subTest(accepted=accepted,subscribed=subscribed):
                def printer(stream):
                    header,body=bambu.read(stream)
                    self.assertEqual(header,0x10)
                    self.assertIn(data['code'].encode(),body)
                    bambu.write(stream,0x20,b'\x00\x00' if accepted else b'\x00\x04')
                    if accepted:
                        header,body=bambu.read(stream)
                        self.assertEqual(header,0x82)
                        self.assertIn(('device/'+data['serial']+'/report').encode(),body)
                        bambu.write(stream,0x90,b'\x00\x01\x01' if subscribed else b'\x00\x01\x80')

                redirect,thread,errors=self.printer(printer)
                with redirect:
                    if subscribed:
                        bambu.verify_connection(data)
                    else:
                        expected='report subscription' if accepted else 'LAN access code'
                        with self.assertRaisesRegex(EditError,expected):bambu.verify_connection(data)
                thread.join(9)
                self.assertFalse(thread.is_alive())
                self.assertFalse(errors,errors)

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
