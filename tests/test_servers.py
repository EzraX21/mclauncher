"""服务器列表与 Server List Ping 的测试（本地假服务器，不联网）。"""

import json
import socket
import tempfile
import threading
import unittest
from pathlib import Path

from mcl import nbt, servers
from mcl.config import Config
from mcl.servers import ServerError


def pack_varint(value: int) -> bytes:
    """测试自己的 VarInt 实现：不复用被测代码，避免自证。"""
    out = bytearray()
    while True:
        chunk = value & 0x7F
        value >>= 7
        out.append(chunk | 0x80 if value else chunk)
        if not value:
            return bytes(out)


def pack_string(text: str) -> bytes:
    raw = text.encode("utf-8")
    return pack_varint(len(raw)) + raw


def frame(payload: bytes) -> bytes:
    return pack_varint(len(payload)) + payload


class FakeServer(threading.Thread):
    """一个只会回答状态查询的假 Minecraft 服务器。"""

    def __init__(self, response: dict):
        super().__init__(daemon=True)
        self.response = response
        self.seen_host = None
        self.seen_port = None
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.sock.bind(("127.0.0.1", 0))
        self.sock.listen(1)
        self.sock.settimeout(5)
        self.port = self.sock.getsockname()[1]

    def run(self):
        try:
            conn, _ = self.sock.accept()
        except OSError:
            return
        with conn:
            conn.settimeout(5)
            stream = conn.makefile("rb")
            _read_packet(stream)  # 握手
            _read_packet(stream)  # 状态请求
            body = b"\x00" + pack_string(json.dumps(self.response, ensure_ascii=False))
            conn.sendall(frame(body))

    def close(self):
        self.sock.close()


def _read_varint(stream) -> int:
    result = 0
    shift = 0
    while True:
        chunk = stream.read(1)
        if not chunk:
            raise EOFError
        byte = chunk[0]
        result |= (byte & 0x7F) << shift
        shift += 7
        if not byte & 0x80:
            return result


def _read_packet(stream) -> bytes:
    length = _read_varint(stream)
    return stream.read(length)


class AddressTests(unittest.TestCase):
    def test_split_default_port(self):
        self.assertEqual(servers.split_address("mc.hypixel.net"), ("mc.hypixel.net", 25565))

    def test_split_explicit_port(self):
        self.assertEqual(servers.split_address("play.example.com:25566"), ("play.example.com", 25566))

    def test_split_ipv6_with_port(self):
        self.assertEqual(servers.split_address("[::1]:25570"), ("::1", 25570))

    def test_split_bare_ipv6(self):
        """裸 IPv6 里的冒号不是端口分隔符。"""
        self.assertEqual(servers.split_address("::1"), ("::1", 25565))

    def test_join_omits_default_port(self):
        self.assertEqual(servers.join_address("mc.hypixel.net", 25565), "mc.hypixel.net")
        self.assertEqual(servers.join_address("mc.hypixel.net", 25566), "mc.hypixel.net:25566")
        self.assertEqual(servers.join_address("::1", 25565), "[::1]")

    def test_roundtrip(self):
        for text in ("mc.hypixel.net", "play.example.com:25566", "[::1]:25570"):
            host, port = servers.split_address(text)
            self.assertEqual(servers.join_address(host, port), text)


class PathTests(unittest.TestCase):
    def test_isolated_versions_use_version_dir(self):
        """游戏的工作目录是 versions/<id>/，server.dat 就必须在那儿，否则游戏看不到。"""
        with tempfile.TemporaryDirectory() as directory:
            cfg = Config(game_dir=directory, isolate_versions=True)
            path = servers.servers_path(cfg, "1.20.1")
            self.assertEqual(path, (Path(directory) / "versions" / "1.20.1" / "servers.dat").resolve())

    def test_shared_list_in_game_root(self):
        with tempfile.TemporaryDirectory() as directory:
            cfg = Config(game_dir=directory, isolate_versions=False)
            self.assertEqual(servers.servers_path(cfg, "1.20.1"),
                             (Path(directory) / "servers.dat").resolve())


class ListTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.cfg = Config(game_dir=str(Path(self.tmp.name) / "game"), isolate_versions=False)

    def tearDown(self):
        self.tmp.cleanup()

    def test_missing_file_is_empty(self):
        data = servers.listing(self.cfg, "1.20.1")
        self.assertEqual(data["servers"], [])
        self.assertFalse(Path(data["path"]).exists())

    def test_add_writes_valid_nbt(self):
        servers.add(self.cfg, "1.20.1", "Hypixel", "mc.hypixel.net")
        path = servers.servers_path(self.cfg, "1.20.1")
        root = nbt.loads(path.read_bytes())  # 独立于我们的列表代码再解一次
        self.assertEqual(root["servers"][0]["name"], "Hypixel")
        self.assertEqual(root["servers"][0]["ip"], "mc.hypixel.net")
        self.assertIsInstance(root["servers"][0]["acceptTextures"], nbt.NbtByte)

    def test_add_then_list(self):
        servers.add(self.cfg, "1.20.1", "Hypixel", "mc.hypixel.net:25566")
        data = servers.listing(self.cfg, "1.20.1")
        self.assertEqual(len(data["servers"]), 1)
        item = data["servers"][0]
        self.assertEqual((item["name"], item["host"], item["port"]), ("Hypixel", "mc.hypixel.net", 25566))

    def test_update_keeps_unknown_fields(self):
        """图标之类我们不认识的字段不能被改写冲掉。"""
        servers.add(self.cfg, "1.20.1", "Hypixel", "mc.hypixel.net")
        path = servers.servers_path(self.cfg, "1.20.1")
        root = nbt.loads(path.read_bytes())
        root["servers"][0]["icon"] = nbt.NbtByteArray(b"icon-bytes")
        path.write_bytes(nbt.dumps(root))
        servers.update(self.cfg, "1.20.1", 0, name="改名了")
        again = nbt.loads(path.read_bytes())
        self.assertEqual(again["servers"][0]["name"], "改名了")
        self.assertEqual(bytes(again["servers"][0]["icon"]), b"icon-bytes")

    def test_update_rejects_bad_input(self):
        servers.add(self.cfg, "1.20.1", "Hypixel", "mc.hypixel.net")
        with self.assertRaises(ServerError):
            servers.update(self.cfg, "1.20.1", 0, name="")
        with self.assertRaises(ServerError):
            servers.update(self.cfg, "1.20.1", 0, ip="host:70000")

    def test_remove(self):
        servers.add(self.cfg, "1.20.1", "A", "a.example.com")
        servers.add(self.cfg, "1.20.1", "B", "b.example.com")
        servers.remove(self.cfg, "1.20.1", 0)
        data = servers.listing(self.cfg, "1.20.1")
        self.assertEqual([item["name"] for item in data["servers"]], ["B"])

    def test_remove_out_of_range(self):
        with self.assertRaises(ServerError):
            servers.remove(self.cfg, "1.20.1", 3)

    def test_corrupt_file_is_not_overwritten(self):
        path = servers.servers_path(self.cfg, "1.20.1")
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"not nbt at all")
        with self.assertRaises(ServerError):
            servers.listing(self.cfg, "1.20.1")
        with self.assertRaises(ServerError):
            servers.add(self.cfg, "1.20.1", "X", "x.example.com")
        self.assertEqual(path.read_bytes(), b"not nbt at all")

    def test_add_rejects_empty_name(self):
        with self.assertRaises(ServerError):
            servers.add(self.cfg, "1.20.1", "  ", "mc.hypixel.net")


class PingTests(unittest.TestCase):
    def test_handshake_bytes_are_correct(self):
        """手算的握手包，防止 VarInt 或端口字节序写错。"""
        packet = servers._handshake("localhost", 25565)
        self.assertEqual(packet, b"\x10\x00\xff\x05\x09localhost\x63\xdd\x01")

    def test_status_reads_players_and_motd(self):
        fake = FakeServer({
            "version": {"name": "1.20.1", "protocol": 763},
            "players": {"online": 5, "max": 20},
            "description": {"text": "§a欢迎", "extra": [{"text": " 来玩"}], "translate": "ignored"},
        })
        fake.start()
        try:
            result = servers.status("127.0.0.1", fake.port, timeout=3)
        finally:
            fake.close()
        self.assertTrue(result["online"], result.get("error"))
        self.assertEqual(result["players"], {"online": 5, "max": 20})
        self.assertEqual(result["version"], "1.20.1")
        self.assertEqual(result["motd"], "欢迎 来玩")
        self.assertIsNotNone(result["latency_ms"])

    def test_status_accepts_plain_string_motd(self):
        fake = FakeServer({"description": "老版本字符串", "players": {"online": 0, "max": 0}})
        fake.start()
        try:
            result = servers.status("127.0.0.1", fake.port, timeout=3)
        finally:
            fake.close()
        self.assertEqual(result["motd"], "老版本字符串")

    def test_unreachable_is_not_an_exception(self):
        probe = socket.socket()
        probe.bind(("127.0.0.1", 0))
        port = probe.getsockname()[1]
        probe.close()
        result = servers.status("127.0.0.1", port, timeout=0.4)
        self.assertFalse(result["online"])
        self.assertTrue(result["error"])

    def test_ping_servers_keeps_order(self):
        fake = FakeServer({"description": "ok"})
        fake.start()
        try:
            items = [
                {"host": "127.0.0.1", "port": fake.port},
                {"host": "127.0.0.1", "port": 1},  # 必然连不上
            ]
            results = servers.ping_servers(items, timeout=1.0)
        finally:
            fake.close()
        self.assertEqual(len(results), 2)
        self.assertTrue(results[0]["online"])
        self.assertFalse(results[1]["online"])


class FlattenTests(unittest.TestCase):
    def test_strips_color_codes(self):
        self.assertEqual(servers.flatten_chat("§aA §lB"), "A B")

    def test_nested_extra(self):
        self.assertEqual(
            servers.flatten_chat({"text": "x", "extra": [{"text": "y", "extra": [{"text": "z"}]}]}),
            "xyz")

    def test_unknown_shape_is_empty(self):
        self.assertEqual(servers.flatten_chat(None), "")
        self.assertEqual(servers.flatten_chat(42), "")


if __name__ == "__main__":
    unittest.main()
