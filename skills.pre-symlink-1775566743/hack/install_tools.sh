#!/bin/bash
set -euo pipefail

INSTALL_DIR="$HOME/workspace/experiments/Readarr"

echo "=== Installing Tools ==="

# Install Readarr
echo "Installing Readarr to $INSTALL_DIR..."
mkdir -p "$INSTALL_DIR"

# Readarr develop branch URL (use HTTPS)
DOWNLOAD_URL="https://readarr.servarr.com/v1/update/develop/updatefile?os=linux&runtime=netcore&arch=x64"

TMPFILE="$(mktemp /tmp/readarr.XXXXXX.tar.gz)"
echo "Downloading Readarr..."
curl --fail --location --show-error --output "$TMPFILE" "$DOWNLOAD_URL"

echo "Extracting..."
tar -xzf "$TMPFILE" -C "$INSTALL_DIR" --strip-components=1
rm -f "$TMPFILE"

if [[ -x "$INSTALL_DIR/Readarr" ]]; then
  echo "Readarr installed successfully."
  echo "Run it with: $INSTALL_DIR/Readarr"
else
  echo "[ERROR] Readarr binary not found or not executable in $INSTALL_DIR" >&2
  exit 1
fi
