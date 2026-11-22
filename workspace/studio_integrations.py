"""Package-scoped operations for trusted Studio connection providers."""
import re
from flask import jsonify, request
import bambu
import studio_contract
from editor import EditError


OPERATIONS = {'list', 'discover', 'probe', 'save', 'remove', 'reconnect', 'preview'}


class BambuLan:
    """Keeps printer protocol, certificate approval and private storage authoritative."""
    def __init__(self, server):
        self.manager = server.bambu

    def invoke(self, operation, body):
        if operation == 'list':
            return dict(items=self.manager.listing())
        if operation == 'discover':
            if body:
                raise EditError('Discovery does not accept connection parameters.')
            return dict(items=bambu.discover())
        if operation == 'probe':
            if set(body) != {'host'}:
                raise EditError('Choose a local device address to test.')
            host = bambu.private_host(body['host'])
            try:
                stream, pin = bambu.tls(host)
                stream.close()
                return dict(pin=pin)
            except (OSError, ValueError) as exc:
                raise EditError('Could not read the device certificate. Check its IP, LAN mode and network access from this PC.') from exc
        if operation == 'save':
            key = self.manager.save(body)
            return dict(id=key, items=self.manager.listing())
        if operation == 'preview':
            ids = body.get('ids')
            if set(body) != {'ids'} or not isinstance(ids, list) or len(ids) > 16 or any(
                    not isinstance(key, str) or not re.fullmatch('[a-f0-9]{32}', key) for key in ids):
                raise EditError('Choose saved printers to preview.')
            return dict(printers=self.manager.preview(dict.fromkeys(ids)))
        if set(body) != {'id'} or not isinstance(body['id'], str):
            raise EditError('Choose a saved connection.')
        key = body['id']
        if operation == 'remove':
            self.manager.remove(key)
        elif operation == 'reconnect':
            with self.manager.lock:
                profile = next((p for p in self.manager.read() if p['id'] == key), None)
                if profile is None:
                    raise EditError('Unknown connection.')
                if key in self.manager.links:
                    self.manager.links.pop(key).close()
                link = self.manager.links[key] = bambu.Link(profile)
                link.start()
        return dict(items=self.manager.listing())


# Only compiled-in adapters may execute operations. App packages supply UI data.
PROVIDERS = {'bambu-lan': BambuLan}


def descriptor(server, package, widget):
    with server.store.lock:
        records = server.store.records()
        record = next((p for p in records.values() if p.get('id') == package and (p.get('type') in ('corebar-widget', 'studio-plugin') or p.get('bundledWidgets'))), None)
        template = next((w for w in record.get('widgets', []) if w.get('id') == widget), None) if record else None
        if template is None:
            raise EditError('This app widget is no longer installed. Reinstall it before managing its connections.')
        try:
            panel = studio_contract.resolve(template)
        except ValueError as exc:
            raise EditError('The app connection descriptor is invalid. Update or reinstall the app.') from exc
        connection = panel.get('connection') if panel else None
        if not connection or connection['provider'] not in PROVIDERS:
            raise EditError('This app widget does not provide a supported connection panel.')
        return connection


def register(server):
    @server.app.route('/api/studio/integrations/<package>/<widget>/<operation>', methods=['GET', 'POST'])
    def integration_operation(package, widget, operation):
        if operation not in OPERATIONS or (request.method == 'GET') != (operation == 'list'):
            raise EditError('Unsupported app connection operation.')
        connection = descriptor(server, package, widget)
        body = {} if request.method == 'GET' else request.get_json(silent=True)
        if not isinstance(body, dict):
            raise EditError('App connection parameters must be an object.')
        if operation == 'save':
            for field in connection['fields']:
                if field['type'] != 'choice':
                    continue
                key = field['key']
                value = body.get(key)
                if connection['provider'] == 'bambu-lan' and key == 'model' and value in (None, '', 'generic'):
                    raise EditError('Choose a printer model.')
                if key in body and value not in [option['value'] for option in field['options']]:
                    raise EditError('Choose one of this package\'s '+field['label']+' options.')
        return jsonify(PROVIDERS[connection['provider']](server).invoke(operation, body))
