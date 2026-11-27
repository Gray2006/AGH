"""删掉 hosts 里的 GitHub 行（迅游加速器启动时会写回去）。

用法：python scripts/fix_hosts.py
"""

from __future__ import annotations

import datetime
import pathlib
import sys

HOSTS = pathlib.Path(r"C:\Windows\System32\drivers\etc\hosts")


def main() -> int:
    raw = HOSTS.read_bytes()
    has_bom = raw.startswith(b"\xef\xbb\xbf")
    text = raw.decode("utf-8-sig")

    kept: list[str] = []
    removed: list[str] = []
    for line in text.splitlines(keepends=True):
        body = line.split("#", 1)[0].strip()
        parts = body.split()
        if len(parts) >= 2 and "github" in parts[-1].lower():
            removed.append(line.rstrip())
        else:
            kept.append(line)

    if not removed:
        print("hosts 里没有 GitHub 行，无需改动")
        return 0

    backup_dir = pathlib.Path(__file__).resolve().parent.parent / "runs" / "hosts-backup"
    backup_dir.mkdir(parents=True, exist_ok=True)
    backup = backup_dir / f"hosts-{datetime.datetime.now():%Y%m%d-%H%M%S}.txt"
    backup.write_bytes(raw)
    print(f"备份：{backup}")

    payload = "".join(kept)
    try:
        HOSTS.write_bytes((b"\xef\xbb\xbf" if has_bom else b"") + payload.encode("utf-8"))
    except PermissionError:
        print("需要管理员权限才能改 hosts")
        return 1

    print(f"删了 {len(removed)} 行 GitHub 条目")
    print("记得清 DNS 缓存：ipconfig /flushdns")
    return 0


if __name__ == "__main__":
    sys.exit(main())
