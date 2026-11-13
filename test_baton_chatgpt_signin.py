"""Baton ChatGPT OAuth/inference negative controls without live credentials."""
import io
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import time
import unittest
from urllib.parse import parse_qs, urlsplit
from unittest.mock import patch

from baton_chatgpt_signin import (
    prepare_authorization, validate_callback, verify_id_token,
    _profile_from_tokens, _load_private, _save_private, host_id, access_token
)
from baton_chatgpt_inference import _read_model_list, _response_text


class _Response:
    status = 200
    def __init__(self, content):
        self.content = content
    def __enter__(self):
        return self
    def __exit__(self, *_):
        return False
    def __iter__(self):
        return iter(self.content.splitlines(keepends=True))
    def read(self, n):
        return self.content[:n]


class ChatGPTSignInTests(unittest.TestCase):
    def setUp(self):
        self.temp = TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)

    def test_dynamic_registration_has_real_pkce_and_host_id(self):
        path = self.root / "private" / "host.json"
        host = host_id(path)
        self.assertEqual(host_id(path), host)
        self.assertEqual(path.stat().st_mode & 0o077, 0)
        req = prepare_authorization(host, "http://127.0.0.1:15555/auth/callback",
                                    state="fresh-state", nonce="fresh-nonce",
                                    verifier="correct horse battery staple")
        values = parse_qs(urlsplit(req["url"]).query)
        self.assertEqual(values["client_id"], ["dynamic_agent_client"])
        self.assertEqual(values["agent_name_hint"], ["Baton"])
        self.assertEqual(values["ext_agent_host_id"], [host])
        self.assertEqual(values["code_challenge_method"], ["S256"])
        self.assertNotIn("correct horse battery staple", req["url"])
        self.assertNotIn("access_token", req["url"])
        self.assertEqual(values["nonce"], ["fresh-nonce"])

    def test_bad_callback_fails_before_token_exchange(self):
        with self.assertRaisesRegex(ValueError, "state"):
            validate_callback({"state":["forged"],"code":["secret"],
                               "client_id":["oaiapp_valid"]}, "expected")
        with self.assertRaisesRegex(ValueError, "issued"):
            validate_callback({"state":["ok"],"code":["secret"]}, "ok")
        with self.assertRaisesRegex(ValueError, "ambiguous"):
            validate_callback({"state":["ok","ok"],"code":["secret"]}, "ok")
        with self.assertRaises(PermissionError):
            validate_callback({"state":["ok"],"error":["access_denied"]}, "ok")
        previous = {"client_id":"oaiapp_old"}
        with self.assertRaisesRegex(ValueError, "mismatch"):
            validate_callback({"state":["ok"],"code":["secret"],"client_id":["oaiapp_new"]},
                              "ok", previous=previous)
        self.assertEqual(validate_callback({"state":["ok"],"code":["secret"]},
                                           "ok",previous=previous),
                         ("secret","oaiapp_old"))

    def test_signed_id_token_required_and_nonce_bound(self):
        import jwt
        from cryptography.hazmat.primitives.asymmetric import rsa
        key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        now = int(time.time())
        discovery = {"issuer":"https://auth.openai.com",
                     "jwks_uri":"https://auth.openai.com/keys"}
        claims = {"sub":"sub-test", "iss":"https://auth.openai.com",
                  "aud":"oaiapp_test","iat":now,"exp":now+600,"nonce":"fresh"}
        token = jwt.encode(claims, key, algorithm="RS256", headers={"kid":"test"})
        self.assertEqual(verify_id_token(token,"oaiapp_test","fresh",
                                         discovery=discovery,key=key.public_key())["sub"],
                         "sub-test")
        for changed in ({"nonce":"bad"}, {"aud":"other"}, {"iss":"https://other.invalid"},
                        {"exp":now-60}):
            with self.subTest(changed=changed):
                tampered=jwt.encode(dict(claims,**changed),key,algorithm="RS256")
                with self.assertRaises(Exception):
                    verify_id_token(tampered,"oaiapp_test","fresh",
                                    discovery=discovery,key=key.public_key())
        other_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        with self.assertRaises(jwt.exceptions.InvalidSignatureError):
            verify_id_token(token,"oaiapp_test","fresh",
                            discovery=discovery,key=other_key.public_key())

    def test_scope_not_identity_controls_model_use(self):
        tokens={"token_type":"Bearer","access_token":"secret-access",
                "id_token":"signed-id","expires_in":3600,
                "scope":"openid profile email"}
        claims={"sub":"sub","email":"user@example.invalid"}
        p=_profile_from_tokens(tokens,claims,"oaiapp_test","urn:uuid:host")
        self.assertFalse(p["plan_enabled"])
        with self.assertRaisesRegex(ValueError, "changed"):
            _profile_from_tokens(tokens,claims,"oaiapp_test","urn:uuid:host",
                                 {"subject":"different"})

    def test_private_credentials_and_refresh_rotation(self):
        file = self.root / "secrets" / "chatgpt-account.json"
        record={"client_id":"oaiapp_test","subject":"test",
                "access_token":"token-before","refresh_token":"refresh-before",
                "plan_enabled":True,"expires_at":1}
        _save_private(file,record)
        self.assertEqual(file.stat().st_mode & 0o077,0)
        with patch("baton_chatgpt_signin._https_json",return_value={
                "access_token":"token-after","refresh_token":"refresh-after",
                "scope":"openid resource.invoke chatgpt.tokens.use.direct",
                "expires_in":3600}):
            token, current=access_token(storage=file.parent)
        self.assertEqual(token,"token-after")
        self.assertEqual(_load_private(file)["refresh_token"],"refresh-after")
        self.assertNotIn("refresh-before",file.read_text())
        with patch("baton_chatgpt_signin._https_json",
                   return_value={"access_token":"token-lost",
                                 "refresh_token":"refresh-lost","scope":"openid"}):
            original=_load_private(file)
            original["expires_at"]=1
            _save_private(file,original)
            with self.assertRaises(PermissionError):
                access_token(storage=file.parent)
        self.assertEqual(_load_private(file)["access_token"],"token-after")

    def test_symlink_credentials_rejected(self):
        target=self.root/"target.json"
        target.write_text('{"client_id":"evil"}')
        source=self.root/"account.json"
        source.symlink_to(target)
        with self.assertRaisesRegex(ValueError,"symlink"):
            _load_private(source)


