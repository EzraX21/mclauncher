"""检查更新的单元测试（不联网）。"""

import unittest

from mcl import update


class VersionKeyTests(unittest.TestCase):
    def test_plain_and_prefixed(self):
        self.assertEqual(update.version_key("3.14.0"), (3, 14, 0, 3))
        self.assertEqual(update.version_key("v3.14.0"), (3, 14, 0, 3))

    def test_prerelease_sorts_below_final(self):
        final = update.version_key("3.15.0")
        rc = update.version_key("3.15.0-rc.1")
        beta = update.version_key("3.15.0-beta.2")
        self.assertLess(rc, final)
        self.assertLess(beta, rc)

    def test_pep440_style(self):
        self.assertEqual(update.version_key("3.15.0b1"), update.version_key("3.15.0-beta.1"))

    def test_garbage(self):
        for text in ("", "nightly", "v3", "3.14", None):
            self.assertIsNone(update.version_key(text), text)


class IsNewerTests(unittest.TestCase):
    def test_newer(self):
        self.assertTrue(update.is_newer("v3.15.0", "3.14.0"))
        self.assertTrue(update.is_newer("v3.14.1", "3.14.0"))
        self.assertTrue(update.is_newer("v4.0.0", "3.99.99"))

    def test_not_newer(self):
        self.assertFalse(update.is_newer("v3.14.0", "3.14.0"))
        self.assertFalse(update.is_newer("v3.13.9", "3.14.0"))
        self.assertFalse(update.is_newer("v3.15.0-beta.1", "3.15.0"))

    def test_unparsable_is_not_newer(self):
        self.assertFalse(update.is_newer("weird", "3.14.0"))


def fake_payload(tag="v9.9.9", prerelease=False):
    return {
        "tag_name": tag,
        "html_url": "https://github.com/EzraX21/mclauncher/releases/tag/" + tag,
        "published_at": "2026-11-17T10:00:00Z",
        "prerelease": prerelease,
        "assets": [
            {"name": "mcl-9.9.9-windows-x64-setup.exe", "size": 50039466,
             "browser_download_url": "https://example/setup.exe"},
            {"name": "SHA256SUMS.txt", "size": 771, "browser_download_url": "https://example/sums"},
        ],
    }


class CheckTests(unittest.TestCase):
    def test_notes_and_name(self):
        payload = fake_payload("v3.15.0")
        payload["name"] = "MCL 3.15.0"
        payload["body"] = "## What's Changed\n* feat: x"
        data = update.check("3.14.0", fetch=lambda: payload)
        self.assertEqual(data["name"], "MCL 3.15.0")
        self.assertIn("What's Changed", data["notes"])

    def test_notes_truncated(self):
        payload = fake_payload("v3.15.0")
        payload["body"] = "x" * 9000
        data = update.check("3.14.0", fetch=lambda: payload)
        self.assertEqual(len(data["notes"]), 4000)

    def test_update_available(self):
        data = update.check("3.14.0", fetch=lambda: fake_payload("v3.15.0"))
        self.assertTrue(data["update_available"])
        self.assertEqual(data["current"], "3.14.0")
        self.assertEqual(data["latest"], "v3.15.0")
        self.assertEqual([asset["name"] for asset in data["assets"]][0],
                         "mcl-9.9.9-windows-x64-setup.exe")
        self.assertIn("/releases/tag/v3.15.0", data["page"])

    def test_up_to_date(self):
        data = update.check("3.14.0", fetch=lambda: fake_payload("v3.14.0"))
        self.assertFalse(data["update_available"])

    def test_missing_tag_raises(self):
        with self.assertRaises(update.UpdateError):
            update.check("3.14.0", fetch=lambda: {"assets": []})

    def test_network_error_becomes_update_error(self):
        def boom():
            raise update.UpdateError("查不到最新版本：timeout")

        with self.assertRaises(update.UpdateError):
            update.check("3.14.0", fetch=boom)


if __name__ == "__main__":
    unittest.main()
