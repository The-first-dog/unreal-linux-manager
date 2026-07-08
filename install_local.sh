#!/usr/bin/env bash
#
# Local, user-space installation for Unreal Linux Manager.
#
# Creates an isolated Python virtual environment in ./.venv and installs the
# runtime dependencies (PySide6). Nothing is installed system-wide, which makes
# this safe on immutable / atomic distributions (Bazzite, Fedora Atomic).
#
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

VENV_DIR="$SCRIPT_DIR/.venv"
PYTHON_BIN="${PYTHON:-python3}"

echo "==> Unreal Linux Manager : installation locale"

# --- Python version check -------------------------------------------------- #
if ! command -v "$PYTHON_BIN" >/dev/null 2>&1; then
    echo "Erreur : '$PYTHON_BIN' introuvable. Installez Python 3.11+." >&2
    exit 1
fi

PY_VER="$("$PYTHON_BIN" -c 'import sys; print("%d.%d" % sys.version_info[:2])')"
echo "==> Python détecté : $PY_VER"
"$PYTHON_BIN" -c 'import sys; raise SystemExit(0 if sys.version_info[:2] >= (3, 11) else 1)' || {
    echo "Erreur : Python 3.11 ou supérieur est requis (tomllib)." >&2
    exit 1
}

# --- Virtual environment --------------------------------------------------- #
if [[ ! -d "$VENV_DIR" ]]; then
    echo "==> Création de l'environnement virtuel dans $VENV_DIR"
    # --system-site-packages lets PySide6 fall back to a distro/Flatpak build
    # if pip cannot provide a wheel, which helps on some atomic setups.
    "$PYTHON_BIN" -m venv "$VENV_DIR"
else
    echo "==> Environnement virtuel déjà présent, réutilisation."
fi

# shellcheck disable=SC1091
source "$VENV_DIR/bin/activate"

echo "==> Mise à jour de pip"
python -m pip install --upgrade pip >/dev/null

echo "==> Installation des dépendances (PySide6)"
if [[ -f "$SCRIPT_DIR/requirements.txt" ]]; then
    python -m pip install -r "$SCRIPT_DIR/requirements.txt"
else
    python -m pip install "PySide6>=6.5,<7"
fi

echo ""
echo "==> Installation terminée."
echo "    Lancez l'application avec :  ./run.sh"
