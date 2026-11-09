#!/bin/sh
# Launcher for the /prospect tool (macOS, Linux, and Windows Git Bash).
# Finds a working Python 3.9+, installs Python if none is found, then runs prospect.py.
# No Python packages are needed - the tool only uses the standard library.

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
CHECK='import sys; sys.exit(0 if sys.version_info >= (3, 9) else 1)'

find_python() {
  for c in python3 python; do
    if command -v "$c" >/dev/null 2>&1 && "$c" -c "$CHECK" >/dev/null 2>&1; then
      "$c" -c 'import sys; print(sys.executable)'
      return 0
    fi
  done
  if command -v py >/dev/null 2>&1 && py -3 -c "$CHECK" >/dev/null 2>&1; then
    py -3 -c 'import sys; print(sys.executable)'
    return 0
  fi
  # Installed but not on PATH yet (e.g. straight after a winget install)
  for p in "$HOME"/AppData/Local/Programs/Python/Python3*/python.exe /c/Python3*/python.exe \
           "/c/Program Files/Python3"*/python.exe /opt/homebrew/bin/python3 /usr/local/bin/python3 /usr/bin/python3; do
    if [ -f "$p" ] && "$p" -c "$CHECK" >/dev/null 2>&1; then
      echo "$p"
      return 0
    fi
  done
  return 1
}

install_python() {
  echo "Python 3 was not found - installing it (one-time setup)..." >&2
  case "$(uname -s 2>/dev/null)" in
    MINGW*|MSYS*|CYGWIN*)
      if command -v winget >/dev/null 2>&1; then
        winget install -e --id Python.Python.3.12 --scope user --silent \
          --accept-package-agreements --accept-source-agreements >&2
      else
        echo "winget is not available. Install Python from https://www.python.org/downloads/ (tick 'Add to PATH')." >&2
      fi ;;
    Darwin)
      if command -v brew >/dev/null 2>&1; then
        brew install python >&2
      else
        echo "Install Python from https://www.python.org/downloads/ (or install Homebrew, then: brew install python)." >&2
      fi ;;
    Linux)
      if command -v apt-get >/dev/null 2>&1 && sudo -n true 2>/dev/null; then
        sudo apt-get install -y python3 >&2
      elif command -v dnf >/dev/null 2>&1 && sudo -n true 2>/dev/null; then
        sudo dnf install -y python3 >&2
      else
        echo "Install Python 3 with your package manager, e.g.: sudo apt-get install -y python3" >&2
      fi ;;
  esac
}

PY="$(find_python)"
if [ -z "$PY" ]; then
  install_python
  PY="$(find_python)"
fi
if [ -z "$PY" ]; then
  echo "ERROR: Python 3.9+ is required and could not be installed automatically. Install it, then run this again." >&2
  exit 3
fi

# Windows paths from sys.executable (C:\...) work better in Git Bash in /c/... form
if command -v cygpath >/dev/null 2>&1; then
  PY="$(cygpath -u "$PY")"
fi

PYTHONIOENCODING=utf-8 PYTHONDONTWRITEBYTECODE=1 exec "$PY" "$SCRIPT_DIR/prospect.py" "$@"
