#!/usr/bin/env bash
# Setup script for Space Shooter — creates a local venv and installs pygame
# Works on WSL even when working under /mnt/c by handling Windows vs Linux venv layouts.

set -euo pipefail

echo "=== Space Shooter Setup (venv) ==="

# Always run from the script's directory
SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

# Prefer WSL/Linux python to avoid Windows venv layout under /mnt/c
PY="/usr/bin/python3"
if [ ! -x "$PY" ]; then
  # fallback to python3 in PATH
  if command -v python3 >/dev/null 2>&1; then
    PY="$(command -v python3)"
  else
    echo "ERROR: Python 3 not found. Please install Python 3."
    exit 1
  fi
fi
echo "Using Python at: $PY"

# Make sure venv module exists
if ! "$PY" -m venv --help >/dev/null 2>&1; then
  echo "Python venv module not available. Attempting to install..."
  if command -v apt-get >/dev/null 2>&1; then
    sudo apt-get update
    sudo apt-get install -y python3-venv
  else
    echo "Couldn't auto-install venv tools. Install a Python venv package and re-run."
    exit 1
  fi
fi

VENV_DIR=".venv"

# Create venv if missing
if [ ! -d "$VENV_DIR" ]; then
  echo "Creating virtual environment in $VENV_DIR ..."
  "$PY" -m venv "$VENV_DIR"
fi

# Find the correct activation script (Linux = bin/activate, Windows = Scripts/activate)
ACTIVATE=""
if [ -f "$VENV_DIR/bin/activate" ]; then
  ACTIVATE="$VENV_DIR/bin/activate"
elif [ -f "$VENV_DIR/Scripts/activate" ]; then
  ACTIVATE="$VENV_DIR/Scripts/activate"
else
  echo "ERROR: Could not find venv activation script in '$VENV_DIR'."
  echo "       Expected either '$VENV_DIR/bin/activate' or '$VENV_DIR/Scripts/activate'."
  exit 1
fi

# shellcheck disable=SC1090
source "$ACTIVATE"

# Inside venv, upgrade tooling and install pygame
python -m pip install --upgrade pip setuptools wheel
if ! python - <<'PYCHK'
try:
    import pygame  # noqa: F401
except Exception as e:
    raise SystemExit(1)
PYCHK
then
  echo "Installing pygame in the virtualenv ..."
  python -m pip install "pygame>=2.5"
else
  echo "pygame already present in the virtualenv."
fi

# Create a helper launcher (no auto-run)
cat > run_game.sh <<'LAUNCH'
#!/usr/bin/env bash
set -euo pipefail
SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"

# Choose activation script dynamically
if [ -f "$SCRIPT_DIR/.venv/bin/activate" ]; then
  # shellcheck disable=SC1091
  source "$SCRIPT_DIR/.venv/bin/activate"
elif [ -f "$SCRIPT_DIR/.venv/Scripts/activate" ]; then
  # shellcheck disable=SC1091
  source "$SCRIPT_DIR/.venv/Scripts/activate"
else
  echo "ERROR: venv not found. Run ./setup_space_shooter.sh first."
  exit 1
fi

python "$SCRIPT_DIR/space_shooter.py"
LAUNCH
chmod +x run_game.sh

echo "=== Setup complete! ==="
echo "To play later, run: ./run_game.sh"
