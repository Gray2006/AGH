"""事件日志的外部锚定。

本地哈希链能发现「悄悄改一行」，但发现不了「整条链被替换」：
删掉 events.jsonl 重写一条自洽的新链，链本身校验完全通过。
锚定的做法是把链头与长度写到日志之外，并（可选）签名：

- 只写锚点、不签名：能防「日志被改」，防不了「锚点和日志一起被改」
- 用 Ed25519 签锚点：没有私钥的人改不了锚点，也就无法替换整条链
- 两者都不做等于没锚定：`check_log` 会在返回值里明确标出来

真正的外部锚定（第三方时间戳、另一台机器）由调用方把 AnchorStore 换掉即可；
这里只内置本地 JSONL 存储，不假装它是第三方。
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from .crypto import Key, KeyRing, ProvenanceError, sha256_hex, sign_with, verify_with
from .eventlog import EventLog

ANCHOR_VERSION = 1
DEFAULT_KID = "gw-dev"


@dataclass(frozen=True)
class Anchor:
    head: str
    size: int
    log_path: str = ""
    label: str = ""
    created_at: str = ""
    signer: str = ""
    signature: str = ""
    version: int = ANCHOR_VERSION

    def as_dict(self) -> dict[str, Any]:
        return {
            "version": self.version,
            "head": self.head,
            "size": self.size,
            "log_path": self.log_path,
            "label": self.label,
            "created_at": self.created_at,
            "signer": self.signer,
            "signature": self.signature,
        }

    def message(self) -> str:
        """签名覆盖的字段；不含 signature 自身。"""
        return sha256_hex(
            {
                "version": self.version,
                "head": self.head,
                "size": self.size,
                "log_path": self.log_path,
                "label": self.label,
                "created_at": self.created_at,
                "signer": self.signer,
            }
        )


def _resolved(path: str | Path | None) -> str:
    return str(Path(path).resolve()) if path is not None else ""


def anchor_log(
    log: EventLog,
    *,
    key: Key | None = None,
    label: str = "",
    log_path: str | None = None,
    clock: Any = None,
) -> Anchor:
    """把日志当前的链头与长度固化成锚点。"""
    created_at = clock().isoformat() if clock is not None else datetime.now(UTC).isoformat()
    anchor = Anchor(
        head=log.head(),
        size=log.size(),
        log_path=log_path if log_path is not None else _resolved(log.path),
        label=label,
        created_at=created_at,
        signer=key.kid if key is not None else "",
    )
    if key is not None:
        anchor = Anchor(
            head=anchor.head,
            size=anchor.size,
            log_path=anchor.log_path,
            label=anchor.label,
            created_at=anchor.created_at,
            signer=anchor.signer,
            signature=sign_with(key, anchor.message()),
        )
    return anchor


def verify_anchor(anchor: Anchor, keyring: KeyRing | None, *, kid: str | None = None) -> bool:
    """校验锚点签名。未签名的锚点返回 False（调用方据此降级为「未锚定」）。"""
    if not anchor.signature:
        return False
    if keyring is None:
        return False
    try:
        key = keyring.get(kid or anchor.signer or DEFAULT_KID)
    except ProvenanceError:
        return False
    return verify_with(key, anchor.message(), anchor.signature)


def check_log(
    log: EventLog,
    anchor: Anchor,
    *,
    keyring: KeyRing | None = None,
) -> bool:
    """校验日志是否仍是锚定时的样子；返回签名是否可信。

    - 链头/长度不符 → 抛 LogTampered（日志被改或被截断）
    - 签名不符 → 抛 LogTampered（锚点被改，或签名密钥不对）
    - 未签名锚点 → 返回 False，表示「顺序与完整性可信，但未锚定」
    """
    fresh = EventLog(Path(log.path)) if log.path is not None else log
    fresh.verify_against(anchor.head, anchor.size)
    if not anchor.signature:
        return False
    if not verify_anchor(anchor, keyring):
        from .eventlog import LogTampered

        raise LogTampered("锚点签名校验失败（锚点被替换，或密钥不对）")
    return True


class AnchorStore:
    """锚点存储：一行一个 JSON。换掉它就能换外部位置，接口不变。"""

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)

    def append(self, anchor: Anchor) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("a", encoding="utf-8", newline="\n") as fh:
            fh.write(json.dumps(anchor.as_dict(), ensure_ascii=False, sort_keys=True) + "\n")

    def read(self) -> list[Anchor]:
        if not self.path.exists():
            return []
        out: list[Anchor] = []
        for line in self.path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            data = json.loads(line)
            out.append(
                Anchor(
                    head=data["head"],
                    size=int(data["size"]),
                    log_path=data.get("log_path", ""),
                    label=data.get("label", ""),
                    created_at=data.get("created_at", ""),
                    signer=data.get("signer", ""),
                    signature=data.get("signature", ""),
                    version=int(data.get("version", ANCHOR_VERSION)),
                )
            )
        return out

    def latest(self, log_path: str | None = None) -> Anchor | None:
        target = _resolved(log_path)
        candidates = [a for a in self.read() if log_path is None or _resolved(a.log_path) == target]
        return candidates[-1] if candidates else None

    def check(self, log: EventLog, *, keyring: KeyRing | None = None) -> bool:
        anchor = self.latest(str(log.path))
        if anchor is None:
            from .eventlog import LogTampered

            raise LogTampered(f"没有针对 {log.path} 的锚点")
        return check_log(log, anchor, keyring=keyring)


def digest_of(anchor: Anchor) -> str:
    """锚点自身的摘要，方便把它写进别处（issue tracker、另一份日志）。"""
    return sha256_hex(anchor.as_dict())


__all__ = [
    "ANCHOR_VERSION",
    "Anchor",
    "AnchorStore",
    "anchor_log",
    "check_log",
    "digest_of",
    "verify_anchor",
]
