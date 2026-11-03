"""Build dist/veil-install.sh: server/install.sh with server/veil, server/decoy and
server/systemd appended as a base64 tarball, so one file installs everything.

    python tools/build.py
"""
from __future__ import annotations

import base64
import hashlib
import io
import tarfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SERVER = ROOT / "server"
OUT = ROOT / "dist" / "veil-install.sh"
PARTS = ("veil", "decoy", "systemd")
MARKER = "__VEIL_PAYLOAD__"


def _lf(data: bytes) -> bytes:
    return data.replace(b"\r\n", b"\n")


def payload() -> bytes:
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w:gz", compresslevel=9) as tar:
        for part in PARTS:
            for path in sorted((SERVER / part).rglob("*")):
                if not path.is_file() or "__pycache__" in path.parts:
                    continue
                data = _lf(path.read_bytes())
                info = tarfile.TarInfo(path.relative_to(SERVER).as_posix())
                info.size, info.mode, info.mtime = len(data), 0o644, 0
                tar.addfile(info, io.BytesIO(data))
    return buf.getvalue()


def main() -> None:
    for module in sorted((SERVER / "veil").glob("*.py")):
        try:
            compile(module.read_text(encoding="utf-8"), str(module), "exec")
        except SyntaxError as exc:
            raise SystemExit(f"refusing to build: {exc}")
    script = _lf((SERVER / "install.sh").read_bytes()).decode("utf-8")
    if not script.rstrip().endswith("exit $?"):
        raise SystemExit("install.sh must end with `exit $?` so bash never reads the payload")
    encoded = base64.encodebytes(payload()).decode("ascii")
    OUT.parent.mkdir(exist_ok=True)
    OUT.write_bytes(f"{script.rstrip()}\n\n{MARKER}\n{encoded}".encode("utf-8"))
    # `veil update` checks the download against this before running it.
    digest = hashlib.sha256(OUT.read_bytes()).hexdigest()
    OUT.with_name(OUT.name + ".sha256").write_text(f"{digest}  {OUT.name}\n", encoding="ascii")
    print(f"wrote {OUT.relative_to(ROOT)} ({OUT.stat().st_size // 1024} KiB, sha256 {digest[:12]}...)")


if __name__ == "__main__":
    main()
