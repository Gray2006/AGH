"""自我改写代码的安全底座：不可变制品 + 原子切换 + 门禁 + 回滚。

「新代码跑通就删旧代码」这个思路方向对，但「跑通」不能证明没有 bug，
删掉旧代码就把唯一的退路也交出去了。这里改成：

1. **永不删除**：每个版本打成 tar.gz，算 manifest 与整包 sha256，可选签名；
2. **原子切换**：只有指针文件（current.json）决定跑哪个版本，切换是 tmp + replace；
3. **门禁**：候选版本在临时目录解开，跑完所有 gate 才允许切换；任一失败自动回滚；
4. **回滚**：指针回到上一版，旧版本一直都在；
5. **回收**：显式 gc，默认只清「超过保留期且不在最近 N 个里」的制品。

注意边界：这套东西假设**监督者在被改代码之外**。如果新代码能改指针、
改 gate 或改监督者本身，所有门禁都是装饰。真正的自改系统需要独立进程/权限。
"""

from __future__ import annotations

import hashlib
import json
import os
import tarfile
import tempfile
import time
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Protocol

MANIFEST = "manifest.json"
POINTER = "current.json"
HISTORY = "history.json"


class SelfModError(Exception):
    pass


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def build_manifest(root: Path) -> dict[str, str]:
    manifest: dict[str, str] = {}
    for path in sorted(root.rglob("*")):
        if path.is_file():
            manifest[str(path.relative_to(root)).replace("\\", "/")] = sha256_file(path)
    return manifest


@dataclass
class Artifact:
    version: str
    archive: Path
    sha256: str
    created_ms: int
    manifest: dict[str, str] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        return {
            "version": self.version,
            "archive": str(self.archive),
            "sha256": self.sha256,
            "created_ms": self.created_ms,
            "files": len(self.manifest),
        }


