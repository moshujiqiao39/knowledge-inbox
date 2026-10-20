from __future__ import annotations

import re
import threading
from pathlib import Path

from inbox.logic import CaptureError, Entry, build_entry, compute_dedup, parse_tags, union_tags


HEADER = """# 知识收件箱

这个文件由知识收件箱程序自动追加。可以改「标签」和正文。
请保留每条笔记开头和结尾的 `<!-- kb ... -->` 标记，搜索页靠它们认出一条笔记。

"""

_START = re.compile(r"^<!-- kb id=([0-9a-f]{8,32}) dedup=([0-9a-f]{8,64}) -->$")
_END = re.compile(r"^<!-- /kb id=([0-9a-f]{8,32}) -->$")
_TAG_LINE = re.compile(r"^标签\s*[:：]\s*(.*)$")
_URL_LINE = re.compile(r"^链接\s*[:：]\s*(.*)$")


def render_entry(entry: Entry) -> str:
    tags = " ".join(f"#{tag}" for tag in entry.tags)
    end = f"<!-- /kb id={entry.id} -->"
    body = entry.text.replace(end, "")
    lines = [
        f"<!-- kb id={entry.id} dedup={entry.dedup} -->",
        f"## {entry.time}",
        f"标签：{tags}",
        f"链接：{entry.url}",
        "",
        body,
        end,
        "",
    ]
    return "\n".join(lines)


class Store:
    def __init__(self, path: Path) -> None:
        self.path = path
        self._lock = threading.RLock()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        if not self.path.exists():
            self.path.write_text(HEADER, encoding="utf-8", newline="\n")

    def add(self, entry: Entry) -> str:
        """返回 saved、duplicate 或 updated。"""
        with self._lock:
            text = self._read()
            for found, start, end in self._locate(text):
                keys = {found.dedup, compute_dedup(found.url, found.text)}
                incoming = {entry.dedup, compute_dedup(entry.url, entry.text)}
                if keys.isdisjoint(incoming):
                    continue
                merged = union_tags(found.tags, entry.tags)
                if merged == found.tags:
                    return "duplicate"
                self._replace_tags(text, start, end, merged)
                return "updated"
            self._append(entry)
            return "saved"

    def list_entries(self) -> list[Entry]:
        with self._lock:
            entries = [item for item, _start, _end in self._locate(self._read())]
        entries.reverse()
        return entries

    def list_public(self) -> list[dict]:
        return [
            {
                "id": entry.id,
                "time": entry.time,
                "tags": entry.tags,
                "url": entry.url,
                "text": entry.text,
            }
            for entry in self.list_entries()
        ]

    def _read(self) -> str:
        return self.path.read_text(encoding="utf-8")

    def _append(self, entry: Entry) -> None:
        with self.path.open("a", encoding="utf-8", newline="\n") as handle:
            handle.write("\n")
            handle.write(render_entry(entry))

    def _replace_tags(self, text: str, start: int, end: int, tags: list[str]) -> None:
        lines = text.splitlines()
        tag_line = "标签：" + " ".join(f"#{tag}" for tag in tags)
        for index in range(start, min(end + 1, len(lines))):
            if _TAG_LINE.match(lines[index].strip()):
                lines[index] = tag_line
                break
        else:
            insert_at = min(start + 1, len(lines))
            for index in range(start, min(end + 1, len(lines))):
                if lines[index].startswith("##"):
                    insert_at = index + 1
                    break
            lines.insert(insert_at, tag_line)
        self.path.write_text("\n".join(lines) + "\n", encoding="utf-8", newline="\n")

    def _locate(self, text: str) -> list[tuple[Entry, int, int]]:
        lines = text.splitlines()
        found: list[tuple[Entry, int, int]] = []
        index = 0
        total = len(lines)
        while index < total:
            match = _START.match(lines[index].strip())
            if not match:
                index += 1
                continue
            entry_id, dedup = match.group(1), match.group(2)
            start = index
            index += 1
            body: list[str] = []
            end_index = None
            while index < total:
                end_match = _END.match(lines[index].strip())
                if end_match and end_match.group(1) == entry_id:
                    end_index = index
                    break
                body.append(lines[index])
                index += 1
            if end_index is None:
                break
            found.append((_entry_from_body(body, entry_id, dedup), start, end_index))
            index += 1
        return found


def save_text(store: Store, text: str, tags_raw: str) -> tuple[str, str]:
    try:
        entry = build_entry(text, parse_tags(tags_raw))
    except CaptureError as exc:
        return exc.code, str(exc)
    if entry is None:
        return "empty", "剪贴板是空的。请先复制一段文字或链接。"
    status = store.add(entry)
    messages = {
        "saved": "已保存",
        "duplicate": "这条已经收过，没有重复写入",
        "updated": "这条已经收过，已补上新标签",
    }
    return status, messages[status]


def _entry_from_body(lines: list[str], entry_id: str, dedup: str) -> Entry:
    while lines and not lines[0].strip():
        lines = lines[1:]
    cursor = 0
    time = ""
    tags: list[str] = []
    url = ""
    if cursor < len(lines) and lines[cursor].startswith("##"):
        time = lines[cursor][2:].strip()
        cursor += 1
    if cursor < len(lines):
        tag_match = _TAG_LINE.match(lines[cursor].strip())
        if tag_match:
            tags = parse_tags(tag_match.group(1))
            cursor += 1
    if cursor < len(lines):
        url_match = _URL_LINE.match(lines[cursor].strip())
        if url_match:
            url = url_match.group(1).strip()
            cursor += 1
    if cursor < len(lines) and lines[cursor].strip() == "":
        cursor += 1
    text = "\n".join(lines[cursor:]).strip()
    return Entry(id=entry_id, time=time, tags=tags, url=url, text=text, dedup=dedup)
