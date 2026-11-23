"""冻结层锚点（D2）。

原规格的 judge_hash 写在被哈希的 frozen_judge.yaml 里 —— 自引用，改文件同时改哈希，
锚点等于没有。这里：
- 锚点 = 一份覆盖「冻结配置 + phase_gates + thresholds + Go/No-Go 脚本」的 sha256 清单；
- 清单本身存在冻结目录之外，并由网关密钥签名；
- 清单若被放进冻结目录，直接报错（不允许自引用）。
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

from .crypto import KeyRing, _sign, canonical_bytes


class FrozenLayerError(Exception):
    pass


class SelfReferenceError(FrozenLayerError):
    pass


class FrozenLayerTampered(FrozenLayerError):
    def __init__(self, diffs: dict[str, str]) -> None:
        super().__init__(f"冻结层被改动: {diffs}")
        self.diffs = diffs


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _collect(root: Path, include: Iterable[str]) -> list[Path]:
    files: list[Path] = []
    for pattern in include:
        files.extend(sorted(root.glob(pattern)))
    return [p for p in files if p.is_file()]


@dataclass
class Anchor:
    """签名锚点，存放在冻结目录之外。"""

    manifest: dict[str, str]
    manifest_sha256: str
    kid: str
    sig: str

    def verify_with(self, keyring: KeyRing) -> None:
        expected = _sign(keyring.get(self.kid).secret, self.manifest_sha256)
        if expected != self.sig:
            raise FrozenLayerError("锚点签名无效")
        if hashlib.sha256(canonical_bytes(self.manifest)).hexdigest() != self.manifest_sha256:
            raise FrozenLayerError("清单哈希与锚点不一致")


class FrozenLayer:
    """覆盖范围由 include 决定：配置 + 脚本，全部在锚点内。"""

    def __init__(
        self,
        root: Path,
        include: tuple[str, ...] = ("*.json", "scripts/*.py"),
    ) -> None:
        self.root = Path(root).resolve()
        self.include = include

    def files(self) -> list[Path]:
        return _collect(self.root, self.include)

    def manifest(self) -> dict[str, str]:
        return {
            str(p.relative_to(self.root)).replace("\\", "/"): sha256_file(p)
            for p in self.files()
        }

    def _assert_outside(self, path: Path) -> None:
        resolved = Path(path).resolve()
        if resolved == self.root or self.root in resolved.parents:
            raise SelfReferenceError(f"锚点不能放在冻结目录内: {resolved}")

    def write_anchor(self, path: Path, keyring: KeyRing, kid: str) -> Anchor:
        self._assert_outside(path)
        manifest = self.manifest()
        manifest_hash = hashlib.sha256(canonical_bytes(manifest)).hexdigest()
        anchor = Anchor(
            manifest=manifest,
            manifest_sha256=manifest_hash,
            kid=kid,
            sig=_sign(keyring.get(kid).secret, manifest_hash),
        )
        path.write_text(
            json.dumps(anchor.__dict__, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        return anchor

    def load_anchor(self, path: Path) -> Anchor:
        raw = json.loads(Path(path).read_text(encoding="utf-8"))
        return Anchor(**raw)

    def verify(self, path: Path, keyring: KeyRing) -> Anchor:
        anchor = self.load_anchor(path)
        anchor.verify_with(keyring)
        current = self.manifest()
        diffs: dict[str, str] = {}
        for name, digest in anchor.manifest.items():
            if name not in current:
                diffs[name] = "missing"
            elif current[name] != digest:
                diffs[name] = "changed"
        for name in current:
            if name not in anchor.manifest:
                diffs[name] = "unexpected"
        if diffs:
            raise FrozenLayerTampered(diffs)
        return anchor

    def guard_write(self, path: Path) -> None:
        """一切修改都要过这里：冻结层相关改动一律拒绝（D10）。"""
        resolved = Path(path).resolve()
        if self.root in resolved.parents or resolved == self.root:
            raise FrozenLayerError(f"拒绝修改冻结层文件: {resolved}")


def load_json(root: Path, name: str) -> dict:
    return json.loads((Path(root) / name).read_text(encoding="utf-8"))
