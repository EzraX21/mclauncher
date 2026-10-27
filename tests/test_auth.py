"""微软登录链路的单元测试（全部 mock，不联网）。"""

import tempfile
import time
import unittest
from pathlib import Path
from unittest import mock

from mcl import auth


class AuthTests(unittest.TestCase):
    def test_friendly_errors(self):
        self.assertIn("公共客户端流", auth.friendly("AADSTS7000218: ..."))
        self.assertIn("client id", auth.friendly("AADSTS700016: ..."))
        self.assertIn("AppRegInfo", auth.friendly("Invalid app registration"))

    def test_chain_builds_account(self):
        xbl = {"Token": "xbl-token", "DisplayClaims": {"xui": [{"uhs": "uhs-1"}]}}
        xsts = {"Token": "xsts-token", "DisplayClaims": {"xui": [{"uhs": "uhs-1"}]}}
        mc = {"access_token": "mc-token", "expires_in": 86400}
        with mock.patch("mcl.auth._post_json", side_effect=[xbl, xsts, mc]), \
                mock.patch("mcl.auth._profile",
                           return_value={"id": "069a79f444e94726a5befca90e38aaf5", "name": "Notch"}):
            account = auth._chain("ms-access", "refresh-token", "client-id")
        self.assertEqual(account.name, "Notch")
        self.assertEqual(account.uuid, "069a79f4-44e9-4726-a5be-fca90e38aaf5")
        self.assertEqual(account.access_token, "mc-token")
        self.assertEqual(account.refresh_token, "refresh-token")
        self.assertGreater(account.expires_at, time.time())

    def test_login_device_flow(self):
        device = {"device_code": "dev", "user_code": "ABCD-EFGH",
                  "verification_uri": "https://microsoft.com/devicelogin",
                  "interval": 0, "expires_in": 900}
        token = {"access_token": "ms-access", "refresh_token": "refresh"}
        account = auth.Account(name="Notch", uuid="uuid", access_token="mc",
                               refresh_token="refresh", expires_at=time.time() + 3600)
        codes = []
        with mock.patch("mcl.auth._post_form", side_effect=[device, token]), \
                mock.patch("mcl.auth.time.sleep"), \
                mock.patch("mcl.auth._chain", return_value=account), \
                mock.patch("mcl.auth.save_account") as save:
            result = auth.login("client-id", on_code=codes.append)
        self.assertEqual(result.name, "Notch")
        self.assertEqual(codes[0]["user_code"], "ABCD-EFGH")
        save.assert_called_once()

    def test_account_cache(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "accounts.json"
            account = auth.Account(name="Notch", uuid="uuid", access_token="mc",
                                   refresh_token="refresh", expires_at=time.time() + 3600,
                                   client_id="cid")
            with mock.patch("mcl.auth.accounts_path", return_value=path):
                auth.save_account(account)
                loaded = auth.load_account()
                self.assertEqual(loaded.name, "Notch")
                self.assertEqual(loaded.client_id, "cid")
                auth.clear_account()
                self.assertIsNone(auth.load_account())

    def test_ensure_account_returns_none_without_cache(self):
        with mock.patch("mcl.auth.load_account", return_value=None):
            self.assertIsNone(auth.ensure_account(mock.Mock(ms_client_id="")))
