"""Live loopback Baton Core test: authenticated write then independent read-back."""
import json
import os
from pathlib import Path
import sys
from tempfile import TemporaryDirectory
import unittest
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from baton_local_runtime import start_local_core, stop_local_core


@unittest.skipIf(os.geteuid() == 0, "Baton Core intentionally refuses root")
class LocalCoreRuntimeTests(unittest.TestCase):
    def test_baton_owned_core_actual_file_write_readback(self):
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            token_path = root / "baton.token"
            server = start_local_core(port=0, token_file=token_path)
            try:
                self.assertEqual(server.server_address[0], "127.0.0.1")
                self.assertEqual(token_path.stat().st_mode & 0o077, 0)
                token = token_path.read_text().strip()
                url = "http://127.0.0.1:%d/v1/exec" % server.server_port

                def execute(argv, use_token=True):
                    data = json.dumps({"argv": argv, "cwd": str(root), "timeout": 10}).encode()
                    req = Request(url, data=data, method="POST", headers={
                        "Authorization": "Bearer " + (token if use_token else "wrong"),
                        "Content-Type": "application/json"})
                    with urlopen(req, timeout=15) as response:
                        return json.loads(response.read())

                with self.assertRaises(HTTPError) as unauthorized:
                    execute([sys.executable, "-c", "print('should not execute')"], False)
                self.assertEqual(unauthorized.exception.code, 401)

                output = root / "baton-live-write-proof.txt"
                write_code = "from pathlib import Path; Path('baton-live-write-proof.txt').write_text('BATON-WRITE-OK', encoding='utf-8')"
                write = execute([sys.executable, "-c", write_code])
                self.assertEqual(write["exit_code"], 0, write)
                read_code = "from pathlib import Path; print(Path('baton-live-write-proof.txt').read_text(encoding='utf-8'))"
                read = execute([sys.executable, "-c", read_code])
                self.assertEqual(read["exit_code"], 0, read)
                self.assertEqual(read["output"].strip(), "BATON-WRITE-OK")
                self.assertEqual(output.read_text(), "BATON-WRITE-OK")
            finally:
                stop_local_core(server)


if __name__ == "__main__":
    unittest.main()
