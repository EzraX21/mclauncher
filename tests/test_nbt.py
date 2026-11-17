"""NBT 编解码的单元测试（servers.dat 形状）。"""

import gzip
import unittest

from mcl.nbt import (
    NbtByte,
    NbtError,
    NbtList,
    dumps,
    loads,
)

# 手写的一份 servers.dat：一个 Hypixel 服务器。用来证明字节序、名字长度、
# 列表元素类型这些细节是对的，不是拿自己的写入器来自证。
SERVERS_DAT = (
    b"\x0a\x00\x00"                                    # 根 compound，名字空
    b"\x09\x00\x07servers"                             # TAG_List，名字 servers
    b"\x0a"                                            # 元素类型 compound
    b"\x00\x00\x00\x01"                                # 1 个元素
    # 列表元素只有 payload：没有 tag id、没有名字（NBT 规范）
    b"\x08\x00\x04name\x00\x07Hypixel"                 # name = Hypixel
    b"\x08\x00\x02ip\x00\x0emc.hypixel.net"            # ip = mc.hypixel.net
    b"\x01\x00\x0eacceptTextures\x01"                  # acceptTextures = 1（byte）
    b"\x00"                                            # 元素 compound 结束
    b"\x00"                                            # 根 compound 结束
)

EMPTY_SERVERS_DAT = (
    b"\x0a\x00\x00"
    b"\x09\x00\x07servers"
    b"\x00"                                            # 空列表的元素类型按 0 写
    b"\x00\x00\x00\x00"
    b"\x00"
)


class LoadTests(unittest.TestCase):
    def test_reads_real_shape(self):
        root = loads(SERVERS_DAT)
        servers = root["servers"]
        self.assertEqual(len(servers), 1)
        self.assertEqual(servers[0]["name"], "Hypixel")
        self.assertEqual(servers[0]["ip"], "mc.hypixel.net")

    def test_byte_tag_is_preserved(self):
        """acceptTextures 必须还是 byte，写成 int 的话游戏会读不动。"""
        value = loads(SERVERS_DAT)["servers"][0]["acceptTextures"]
        self.assertIsInstance(value, NbtByte)
        self.assertEqual(value, 1)

    def test_reads_gzip_wrapper(self):
        root = loads(gzip.compress(SERVERS_DAT))
        self.assertEqual(root["servers"][0]["ip"], "mc.hypixel.net")

    def test_empty_list(self):
        root = loads(EMPTY_SERVERS_DAT)
        self.assertEqual(root["servers"], [])

    def test_truncated_raises(self):
        with self.assertRaises(NbtError):
            loads(SERVERS_DAT[:-6])

    def test_empty_input_raises(self):
        with self.assertRaises(NbtError):
            loads(b"")

    def test_non_compound_root_raises(self):
        with self.assertRaises(NbtError):
            loads(b"\x08\x00\x00\x00\x01a")


class DumpTests(unittest.TestCase):
    def test_roundtrip_is_byte_identical(self):
        self.assertEqual(dumps(loads(SERVERS_DAT), compress=False), SERVERS_DAT)

    def test_roundtrip_empty_list(self):
        self.assertEqual(dumps(loads(EMPTY_SERVERS_DAT), compress=False), EMPTY_SERVERS_DAT)

    def test_gzip_by_default(self):
        payload = dumps(loads(SERVERS_DAT))
        self.assertEqual(payload[:2], b"\x1f\x8b")
        self.assertEqual(loads(payload)["servers"][0]["name"], "Hypixel")

    def test_unknown_field_survives(self):
        """认不出的字段也要能原样写回，不能因为不认识就丢掉。"""
        root = loads(SERVERS_DAT)
        root["servers"][0]["hidden"] = NbtByte(1)
        again = loads(dumps(root))
        self.assertEqual(again["servers"][0]["hidden"], 1)
        self.assertIsInstance(again["servers"][0]["hidden"], NbtByte)

    def test_empty_list_keeps_element_tag(self):
        root = {"servers": NbtList([], tag=10)}
        self.assertEqual(loads(dumps(root))["servers"], [])

    def test_bool_is_rejected(self):
        """bool 也是 int，写出去会变成 int 3，必须在写之前拦住。"""
        with self.assertRaises(NbtError):
            dumps({"servers": True})


if __name__ == "__main__":
    unittest.main()
