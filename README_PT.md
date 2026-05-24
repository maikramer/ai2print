# ai2print

Aplicação GTK4 para reparar malhas STL/3MF antes da impressão 3D. O pipeline de reparo corre em Python ([PyMeshLab](https://pymeshlab.readthedocs.io/), [Trimesh](https://trimesh.org/)); a interface é Rust/GTK4.

**English:** [README.md](README.md)

## Funcionalidades

- Arrastar-e-soltar ou seletor de ficheiros (STL, OBJ, PLY, OFF, GLB, GLTF, 3MF)
- Modo **Print** — malha fechada e manifold optimizada para fatiadores FDM
- Modo **Gentle** — limpeza mais suave, com menos alterações topológicas
- Log em tempo real na GUI
- Conversão GLB opcional via Blender (`STL_REPAIR_BLENDER`)

## Instalação (recomendado)

```bash
git clone https://github.com/maikramer/ai2print.git
cd ai2print
./install.sh
```

Instala o [Clified](https://pypi.org/project/clified/) via PyPI se necessário, compila o binário Rust, cria `.venv` com dependências Python e regista `ai2print` em `~/.local/bin`.

Alias legado: `stl-repair-gui`.

Windows:

```powershell
.\install.ps1
```

## Uso

```bash
ai2print
# ou, no repo clonado (dev):
./run.sh
```

## Pré-requisitos

| Componente | Notas |
|------------|-------|
| Python 3.10+ com **pip** | Debian/Ubuntu: `python3-full` |
| Rust (`cargo`) | [rustup.rs](https://rustup.rs) |
| GTK4 dev | Linux: `libgtk-4-dev`, `libglib2.0-dev`, … |
| Clified **≥ 0.4.1** | Instalado automaticamente pelo `install.sh` |
| Blender (opcional) | Defina `STL_REPAIR_BLENDER` para fluxos GLB |

O `install.sh` detecta um Python com pip funcional (ignora venvs sem pip no PATH) e trata PEP 668 (`--break-system-packages` quando necessário).

## Variáveis de ambiente

| Variável | Função |
|----------|--------|
| `STL_REPAIR_ROOT` | Raiz do projecto (definida pelo wrapper Clified) |
| `STL_REPAIR_PYTHON` | Interpretador Python do script de reparo (`.venv`) |
| `STL_REPAIR_BLENDER` | Caminho do Blender (opcional) |
| `PYTHON_CMD` | Override do Python na instalação |
| `CLIFIED_TOOLS` | Override do caminho para `tools.yaml` |

## Resolução de problemas

| Problema | Solução |
|----------|---------|
| `No module named pip` | `PYTHON_CMD=/usr/bin/python3.12 ./install.sh` ou instale `python3-full` |
| `externally-managed-environment` | Automático no `install.sh`; ou `pipx install clified` |
| GUI abre mas reparo falha | Reinstale: `./install.sh --action reinstall` |
| Binário em falta no dev | `cargo build --release` e `./run.sh` |

## Desenvolvimento

```bash
cargo build --release
python3 -m venv .venv
.venv/bin/pip install -r python/requirements.txt
./run.sh
```

Reinstalar após mudanças em hooks ou `tools.yaml`:

```bash
./install.sh --action reinstall
```

Hook Python para o Clified: [`clified_install.py`](clified_install.py) (`post_install` — venv + wrapper com variáveis de ambiente).

## Licença

MIT — ver [LICENSE](LICENSE).
