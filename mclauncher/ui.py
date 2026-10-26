"""终端输出的小工具：颜色、对齐（含中文双宽）、摘要框。"""

from __future__ import annotations

import os
import sys
import unicodedata

RESET = "\033[0m"
STYLES = {
    "bold": "\033[1m",
    "dim": "\033[2m",
    "cyan": "\033[36m",
    "green": "\033[32m",
    "yellow": "\033[33m",
    "red": "\033[31m",
    "blue": "\033[34m",
    "magenta": "\033[35m",
}


def display_width(text: str) -> int:
    total = 0
    for char in text:
        if unicodedata.combining(char):
            continue
        total += 2 if unicodedata.east_asian_width(char) in ("W", "F") else 1
    return total


def pad(text: str, width: int, align: str = "left") -> str:
    gap = max(0, width - display_width(text))
    if align == "right":
        return " " * gap + text
    return text + " " * gap


class UI:
    def __init__(self, color: bool | None = None):
        if color is None:
            color = sys.stdout.isatty() and not os.environ.get("NO_COLOR")
        self.color = bool(color)

    # ------------------------------------------------------------ 基础
    def paint(self, text: str, style: str) -> str:
        if not self.color:
            return text
        return f"{STYLES.get(style, '')}{text}{RESET}"

    def blank(self) -> None:
        print()

    def note(self, text: str) -> None:
        print(self.paint("  " + text, "dim"))

    def info(self, text: str) -> None:
        print("  " + text)

    def ok(self, text: str) -> None:
        print(self.paint("  ✓ ", "green") + text)

    def warn(self, text: str) -> None:
        print(self.paint("  ! ", "yellow") + text)

    def error(self, text: str) -> None:
        print(self.paint("  ✗ ", "red") + text)

    def title(self, text: str) -> None:
        self.blank()
        print(self.paint(f"  {text}", "bold"))

    def kv(self, key: str, value: str, key_width: int = 8) -> None:
        label = pad(key, key_width)
        if display_width(key) >= key_width:
            label += " "
        print(f"  {self.paint(label, 'dim')}{value}")

    # ------------------------------------------------------------ 摘要框
    def box(self, title: str, rows: list[tuple[str, str]]) -> None:
        key_width = max((display_width(k) for k, _ in rows), default=0) + 2
        widths = [display_width(f"{pad(k, key_width)}{v}") for k, v in rows]
        inner = max([display_width(title) + 4] + widths) + 2
        if self.color:
            edge = self.paint("│", "dim")
            corner = self.paint("┌", "dim"), self.paint("┐", "dim")
            bottom = self.paint("└", "dim"), self.paint("┘", "dim")
        else:
            edge, corner, bottom = "│", ("┌", "┐"), ("└", "┘")
        print()
        print("  " + corner[0] + self.paint(f" {title} ", "bold") + "─" * (inner - display_width(title) - 2) + corner[1])
        for key, value in rows:
            content = " " + pad(f"{pad(key, key_width)}{value}", inner - 2) + " "
            print("  " + edge + content + edge)
        print("  " + bottom[0] + "─" * inner + bottom[1])
