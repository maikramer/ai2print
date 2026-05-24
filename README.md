# ai2print

GUI GTK4 para reparar malhas STL/3MF antes da impressão 3D. O backend de reparo usa Python (`pymeshlab`, `trimesh`); a interface é Rust/GTK4.

## Instalação (recomendado)

```bash
./install.sh
```

Instala [Clified](https://pypi.org/project/clified/) via PyPI se necessário, compila o binário Rust, cria `.venv` com dependências Python e regista `ai2print` em `~/.local/bin`.

Alias legado: `stl-repair-gui`.

## Uso

```bash
ai2print
# ou, no repo clonado:
./run.sh
```

## Pré-requisitos

- Python 3.10+ com **pip** (`python3-full` no Debian/Ubuntu)
- Rust (`cargo`) e GTK4 dev (Linux: `libgtk-4-dev`, etc.)
- Opcional: Blender (`STL_REPAIR_BLENDER`) para conversão GLB

O `install.sh` detecta automaticamente um Python com pip (ignora venvs sem pip no PATH) e trata PEP 668 (`--break-system-packages` quando necessário). Requer Clified **>= 0.4.1** no PyPI.

## Resolução de problemas

| Problema | Solução |
|----------|---------|
| `No module named pip` | Defina `PYTHON_CMD=/usr/bin/python3.14` ou instale `python3-full` |
| `externally-managed-environment` | Automático no `install.sh`; ou `pipx install clified` |
| GUI abre mas Python falha | Reinstale: `./install.sh --action reinstall` |

## Desenvolvimento

```bash
cargo build --release
./run.sh
```

Reinstalar após mudanças:

```bash
./install.sh --action reinstall
```
