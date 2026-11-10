"""Offline B1/B5 security and transport checks; never exercises ChatGPT UI."""
from pathlib import Path
import tempfile
import threading
import unittest
from urllib.error import HTTPError
from urllib.request import Request, build_opener, ProxyHandler

from baton_remote_b1.agent import Gateway, load_token_file
from baton_remote_b1.client import request_status

TOKEN = '0123456789abcdef0123456789abcdef01234567'


class BatonRemoteTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.pause = Path(self.temp.name) / 'PAUSE_UI_WRITES'
        self.server = Gateway(0, TOKEN, self.pause)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.addCleanup(self._shutdown)
        self.url = 'http://127.0.0.1:%d' % self.server.server_port
        self.opener = build_opener(ProxyHandler({}))

    def _shutdown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=2)

    def raw(self, path, token=None, method='GET', host=None):
        headers = {}
        if token is not None:
            headers['Authorization'] = 'Bearer ' + token
        if host is not None:
            headers['Host'] = host
        request = Request(self.url + path, headers=headers, method=method)
        try:
            with self.opener.open(request, timeout=2) as response:
                return response.status, response.read(), dict(response.headers)
        except HTTPError as exc:
            return exc.code, exc.read(), dict(exc.headers)

    def test_health_authenticated(self):
        result = request_status(self.url, TOKEN, 'health')
        self.assertEqual(result['status'], 'ok')
        self.assertEqual(result['mode'], 'read-only')

    def test_missing_or_wrong_token_rejected(self):
        self.assertEqual(self.raw('/v1/health')[0], 401)
        self.assertEqual(self.raw('/v1/health', 'wrong')[0], 401)

    def test_host_header_rejected(self):
        self.assertEqual(self.raw('/v1/health', TOKEN, host='attacker.example')[0], 403)

    def test_no_general_shell_or_write(self):
        self.assertEqual(self.raw('/v1/exec?cmd=id', TOKEN)[0], 404)
        self.assertEqual(self.raw('/v1/health', TOKEN, method='POST')[0], 405)
        self.assertEqual(self.raw('/v1/pause-status', TOKEN, method='DELETE')[0], 405)

    def test_pause_presence_and_symlink_fail_closed(self):
        self.assertFalse(request_status(self.url, TOKEN, 'pause-status')['ui_writes_paused'])
        self.pause.touch()
        self.assertTrue(request_status(self.url, TOKEN, 'pause-status')['ui_writes_paused'])
        self.pause.unlink()
        self.pause.symlink_to(self.pause.parent / 'missing')
        self.assertTrue(request_status(self.url, TOKEN, 'pause-status')['ui_writes_paused'])

    def test_client_rejects_remote_or_unlisted_operation(self):
        for url in ['http://example.org:1234', 'https://127.0.0.1:8765', 'http://user@127.0.0.1:8765', 'http://127.0.0.1:8765/a']:
            with self.subTest(url=url), self.assertRaises(ValueError):
                request_status(url, TOKEN, 'health')
        with self.assertRaises(ValueError):
            request_status(self.url, TOKEN, 'shell')

    def test_no_store_headers(self):
        code, _, headers = self.raw('/v1/health', TOKEN)
        self.assertEqual(code, 200)
        self.assertEqual(headers['Cache-Control'], 'no-store')
        self.assertEqual(headers['X-Content-Type-Options'], 'nosniff')

    def test_missing_pause_parent_fails_closed(self):
        self.server.pause_file = self.pause.parent / 'missing-dir' / 'PAUSE_UI_WRITES'
        self.assertTrue(request_status(self.url, TOKEN, 'pause-status')['ui_writes_paused'])

    def test_symlinked_pause_parent_fails_closed(self):
        real = self.pause.parent / 'real'
        real.mkdir()
        link = self.pause.parent / 'alias'
        link.symlink_to(real, target_is_directory=True)
        self.server.pause_file = link / 'PAUSE_UI_WRITES'
        self.assertTrue(request_status(self.url, TOKEN, 'pause-status')['ui_writes_paused'])

    def test_dangling_symlinked_pause_parent_fails_closed(self):
        link = self.pause.parent / 'dangling-parent'
        link.symlink_to(self.pause.parent / 'missing', target_is_directory=True)
        self.server.pause_file = link / 'PAUSE_UI_WRITES'
        self.assertTrue(request_status(self.url, TOKEN, 'pause-status')['ui_writes_paused'])

    def test_relative_and_parent_traversal_paths_fail_closed(self):
        self.server.pause_file = Path('PAUSE_UI_WRITES')
        self.assertTrue(request_status(self.url, TOKEN, 'pause-status')['ui_writes_paused'])
        self.server.pause_file = self.pause.parent / '..' / 'PAUSE_UI_WRITES'
        self.assertTrue(request_status(self.url, TOKEN, 'pause-status')['ui_writes_paused'])

    def test_restart_reuses_token_without_side_effects(self):
        self.assertFalse(request_status(self.url, TOKEN, 'pause-status')['ui_writes_paused'])
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=2)
        self.server = Gateway(0, TOKEN, self.pause)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.url = 'http://127.0.0.1:%d' % self.server.server_port
        self.assertEqual(request_status(self.url, TOKEN, 'health')['status'], 'ok')

    def test_token_file_permissions_and_symlink(self):
        p = Path(self.temp.name) / 'token'
        p.write_text(TOKEN + '\n')
        p.chmod(0o600)
        self.assertEqual(load_token_file(p), TOKEN)
        p.chmod(0o644)
        with self.assertRaises(PermissionError):
            load_token_file(p)
        p.chmod(0o600)
        link = Path(self.temp.name) / 'link'
        link.symlink_to(p)
        with self.assertRaises(OSError):
            load_token_file(link)

    def test_no_secrets_in_health_response(self):
        _, body, _ = self.raw('/v1/health', TOKEN)
        self.assertNotIn(TOKEN.encode(), body)
        self.assertNotIn(str(self.pause).encode(), body)


if __name__ == '__main__':
    unittest.main()
