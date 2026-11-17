"""最小 NBT 编解码（Minecraft 的 servers.dat 等文件格式）。

只做一件事：把 NBT 读成 Python 结构、再原样写回去。为了让「读进来再写出去」
不损坏原文件，数值类型用 int/float 的子类携带 tag 信息，未知字段也能原样保留。

映射：

| tag | 名字 | Python 类型 |
|---|---|---|
| 1 | Byte | `NbtByte`（int 子类） |
| 2 | Short | `NbtShort`（int 子类） |
| 3 | Int | `int` |
| 4 | Long | `NbtLong`（int 子类） |
| 5 | Float | `NbtFloat`（float 子类） |
| 6 | Double | `float` |
| 7 | ByteArray | `NbtByteArray` |
| 8 | String | `str` |
| 9 | List | `NbtList` |
| 10 | Compound | `dict` |
| 11 | IntArray | `NbtIntArray` |
| 12 | LongArray | `NbtLongArray` |

根节点名统一按 `""` 处理：servers.dat 和绝大多数 Minecraft 文件都是空名字。
"""

from __future__ import annotations

import gzip
import struct
from typing import Any

TAG_END = 0
TAG_BYTE = 1
TAG_SHORT = 2
TAG_INT = 3
TAG_LONG = 4
TAG_FLOAT = 5
TAG_DOUBLE = 6
TAG_BYTE_ARRAY = 7
TAG_STRING = 8
TAG_LIST = 9
TAG_COMPOUND = 10
TAG_INT_ARRAY = 11
TAG_LONG_ARRAY = 12

GZIP_MAGIC = b"\x1f\x8b"


class NbtError(ValueError):
    """NBT 数据坏了，或者结构不是这里支持的形状。"""


class NbtByte(int):
    """TAG_Byte：Minecraft 的布尔值也用它（0/1）。"""


class NbtShort(int):
    """TAG_Short。"""


class NbtLong(int):
    """TAG_Long。"""


class NbtFloat(float):
    """TAG_Float。"""


class NbtByteArray(bytes):
    """TAG_Byte_Array。"""


class NbtIntArray(list):
    """TAG_Int_Array。"""


class NbtLongArray(list):
    """TAG_Long_Array。"""


class NbtList(list):
    """TAG_List：除了元素，还要记住元素类型（空列表必须有类型才写得回去）。"""

    def __init__(self, items: Any = (), tag: int | None = None) -> None:
        super().__init__(items)
        self.tag = tag

    def element_tag(self) -> int:
        if self.tag is not None:
            return self.tag
        return _tag_of(self[0]) if self else TAG_END


def _tag_of(value: Any) -> int:
    """按 Python 类型反查 tag。认不出的类型直接报错，不猜。"""
    if isinstance(value, bool):  # bool 是 int 的子类，必须先判
        raise NbtError("bool 不是 NBT 类型，请用 NbtByte(0/1)")
    if isinstance(value, NbtByte):
        return TAG_BYTE
    if isinstance(value, NbtShort):
        return TAG_SHORT
    if isinstance(value, NbtLong):
        return TAG_LONG
    if isinstance(value, int):
        return TAG_INT
    if isinstance(value, NbtFloat):
        return TAG_FLOAT
    if isinstance(value, float):
        return TAG_DOUBLE
    if isinstance(value, NbtByteArray):
        return TAG_BYTE_ARRAY
    if isinstance(value, NbtIntArray):
        return TAG_INT_ARRAY
    if isinstance(value, NbtLongArray):
        return TAG_LONG_ARRAY
    if isinstance(value, str):
        return TAG_STRING
    if isinstance(value, NbtList):
        return TAG_LIST
    if isinstance(value, dict):
        return TAG_COMPOUND
    if isinstance(value, (list, tuple)):
        return TAG_LIST
    raise NbtError(f"不支持的 NBT 值类型：{type(value).__name__}")


