from __future__ import annotations

import hashlib
import re
import secrets
from dataclasses import dataclass
from datetime import datetime
from urllib.parse import parse_qsl, urlsplit, urlunsplit, urlencode


MAX_CHARS = 100_000
_TRACKING = {"fbclid", "gclid", "igshid", "spm", "scm", "mc_cid", "mc_eid"}
_URL_IN_TEXT = re.compile(r"https?://[^\s<>\"']+", re.IGNORECASE)
_TAG_SPLIT = re.compile(r"[\s,，、;；]+")
_HOTKEY_NAMES = {
    "ctrl": "Ctrl",
    "control": "Ctrl",
    "alt": "Alt",
    "alt_l": "Alt",
    "alt_r": "Alt",
    "shift": "Shift",
    "cmd": "Cmd",
    "command": "Cmd",
    "super": "Win",
    "space": "Space",
    "enter": "Enter",
    "tab": "Tab",
    "esc": "Esc",
    "escape": "Esc",
}


class CaptureError(Exception):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


@dataclass
class Entry:
    id: str
    time: str
    tags: list[str]
    url: str
    text: str
    dedup: str


def parse_tags(raw: str) -> list[str]:
    tags: list[str] = []
    seen: set[str] = set()
    for part in _TAG_SPLIT.split(raw.strip()):
        tag = part.strip().lstrip("#＃").strip()
        if not tag or tag in seen:
            continue
        tags.append(tag[:40])
        seen.add(tag[:40])
        if len(tags) >= 20:
            break
    return tags


def hotkey_label(spec: str) -> str:
    labels: list[str] = []
    for part in spec.split("+"):
        key = part.strip().strip("<>").strip()
        if not key:
            continue
        mapped = _HOTKEY_NAMES.get(key.lower())
        if mapped:
            labels.append(mapped)
        elif len(key) == 1:
            labels.append(key.upper())
        else:
            labels.append(key[:1].upper() + key[1:])
    return "+".join(labels) or spec


def is_pure_url(text: str) -> bool:
    candidate = text.strip()
    if not candidate or any(char in candidate for char in "\n\r\t "):
        return False
    lowered = candidate.lower()
    return lowered.startswith("http://") or lowered.startswith("https://")


def clean_url(text: str) -> str:
    return text.strip().rstrip(".,);，。；、）]>\"'")


def extract_first_url(text: str) -> str:
    match = _URL_IN_TEXT.search(text)
    if not match:
        return ""
    return clean_url(match.group(0))


def normalize_url(url: str) -> str:
    parts = urlsplit(clean_url(url))
    host = (parts.hostname or "").lower()
    try:
        host = host.encode("idna").decode("ascii")
    except UnicodeError:
        pass
    if parts.port and not (
        (parts.scheme == "http" and parts.port == 80)
        or (parts.scheme == "https" and parts.port == 443)
    ):
        host = f"{host}:{parts.port}"
    path = parts.path or "/"
    if path != "/":
        path = path.rstrip("/")
    query_pairs = [
        (key, value)
        for key, value in parse_qsl(parts.query, keep_blank_values=True)
        if key.lower() not in _TRACKING and not key.lower().startswith("utm_")
    ]
    return urlunsplit((parts.scheme.lower(), host, path, urlencode(query_pairs), ""))


def normalize_text(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def compute_dedup(url: str, text: str) -> str:
    if is_pure_url(text) or (url and not text.strip()):
        basis = "u:" + normalize_url(url or text)
    else:
        basis = "t:" + normalize_text(text)
    return hashlib.sha256(basis.encode("utf-8")).hexdigest()[:20]


def union_tags(old: list[str], new: list[str]) -> list[str]:
    merged = list(old)
    seen = set(old)
    for tag in new:
        if tag not in seen:
            seen.add(tag)
            merged.append(tag)
    return merged


def build_entry(
    text: str,
    tags: list[str],
    *,
    now: datetime | None = None,
    entry_id: str | None = None,
) -> Entry | None:
    raw = text.replace("\r\n", "\n").replace("\r", "\n").strip()
    if not raw:
        return None
    if len(raw) > MAX_CHARS:
        raise CaptureError("too_long", "这段内容超过 10 万字，没有收录。请只复制需要的部分。")
    moment = now or datetime.now()
    if is_pure_url(raw):
        url = clean_url(raw)
        body = ""
    else:
        url = extract_first_url(raw)
        body = raw
    return Entry(
        id=entry_id or secrets.token_hex(8),
        time=moment.strftime("%Y-%m-%d %H:%M:%S"),
        tags=list(tags),
        url=url,
        text=body,
        dedup=compute_dedup(url, body),
    )


def classify_clipboard(text: str, has_image: bool) -> tuple[str, str]:
    if text and text.strip():
        return "text", text
    if has_image:
        return "image", ""
    return "empty", ""
