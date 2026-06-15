#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"

echo "Compiling AppleScripts..."
osacompile -o "$SCRIPT_DIR/mailjobscan.scpt" "$SCRIPT_DIR/mailjobscan.applescript"
osacompile -o "$SCRIPT_DIR/mailjobscan_rule.scpt" "$SCRIPT_DIR/mailjobscan_rule.applescript"

echo "Installing manual script to ~/Library/Scripts/Applications/Mail/..."
mkdir -p ~/Library/Scripts/Applications/Mail/
cp "$SCRIPT_DIR/mailjobscan.scpt" ~/Library/Scripts/Applications/Mail/

echo "Installing rule script to ~/Library/Application Scripts/com.apple.mail/..."
mkdir -p ~/Library/Application\ Scripts/com.apple.mail/
cp "$SCRIPT_DIR/mailjobscan_rule.scpt" ~/Library/Application\ Scripts/com.apple.mail/

echo "Done. Restart Mail.app if needed."