class _Reader:
    def __init__(self, data: bytes) -> None:
        self.data = data
        self.pos = 0

    def take(self, count: int) -> bytes:
        if self.pos + count > len(self.data):
            raise NbtError("NBT 数据提前结束")
        chunk = self.data[self.pos:self.pos + count]
        self.pos += count
        return chunk

    def unpack(self, fmt: str) -> Any:
        size = struct.calcsize(fmt)
        return struct.unpack(fmt, self.take(size))[0]

    def byte(self) -> int:
        return self.unpack(">b")

    def string(self) -> str:
        length = self.unpack(">H")
        try:
            return self.take(length).decode("utf-8")
        except UnicodeDecodeError as exc:
            raise NbtError(f"NBT 字符串不是合法 UTF-8：{exc}") from exc

    def payload(self, tag: int) -> Any:
        if tag == TAG_BYTE:
            return NbtByte(self.byte())
        if tag == TAG_SHORT:
            return NbtShort(self.unpack(">h"))
        if tag == TAG_INT:
            return self.unpack(">i")
        if tag == TAG_LONG:
            return NbtLong(self.unpack(">q"))
        if tag == TAG_FLOAT:
            return NbtFloat(self.unpack(">f"))
        if tag == TAG_DOUBLE:
            return self.unpack(">d")
        if tag == TAG_BYTE_ARRAY:
            return NbtByteArray(self.take(self.unpack(">i")))
        if tag == TAG_STRING:
            return self.string()
        if tag == TAG_LIST:
            element = self.byte()
            count = self.unpack(">i")
            if count < 0:
                raise NbtError("NBT 列表长度是负数")
            return NbtList((self.payload(element) for _ in range(count)), tag=element)
        if tag == TAG_COMPOUND:
            return self.compound()
        if tag == TAG_INT_ARRAY:
            return NbtIntArray(self.unpack(">i") for _ in range(self.unpack(">i")))
        if tag == TAG_LONG_ARRAY:
            return NbtLongArray(self.unpack(">q") for _ in range(self.unpack(">i")))
        raise NbtError(f"不认识的 NBT tag：{tag}")

    def compound(self) -> dict:
        result: dict[str, Any] = {}
        while True:
            tag = self.byte()
            if tag == TAG_END:
                return result
            name = self.string()
            result[name] = self.payload(tag)


class _Writer:
    def __init__(self) -> None:
        self.chunks: list[bytes] = []

    def byte(self, value: int) -> None:
        self.chunks.append(struct.pack(">b", value))

    def string(self, value: str) -> None:
        encoded = value.encode("utf-8")
        if len(encoded) > 0xFFFF:
            raise NbtError("NBT 字符串超过 65535 字节")
        self.chunks.append(struct.pack(">H", len(encoded)) + encoded)

    def payload(self, tag: int, value: Any) -> None:
        if tag == TAG_BYTE:
            self.chunks.append(struct.pack(">b", int(value)))
        elif tag == TAG_SHORT:
            self.chunks.append(struct.pack(">h", int(value)))
        elif tag == TAG_INT:
            self.chunks.append(struct.pack(">i", int(value)))
        elif tag == TAG_LONG:
            self.chunks.append(struct.pack(">q", int(value)))
        elif tag == TAG_FLOAT:
            self.chunks.append(struct.pack(">f", float(value)))
        elif tag == TAG_DOUBLE:
            self.chunks.append(struct.pack(">d", float(value)))
        elif tag == TAG_BYTE_ARRAY:
            raw = bytes(value)
            self.chunks.append(struct.pack(">i", len(raw)) + raw)
        elif tag == TAG_STRING:
            self.string(str(value))
        elif tag == TAG_LIST:
            element = value.element_tag() if isinstance(value, NbtList) else _tag_of(value[0]) if value else TAG_END
            self.byte(element)
            self.chunks.append(struct.pack(">i", len(value)))
            for item in value:
                self.payload(element, item)
        elif tag == TAG_COMPOUND:
            for name, item in value.items():
                item_tag = _tag_of(item)
                self.byte(item_tag)
                self.string(name)
                self.payload(item_tag, item)
            self.byte(TAG_END)
        elif tag == TAG_INT_ARRAY:
            self.chunks.append(struct.pack(">i", len(value)))
            for item in value:
                self.chunks.append(struct.pack(">i", int(item)))
        elif tag == TAG_LONG_ARRAY:
            self.chunks.append(struct.pack(">i", len(value)))
            for item in value:
                self.chunks.append(struct.pack(">q", int(item)))
        else:
            raise NbtError(f"不认识的 NBT tag：{tag}")


def loads(data: bytes) -> dict:
    """解出一份 NBT 根 compound。自动识别 gzip 包装。"""
    if not data:
        raise NbtError("NBT 数据是空的")
    if data[:2] == GZIP_MAGIC:
        try:
            data = gzip.decompress(data)
        except OSError as exc:
            raise NbtError(f"gzip 解压失败：{exc}") from exc
    reader = _Reader(data)
    tag = reader.byte()
    if tag != TAG_COMPOUND:
        raise NbtError(f"NBT 根节点必须是 compound，实际是 tag {tag}")
    reader.string()  # 根节点名，Minecraft 用空字符串
    return reader.compound()


def dumps(root: dict, compress: bool = True) -> bytes:
    """把 compound 写回字节。`compress=True` 时按 gzip 包装（servers.dat 就是这种）。"""
    if not isinstance(root, dict):
        raise NbtError("NBT 根节点必须是 dict")
    writer = _Writer()
    writer.byte(TAG_COMPOUND)
    writer.string("")
    writer.payload(TAG_COMPOUND, root)
    raw = b"".join(writer.chunks)
    return gzip.compress(raw) if compress else raw
