"""Installer tests: no system writes and no browser auto-install."""
import json
from pathlib import Path
import shutil
from tempfile import TemporaryDirectory
import unittest

from install_baton_browser_bridge import install_bridge, EXPECTED_EXTENSION_ID


class NativeInstallerTests(unittest.TestCase):
    def setUp(self):
        self.temp=TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name)/"checkout"
        self.home=Path(self.temp.name)/"home"
        (self.root/"baton_extension").mkdir(parents=True)
        shutil.copyfile(
            Path(__file__).with_name("baton_extension")/"manifest.json",
            self.root/"baton_extension"/"manifest.json"
        )
        (self.root/"baton_browser_native_host.py").write_text("# test\n")
        self.home.mkdir()

    def install(self):
        return install_bridge(root=self.root,home=self.home,
            browsers=(".config/BraveSoftware/Brave-Browser/NativeMessagingHosts",))

    def test_register_just_one_verified_extension_without_root(self):
        data=self.install()
        self.assertEqual(data["extension_id"],EXPECTED_EXTENSION_ID)
        native=Path(data["host_launcher"])
        self.assertTrue(native.is_file())
        self.assertEqual(native.stat().st_mode & 0o077,0)
        self.assertIn(str(self.root/"baton_browser_native_host.py"),native.read_text())
        manifest=self.home/".config/BraveSoftware/Brave-Browser/NativeMessagingHosts/com.baton.greg.json"
        obj=json.loads(manifest.read_text())
        self.assertEqual(obj["name"],"com.baton.greg")
        self.assertEqual(obj["path"],str(native))
        self.assertEqual(obj["allowed_origins"],
                         ["chrome-extension://"+EXPECTED_EXTENSION_ID+"/"])
        self.assertEqual(manifest.stat().st_mode & 0o077,0)
        self.assertEqual(self.install()["extension_id"],EXPECTED_EXTENSION_ID)

    def test_refuse_unknown_preexisting_host(self):
        path=self.home/".config/BraveSoftware/Brave-Browser/NativeMessagingHosts/com.baton.greg.json"
        path.parent.mkdir(parents=True)
        path.write_text('{"name":"not-baton","allowed_origins":[]}')
        with self.assertRaisesRegex(ValueError,"different"):
            self.install()
        self.assertIn("not-baton",path.read_text())

    def test_reject_registration_symlink(self):
        path=self.home/".config/BraveSoftware/Brave-Browser/NativeMessagingHosts/com.baton.greg.json"
        path.parent.mkdir(parents=True)
        target=self.home/"other"
        target.write_text("protected")
        path.symlink_to(target)
        with self.assertRaisesRegex(ValueError,"linked"):
            self.install()
        self.assertEqual(target.read_text(),"protected")

    def test_reject_extension_key_mismatch(self):
        path=self.root/"baton_extension"/"manifest.json"
        data=json.loads(path.read_text())
        data["key"]="YXR0YWNr"
        path.write_text(json.dumps(data))
        with self.assertRaisesRegex(ValueError,"identity changed"):
            self.install()

    def test_does_not_overwrite_unrelated_launcher(self):
        dest=self.home/".local/bin/baton-browser-native-host"
        dest.parent.mkdir(parents=True)
        dest.write_text("#!/bin/sh\necho other\n")
        with self.assertRaisesRegex(ValueError,"unrelated"):
            self.install()
        self.assertIn("other",dest.read_text())


if __name__=="__main__":
    unittest.main()
