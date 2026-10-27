"""本地模组管理的单元测试。"""

import tempfile
import unittest
from pathlib import Path

from mcl.mods import find, list_mods, remove, set_enabled


class ModTests(unittest.TestCase):
    def test_list_toggle_remove(self):
        with tempfile.TemporaryDirectory() as directory:
            mods = Path(directory)
            (mods / "a.jar").write_bytes(b"a")
            (mods / "b.jar.disabled").write_bytes(b"b")
            (mods / "notes.txt").write_text("x", encoding="utf-8")

            items = list_mods(mods)
            self.assertEqual([(item.name, item.enabled) for item in items],
                             [("a.jar", True), ("b.jar", False)])

            destination = set_enabled(items[0], False)
            self.assertTrue(destination.name.endswith(".disabled"))
            self.assertFalse((mods / "a.jar").exists())

            destination = set_enabled(list_mods(mods)[0], True)
            self.assertEqual(destination.name, "a.jar")
            self.assertTrue((mods / "a.jar").exists())

            self.assertEqual([item.name for item in find(mods, "a.")], ["a.jar"])
            remove(find(mods, "a.jar")[0])
            self.assertFalse((mods / "a.jar").exists())


if __name__ == "__main__":
    unittest.main()
