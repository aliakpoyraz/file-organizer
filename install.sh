#!/usr/bin/env bash
#
# fo (file-organizer) installer.
#
#   curl -fsSL https://raw.githubusercontent.com/aliakpoyraz/file-organizer/main/install.sh | bash
#
# Downloads a prebuilt standalone `fo` binary (no Python required) that matches
# your OS/CPU. If no prebuilt binary is available it falls back to installing
# from source with pipx/pip.

set -euo pipefail

REPO="aliakpoyraz/file-organizer"

c_info() { printf '\033[36m%s\033[0m\n' "$*"; }
c_ok()   { printf '\033[32m%s\033[0m\n' "$*"; }
c_warn() { printf '\033[33m%s\033[0m\n' "$*"; }
c_err()  { printf '\033[31m%s\033[0m\n' "$*" >&2; }

# --- Pick an install directory --------------------------------------------
pick_bindir() {
  if [ -w "/usr/local/bin" ] 2>/dev/null; then
    echo "/usr/local/bin"
  else
    echo "$HOME/.local/bin"
  fi
}

install_from_source() {
  c_warn "Installing from source instead (requires Python 3.11+)."
  local pkg="git+https://github.com/${REPO}.git"
  if command -v pipx >/dev/null 2>&1; then
    pipx install --force "$pkg"
  elif command -v python3 >/dev/null 2>&1; then
    python3 -m pip install --user --upgrade "$pkg"
  else
    c_err "Neither a prebuilt binary nor Python is available. Install Python 3.11+ and retry."
    exit 1
  fi
  c_ok "Installed. Start it with:  fo"
  exit 0
}

# --- Detect the matching release asset ------------------------------------
os="$(uname -s)"
arch="$(uname -m)"
asset=""
case "$os" in
  Darwin)
    case "$arch" in
      arm64) asset="fo-macos-arm64" ;;
      x86_64) asset="fo-macos-x86_64" ;;
    esac ;;
  Linux)
    case "$arch" in
      x86_64) asset="fo-linux-x86_64" ;;
    esac ;;
esac

if [ -z "$asset" ]; then
  c_warn "No prebuilt binary for ${os}/${arch}."
  install_from_source
fi

url="https://github.com/${REPO}/releases/latest/download/${asset}"
bindir="$(pick_bindir)"
mkdir -p "$bindir"
tmp="$(mktemp)"

c_info "Downloading ${asset} ..."
if ! curl -fsSL "$url" -o "$tmp"; then
  c_warn "Could not download a prebuilt binary (no release published yet?)."
  rm -f "$tmp"
  install_from_source
fi

chmod +x "$tmp"
mv "$tmp" "$bindir/fo"
c_ok "Installed fo to $bindir/fo"

ensure_on_path() {
  case ":$PATH:" in
    *":$bindir:"*) return 0 ;;
  esac
  local line="export PATH=\"$bindir:\$PATH\""
  local rc=""
  case "$(basename "${SHELL:-}")" in
    zsh)  rc="$HOME/.zshrc" ;;
    bash) [ -f "$HOME/.bashrc" ] && rc="$HOME/.bashrc" || rc="$HOME/.bash_profile" ;;
  esac
  if [ -n "$rc" ]; then
    if [ -f "$rc" ] && grep -Fq "$bindir" "$rc"; then :; else
      printf '\n# added by fo installer\n%s\n' "$line" >> "$rc"
      c_info "Added $bindir to PATH in $rc"
    fi
    c_warn "Restart your terminal (or run: source $rc) to use 'fo'."
  else
    c_warn "Add this to your shell profile so 'fo' is found:"
    c_warn "  $line"
  fi
}
ensure_on_path

echo
c_ok "Done. Start it with:"
echo "  fo"
