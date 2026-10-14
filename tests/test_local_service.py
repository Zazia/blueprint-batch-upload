import hashlib
import http.client
import json
from pathlib import Path
import sys
import tempfile
import threading
import unittest
from urllib.parse import quote

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from local_service import make_server


class LocalTransport(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.origin = 'http://example.test'
        self.token = 'synthetic-test-token-123456789'

    def server(self, mode, **kw):
        server = make_server(self.root, self.origin, self.token, mode, **kw)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        def close():
            server.shutdown()
            server.server_close()
            thread.join()
        self.addCleanup(close)
        return server

    def request(self, server, method, path, body=None, headers=None):
        connection = http.client.HTTPConnection('127.0.0.1', server.server_port, timeout=3)
        try:
            connection.request(method, path, body, headers if headers is not None else {'X-Upload-Token': self.token, 'Origin': self.origin})
            response = connection.getresponse()
            return response.status, dict(response.getheaders()), response.read()
        finally:
            connection.close()

    def test_file_unicode_literal_percent_and_hash(self):
        file = self.root / 'A_中文%20图.pack'
        file.write_bytes(b'opaque')
        server = self.server('files', allowed={str(file.resolve())})
        status, headers, data = self.request(server, 'GET', '/' + quote(file.name))
        self.assertEqual((status, data), (200, b'opaque'))
        self.assertEqual(headers['X-Content-SHA256'], hashlib.sha256(data).hexdigest())
        self.assertEqual(headers['Access-Control-Allow-Origin'], self.origin)
        self.assertEqual(self.request(server, 'HEAD', '/' + quote(file.name))[2], b'')

    def test_auth_cors_allowlist_and_traversal(self):
        (self.root / 'a.pack').write_bytes(b'a')
        server = self.server('files', allowed=set())
        for path in ['/a.pack', '/', '/%2e%2e/secret', '/C%3a/secret', '/x%5csecret']:
            self.assertEqual(self.request(server, 'GET', path)[0], 404)
        self.assertEqual(self.request(server, 'GET', '/a.pack', headers={})[0], 403)
        self.assertEqual(self.request(server, 'GET', '/a.pack', headers={'X-Upload-Token': self.token, 'Origin': 'http://other.test'})[0], 403)
        self.assertEqual(self.request(server, 'OPTIONS', '/', headers={'Origin': self.origin})[0], 204)
        self.assertEqual(self.request(server, 'OPTIONS', '/', headers={'Origin': 'http://other.test'})[0], 403)

    def test_receipts_do_not_overwrite_and_reject_invalid_body(self):
        server = self.server('receive', max_bytes=50)
        names = []
        for _ in range(2):
            status, _, data = self.request(server, 'POST', '/result', b'{"state":"unknown"}')
            self.assertEqual(status, 201)
            names.append(json.loads(data)['file'])
        self.assertEqual(len(set(names)), 2)
        self.assertEqual(len(list(self.root.glob('*.json'))), 2)
        for path, body in [('/../escape', b'{}'), ('/bad', b'not json'), ('/bad', b'1'), ('/big', b' ' * 51)]:
            self.assertEqual(self.request(server, 'POST', path, body)[0], 400)
        self.assertEqual(self.request(server, 'GET', '/ping')[2], b'pong')
        self.assertEqual(self.request(server, 'GET', '/result')[0], 404)


if __name__ == '__main__':
    unittest.main()
