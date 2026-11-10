"""Static B5 service-template guard; not a live systemd/Greg verification."""
from pathlib import Path
import unittest


UNIT = Path(__file__).resolve().parents[1] / 'deploy/systemd/baton-remote-ingress.service'


class ServiceManifestTests(unittest.TestCase):
    def test_receive_only_and_explicit_route(self):
        text = UNIT.read_text(encoding='utf-8')
        self.assertIn('-m remote_security.http_ingress', text)
        self.assertIn('--route sender000=target000', text)
        self.assertIn('--target target000', text)
        self.assertIn('--port 8788', text)
        self.assertNotIn('0.0.0.0', text)
        self.assertNotIn('chatgpt_ui_driver', text)
        self.assertNotIn('run_chatgpt_wake', text)
        self.assertNotIn('ExecStart=/bin/sh', text)

    def test_user_service_has_bounded_restart_and_read_only_home(self):
        text = UNIT.read_text(encoding='utf-8')
        self.assertIn('NoNewPrivileges=true', text)
        self.assertIn('ProtectSystem=strict', text)
        self.assertIn('ProtectHome=read-only', text)
        self.assertIn('ReadWritePaths=%h/.local/state/baton-remote', text)
        self.assertIn('UMask=0077', text)
        self.assertIn('Restart=on-failure', text)
        self.assertIn('StartLimitBurst=3', text)
        self.assertNotIn('User=root', text)
        self.assertNotIn('Restart=always', text)


if __name__ == '__main__':
    unittest.main()
