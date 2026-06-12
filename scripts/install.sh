#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"

echo "Compiling AppleScript..."
osacompile -o "$SCRIPT_DIR/mailjobscan.scpt" "$SCRIPT_DIR/mailjobscan.applescript"

echo "Installing to ~/Library/Scripts/Applications/Mail/..."
mkdir -p ~/Library/Scripts/Applications/Mail/
cp "$SCRIPT_DIR/mailjobscan.scpt" ~/Library/Scripts/Applications/Mail/

echo "Done. Restart Mail.app if needed."
