# ai2print

GTK4 desktop app to repair STL/3MF meshes before 3D printing. The repair pipeline runs in Python ([PyMeshLab](https://pymeshlab.readthedocs.io/), [Trimesh](https://trimesh.org/)); the GUI is Rust/GTK4.

**Português:** [README_PT.md](README_PT.md)

## Features

- Drag-and-drop or file picker for STL, OBJ, PLY, OFF, GLB, GLTF, and 3MF
- **Print** mode — watertight, manifold mesh tuned for FDM slicing
- **Gentle** mode — lighter cleanup with fewer topology changes
- Live log output in the GUI
- Optional Blender-based GLB conversion (`STL_REPAIR_BLENDER`)

## Installation (recommended)

```bash
git clone https://github.com/maikramer/ai2print.git
cd ai2print
./install.sh
```

This installs [Clified](https://pypi.org/project/clified/) from PyPI when needed, builds the Rust binary, creates a Python `.venv`, and registers `ai2print` in `~/.local/bin`.

Legacy alias: `stl-repair-gui`.

Windows:

```powershell
.\install.ps1
```

## Usage

```bash
ai2print
# or, from a cloned repo (dev):
./run.sh
```

## Requirements

| Component | Notes |
|-----------|--------|
| Python 3.10+ with **pip** | Debian/Ubuntu: `python3-full` |
| Rust (`cargo`) | [rustup.rs](https://rustup.rs) |
| GTK4 dev libraries | Linux: `libgtk-4-dev`, `libglib2.0-dev`, … |
| Clified **≥ 0.4.1** | Installed automatically by `install.sh` |
| Blender (optional) | Set `STL_REPAIR_BLENDER` for GLB workflows |

`install.sh` picks a Python with working pip (skips broken venvs on `PATH`) and handles PEP 668 (`--break-system-packages` when required).

## Environment variables

| Variable | Purpose |
|----------|---------|
| `STL_REPAIR_ROOT` | Project root (set automatically by the Clified wrapper) |
| `STL_REPAIR_PYTHON` | Python interpreter for the repair script (`.venv`) |
| `STL_REPAIR_BLENDER` | Path to Blender executable (optional) |
| `PYTHON_CMD` | Override Python used during install |
| `CLIFIED_TOOLS` | Override path to `tools.yaml` |

## Troubleshooting

| Issue | Fix |
|-------|-----|
| `No module named pip` | `PYTHON_CMD=/usr/bin/python3.12 ./install.sh` or install `python3-full` |
| `externally-managed-environment` | Handled by `install.sh`; or `pipx install clified` |
| GUI opens but repair fails | Reinstall: `./install.sh --action reinstall` |
| Binary not found in dev | `cargo build --release` then `./run.sh` |

## Development

```bash
cargo build --release
python3 -m venv .venv
.venv/bin/pip install -r python/requirements.txt
./run.sh
```

Reinstall after changes to hooks or `tools.yaml`:

```bash
./install.sh --action reinstall
```

Python hook for Clified: [`clified_install.py`](clified_install.py) (`post_install` — venv + wrapper with env vars).

## Project layout

```
ai2print/
├── src/main.rs              # GTK4 GUI
├── python/repair_mesh.py    # Repair pipeline
├── clified_install.py       # Clified post_install hook
├── tools.yaml.example       # Clified registry template
├── install.sh / install.ps1 # Clified bootstrap installers
└── scripts/install-bootstrap.sh
```

## License

MIT — see [LICENSE](LICENSE).
