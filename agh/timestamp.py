"""外部可信时间戳。

哈希链只证明「顺序与完整性」，不证明「什么时候写的」。这里把链头交给外部
时间戳机构（TSA）盖章，锚点文件里存 token，事后可验证「这个链头在某个时刻已存在」。

两种后端：
- HmacTimestampAuthority：本地开发用，密钥在本地，只防篡改不防伪造时间；
- HttpTimestampAuthority：把 digest POST 给外部服务，返回 token 与签名，验证走 /verify。
  传输函数可注入，测试不需要网络。

RFC 3161（DER/ASN.1）没有内置实现：需要时把 HttpTimestampAuthority 的 transport
换成调用 TSA 的客户端即可，接口不变。
"""

from __future__ import annotations

import hashlib
import hmac
import json
import time
import urllib.request
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol


class TimestampError(Exception):
    pass


@dataclass(frozen=True)
class TimestampToken:
    digest: str
    issued_at_ms: int
    authority: str
    token: str
    sig: str

    def as_dict(self) -> dict[str, Any]:
        return {
            "digest": self.digest,
            "issued_at_ms": self.issued_at_ms,
            "authority": self.authority,
            "token": self.token,
            "sig": self.sig,
        }


class TimestampAuthority(Protocol):
    name: str

    def stamp(self, digest: str) -> TimestampToken: ...

    def verify(self, token: TimestampToken) -> bool: ...


def _token_message(t: TimestampToken) -> str:
    return "|".join([t.digest, str(t.issued_at_ms), t.authority, t.token])


class HmacTimestampAuthority:
    """本地 TSA：HMAC 盖章。只适合开发与测试。"""

    def __init__(
        self,
        name: str = "local-tsa",
        secret: bytes = b"agh-local-tsa",
        clock: Callable[[], int] | None = None,
    ) -> None:
        self.name = name
        self._secret = secret
        self._clock = clock or (lambda: int(time.time() * 1000))

    def stamp(self, digest: str) -> TimestampToken:
        issued = self._clock()
        token = hashlib.sha256(f"{digest}|{issued}".encode()).hexdigest()
        base = TimestampToken(digest, issued, self.name, token, "")
        sig = hmac.new(self._secret, _token_message(base).encode(), hashlib.sha256).hexdigest()
        return TimestampToken(digest, issued, self.name, token, sig)

    def verify(self, token: TimestampToken) -> bool:
        expected = hmac.new(
            self._secret, _token_message(token).encode(), hashlib.sha256
        ).hexdigest()
        return hmac.compare_digest(expected, token.sig)


Transport = Callable[[str, str, dict[str, Any] | None], dict[str, Any]]


def _urllib_transport(method: str, url: str, payload: dict[str, Any] | None) -> dict[str, Any]:
    data = json.dumps(payload).encode() if payload is not None else None
    req = urllib.request.Request(url, data=data, method=method)
    if data is not None:
        req.add_header("Content-Type", "application/json")
    with urllib.request.urlopen(req, timeout=15) as resp:
        return json.loads(resp.read().decode())


class HttpTimestampAuthority:
    """外部 TSA：POST {digest} 到 url，返回 {token, issued_at_ms, sig}；验证 POST 到 url + '/verify'。"""

    def __init__(
        self,
        url: str,
        name: str = "http-tsa",
        transport: Transport | None = None,
    ) -> None:
        self.name = name
        self.url = url.rstrip("/")
        self._transport = transport or _urllib_transport

    def stamp(self, digest: str) -> TimestampToken:
        data = self._transport("POST", self.url, {"digest": digest})
        try:
            return TimestampToken(
                digest=digest,
                issued_at_ms=int(data["issued_at_ms"]),
                authority=str(data.get("authority", self.name)),
                token=str(data["token"]),
                sig=str(data["sig"]),
            )
        except (KeyError, TypeError, ValueError) as exc:
            raise TimestampError(f"TSA 返回不完整：{exc}") from exc

    def verify(self, token: TimestampToken) -> bool:
        data = self._transport("POST", f"{self.url}/verify", token.as_dict())
        return bool(data.get("valid"))


def anchor_log(
    log_head: str,
    tsa: TimestampAuthority,
    path: str | Path,
) -> TimestampToken:
    """把日志链头交给 TSA 盖章并落盘。"""
    token = tsa.stamp(log_head)
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(token.as_dict(), ensure_ascii=False, indent=2), encoding="utf-8")
    return token


def verify_anchor(path: str | Path, tsa: TimestampAuthority) -> TimestampToken:
    raw = json.loads(Path(path).read_text(encoding="utf-8"))
    token = TimestampToken(**raw)
    if not tsa.verify(token):
        raise TimestampError("时间戳签名无效")
    return token


__all__ = [
    "HmacTimestampAuthority",
    "HttpTimestampAuthority",
    "TimestampAuthority",
    "TimestampError",
    "TimestampToken",
    "anchor_log",
    "verify_anchor",
]