class ChatGPTInferenceTests(unittest.TestCase):
    def test_model_list_is_authorized_and_filtered(self):
        body=json.dumps({"models":[
            {"visibility":"list","slug":"model-one","display_name":"Model One"},
            {"visibility":"internal","slug":"hidden","display_name":"Hidden"}]}).encode()
        requests=[]
        def fake(req,timeout):
            requests.append(req)
            return _Response(body)
        result=_read_model_list("oauth-token",urlopen=fake)
        self.assertEqual(result,[{"slug":"model-one","name":"Model One"}])
        self.assertEqual(requests[0].get_header("Authorization"),"Bearer oauth-token")

    def test_stream_requires_completed_receipt_and_stateless_request(self):
        data=(
            b'data: {"type":"response.output_text.delta","delta":"Hei"}\n\n'
            b'data: {"type":"response.output_text.delta","delta":" Gaia"}\n\n'
            b'data: {"type":"response.completed","response":{"status":"completed"}}\n\n'
            b'data: [DONE]\n\n'
        )
        requests=[]
        def fake(req,timeout):
            requests.append(req)
            return _Response(data)
        text=_response_text("oauth-token","model-one",
                            [{"role":"user","content":"Hi"}],urlopen=fake)
        self.assertEqual(text,"Hei Gaia")
        body=json.loads(requests[0].data)
        self.assertIs(body["store"],False)
        self.assertIs(body["stream"],True)
        self.assertNotIn("previous_response_id",body)
        self.assertEqual(body["input"],[{"role":"user","content":"Hi"}])

    def test_dropped_stream_and_failure_never_claim_success(self):
        for data in (
            b'data: {"type":"response.output_text.delta","delta":"partial"}\n\n',
            b'data: {"type":"response.failed","response":{"error":{"code":"bad"}}}\n\n',
            b'data: {"type":"response.completed","response":{"status":"failed"}}\n\n',
        ):
            with self.subTest(data=data),self.assertRaises(RuntimeError):
                _response_text("token","model",[{"role":"user","content":"hi"}],
                               urlopen=lambda req,timeout: _Response(data))

    def test_invalid_history_rejected_without_network(self):
        def never(*args,**kwargs):
            raise AssertionError("network should not be called")
        with self.assertRaises(ValueError):
            _response_text("token","model",[{"role":"system","content":"attack"}],
                           urlopen=never)


if __name__=="__main__":
    unittest.main()