class ArtifactStore:
    def __init__(self, root: str | Path, clock: Callable[[], int] | None = None) -> None:
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)
        self._clock = clock or (lambda: int(time.time() * 1000))

    # ---------------------------------------------------------------- 制品
    def stage(self, source: str | Path, version: str) -> Artifact:
        src = Path(source)
        if not src.is_dir():
            raise SelfModError(f"源目录不存在: {src}")
        archive = self.root / f"{version}.tar.gz"
        with tarfile.open(archive, "w:gz") as tar:
            tar.add(src, arcname=".")
        artifact = Artifact(
            version=version,
            archive=archive,
            sha256=sha256_file(archive),
            created_ms=self._clock(),
            manifest=build_manifest(src),
        )
        (self.root / f"{version}.json").write_text(
            json.dumps(artifact.as_dict() | {"manifest": artifact.manifest}, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        return artifact

    def load(self, version: str) -> Artifact:
        meta = self.root / f"{version}.json"
        if not meta.exists():
            raise SelfModError(f"未知版本: {version}")
        data = json.loads(meta.read_text(encoding="utf-8"))
        return Artifact(
            version=data["version"],
            archive=Path(data["archive"]),
            sha256=data["sha256"],
            created_ms=data["created_ms"],
            manifest=data.get("manifest", {}),
        )

    def verify(self, artifact: Artifact) -> bool:
        return artifact.archive.exists() and sha256_file(artifact.archive) == artifact.sha256

    def extract(self, artifact: Artifact, target: str | Path | None = None) -> Path:
        if not self.verify(artifact):
            raise SelfModError(f"制品校验失败: {artifact.version}")
        target = Path(target) if target else Path(tempfile.mkdtemp(prefix=f"agh-{artifact.version}-"))
        target.mkdir(parents=True, exist_ok=True)
        with tarfile.open(artifact.archive, "r:gz") as tar:
            tar.extractall(target, filter="data")
        return target

    # ---------------------------------------------------------------- 指针
    def _read_pointer(self) -> dict[str, Any]:
        path = self.root / POINTER
        if not path.exists():
            return {"current": None, "history": []}
        return json.loads(path.read_text(encoding="utf-8"))

    def _write_pointer(self, data: dict[str, Any]) -> None:
        path = self.root / POINTER
        tmp = path.with_suffix(".tmp")
        tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        os.replace(tmp, path)

    def current(self) -> Artifact | None:
        version = self._read_pointer().get("current")
        return self.load(version) if version else None

    def activate(self, version: str) -> Artifact:
        artifact = self.load(version)
        if not self.verify(artifact):
            raise SelfModError(f"制品校验失败，拒绝切换: {version}")
        pointer = self._read_pointer()
        current = pointer.get("current")
        if current == version:
            return artifact
        history = pointer.get("history", [])
        if current:
            history.append(current)
        self._write_pointer({"current": version, "history": history})
        return artifact

    def rollback(self) -> Artifact | None:
        pointer = self._read_pointer()
        history = pointer.get("history", [])
        if not history:
            return None
        previous = history.pop()
        self._write_pointer({"current": previous, "history": history})
        return self.load(previous)

    def gc(self, *, keep_last: int = 5, min_age_days: int = 30, now_ms: int | None = None) -> list[str]:
        """只清超过保留期、且不在最近 keep_last 里的制品；当前版本永不删。"""
        now = now_ms if now_ms is not None else self._clock()
        versions = sorted(
            (self.load(p.stem) for p in self.root.glob("*.json") if p.stem not in {POINTER[:-5], HISTORY[:-5]}),
            key=lambda a: a.created_ms,
            reverse=True,
        )
        current = self._read_pointer().get("current")
        removed: list[str] = []
        for index, artifact in enumerate(versions):
            if index < keep_last or artifact.version == current:
                continue
            age_days = (now - artifact.created_ms) / 86_400_000
            if age_days < min_age_days:
                continue
            artifact.archive.unlink(missing_ok=True)
            (self.root / f"{artifact.version}.json").unlink(missing_ok=True)
            removed.append(artifact.version)
        return removed


class Gate(Protocol):
    name: str

    def check(self, workdir: Path) -> tuple[bool, str]: ...


@dataclass
class GateResult:
    name: str
    passed: bool
    detail: str = ""


@dataclass
class PromoteResult:
    ok: bool
    version: str
    gates: list[GateResult]
    activated: bool = False


def promote(
    store: ArtifactStore,
    version: str,
    gates: Sequence[Gate],
    *,
    keep_workdir: str | Path | None = None,
) -> PromoteResult:
    """在临时目录解开候选版本，跑完所有 gate 才切换指针；失败不动现网。"""
    artifact = store.load(version)
    workdir = store.extract(artifact, keep_workdir)
    results: list[GateResult] = []
    for gate in gates:
        try:
            passed, detail = gate.check(workdir)
        except Exception as exc:  # gate 自己崩了按失败处理
            passed, detail = False, f"gate 异常: {exc}"
        results.append(GateResult(gate.name, passed, detail))
        if not passed:
            break
    ok = all(r.passed for r in results) and len(results) == len(gates)
    if ok:
        store.activate(version)
    return PromoteResult(ok=ok, version=version, gates=results, activated=ok)


class CallableGate:
    """把任意 (workdir) -> bool 的函数包成 gate。"""

    def __init__(self, name: str, fn: Callable[[Path], bool | tuple[bool, str]]) -> None:
        self.name = name
        self._fn = fn

    def check(self, workdir: Path) -> tuple[bool, str]:
        result = self._fn(workdir)
        if isinstance(result, tuple):
            return result
        return bool(result), ""


class CommandGate:
    """跑一条命令，退出码为 0 即通过（默认不联网、超时 120s）。"""

    def __init__(self, name: str, command: Sequence[str], timeout: int = 120) -> None:
        self.name = name
        self.command = list(command)
        self.timeout = timeout

    def check(self, workdir: Path) -> tuple[bool, str]:
        import subprocess

        try:
            proc = subprocess.run(
                self.command,
                cwd=workdir,
                capture_output=True,
                text=True,
                timeout=self.timeout,
            )
        except subprocess.TimeoutExpired:
            return False, "超时"
        detail = (proc.stdout + proc.stderr)[-800:]
        return proc.returncode == 0, detail


__all__ = [
    "Artifact",
    "ArtifactStore",
    "CallableGate",
    "CommandGate",
    "Gate",
    "GateResult",
    "PromoteResult",
    "SelfModError",
    "build_manifest",
    "promote",
    "sha256_file",
]
