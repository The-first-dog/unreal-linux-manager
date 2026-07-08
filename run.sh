#!/usr/bin/env bash
#
# Launch Unreal Linux Manager from a local virtual environment.
#
# If ./install_local.sh has been run, a .venv exists and is used. Otherwise we
# fall back to the system Python (which must already have PySide6 available).
#
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

VENV_DIR="$SCRIPT_DIR/.venv"

if [[ -d "$VENV_DIR" ]]; then
    # shellcheck disable=SC1091
    source "$VENV_DIR/bin/activate"
    PYTHON="python"
else
    echo "Note : environnement virtuel .venv absent. Utilisation du Python système."
    echo "       Lancez ./install_local.sh pour une installation isolée propre."
    PYTHON="${PYTHON:-python3}"
fi

# Ensure the src/ layout is importable without an editable install.
export PYTHONPATH="$SCRIPT_DIR/src${PYTHONPATH:+:$PYTHONPATH}"

exec "$PYTHON" -m unreal_linux_manager.main "$@"
