"""Optional pdflatex compile. Tests must not require TeX."""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path


def compile_latex(source: str, workdir: Path) -> tuple[bool, str]:
    if not source.strip():
        return False, "empty"
    if shutil.which("pdflatex") is None:
        return False, "pdflatex not installed"
    tex = workdir / "draft.tex"
    tex.write_text(source, encoding="utf-8")
    try:
        proc = subprocess.run(
            ["pdflatex", "-interaction=nonstopmode", tex.name],
            cwd=workdir,
            capture_output=True,
            text=True,
            timeout=60,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        return False, str(exc)
    ok = proc.returncode == 0 and (workdir / "draft.pdf").exists()
    return ok, (proc.stderr or proc.stdout)[-2000:]
