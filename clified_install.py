"""Hooks Clified para ai2print (Rust + venv Python)."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from clified.installer.rust_installer import RustProjectInstaller
    from clified.logging import Logger


def _get_logger() -> Logger:
    from clified.logging import Logger as ClifiedLogger

    return ClifiedLogger()


def _default_python() -> str:
    return os.environ.get("PYTHON_CMD", "python3" if sys.platform != "win32" else "python")


def _venv_python(root: Path) -> Path:
    if sys.platform == "win32":
        return root / ".venv" / "Scripts" / "python.exe"
    return root / ".venv" / "bin" / "python3"


def _ensure_python_venv(root: Path, python_cmd: str) -> Path:
    venv_dir = root / ".venv"
    venv_py = _venv_python(root)
    if not venv_py.is_file():
        subprocess.run(
            [python_cmd, "-m", "venv", str(venv_dir)],
            check=True,
            cwd=root,
        )
        venv_py = _venv_python(root)
    req = root / "python" / "requirements.txt"
    if req.is_file():
        subprocess.run([str(venv_py), "-m", "pip", "install", "-U", "pip"], check=True)
        subprocess.run(
            [str(venv_py), "-m", "pip", "install", "-r", str(req)],
            check=True,
        )
    return venv_py


def _release_binary(installer: RustProjectInstaller) -> Path:
    src = installer.release_binary
    if src.is_file():
        return src.resolve()
    existing = installer.get_existing_binary()
    if existing is not None:
        return existing.resolve()
    msg = f"Binário Rust não encontrado: {src}"
    raise FileNotFoundError(msg)


def _cmd_wrapper_path(wrapper_path: Path) -> Path:
    if wrapper_path.suffix.lower() == ".cmd":
        return wrapper_path
    return wrapper_path.with_suffix(".cmd")


def _write_wrapper(
    *,
    wrapper_path: Path,
    root: Path,
    venv_py: Path,
    bin_src: Path,
    is_windows: bool,
) -> None:
    wrapper_path.parent.mkdir(parents=True, exist_ok=True)
    if wrapper_path.is_file() or wrapper_path.is_symlink():
        wrapper_path.unlink()

    if is_windows:
        cmd_path = _cmd_wrapper_path(wrapper_path)
        lines = [
            "@echo off",
            "REM ai2print — gerado por clified",
            f'set "STL_REPAIR_ROOT={root}"',
            f'set "STL_REPAIR_PYTHON={venv_py}"',
            f'"{bin_src}" %*',
            "",
        ]
        cmd_path.write_text("\r\n".join(lines), encoding="utf-8", newline="\r\n")
        return

    content = (
        "#!/bin/bash\n"
        "# ai2print — gerado por clified\n"
        f'export STL_REPAIR_ROOT="{root}"\n'
        f'export STL_REPAIR_PYTHON="{venv_py}"\n'
        f'exec "{bin_src}" "$@"\n'
    )
    wrapper_path.write_text(content, encoding="utf-8")
    wrapper_path.chmod(0o755)


def post_install(installer: RustProjectInstaller) -> bool:
    """Prepara venv Python, localiza o binário Rust e gera wrappers CLI."""
    logger = _get_logger()
    root = Path(installer.project_root).resolve()

    logger.step("Configurando venv Python (pymeshlab, trimesh…)…")
    try:
        venv_py = _ensure_python_venv(root, _default_python())
    except (subprocess.CalledProcessError, OSError) as exc:
        logger.error(f"Falha ao preparar venv Python: {exc}")
        return False

    try:
        bin_src = _release_binary(installer)
    except FileNotFoundError as exc:
        logger.error(str(exc))
        return False

    wrapper_path = installer.bin_dir / installer.cli_name
    try:
        _write_wrapper(
            wrapper_path=wrapper_path,
            root=root,
            venv_py=venv_py,
            bin_src=bin_src,
            is_windows=installer.is_windows,
        )
    except OSError as exc:
        logger.error(f"Falha ao criar wrapper: {exc}")
        return False

    for alias in ("stl-repair-gui",):
        if alias == installer.cli_name:
            continue
        alias_path = installer.bin_dir / alias
        try:
            _write_wrapper(
                wrapper_path=alias_path,
                root=root,
                venv_py=venv_py,
                bin_src=bin_src,
                is_windows=installer.is_windows,
            )
        except OSError as exc:
            logger.warning(f"Alias {alias}: {exc}")

    logger.success(f"Wrapper com STL_REPAIR_ROOT={root}")
    return True
