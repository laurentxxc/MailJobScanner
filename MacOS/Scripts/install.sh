#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(dirname "$(dirname "$SCRIPT_DIR")")"
MACOS_DIR="$PROJECT_DIR/MacOS"
LAUNCHER="$MACOS_DIR/MailJobScan.command"

echo "Compiling AppleScripts..."
osacompile -o "$SCRIPT_DIR/mailjobscan.scpt" "$SCRIPT_DIR/mailjobscan.applescript"
osacompile -o "$SCRIPT_DIR/mailjobscan_rule.scpt" "$SCRIPT_DIR/mailjobscan_rule.applescript"

echo "Installing manual script to ~/Library/Scripts/Applications/Mail/..."
mkdir -p ~/Library/Scripts/Applications/Mail/
cp "$SCRIPT_DIR/mailjobscan.scpt" ~/Library/Scripts/Applications/Mail/

echo "Installing rule script to ~/Library/Application Scripts/com.apple.mail/..."
mkdir -p ~/Library/Application\ Scripts/com.apple.mail/
cp "$SCRIPT_DIR/mailjobscan_rule.scpt" ~/Library/Application\ Scripts/com.apple.mail/

echo "Making Dashboard launcher executable..."
chmod +x "$LAUNCHER"

echo "Applying app icon to launcher..."
ICON_SRC="$SCRIPT_DIR/appIcon.png"
if [ -f "$ICON_SRC" ]; then
	if command -v fileicon &>/dev/null; then
		fileicon set "$LAUNCHER" "$ICON_SRC"
		echo "App icon applied via fileicon."
	elif command -v brew &>/dev/null; then
		echo "Installing fileicon via Homebrew..."
		brew install fileicon
		fileicon set "$LAUNCHER" "$ICON_SRC"
		echo "App icon applied via fileicon."
	else
		echo "Warning: fileicon not available. Install it with 'brew install fileicon' and re-run install.sh."
	fi
else
	echo "No appIcon.png found — using default icon."
fi

echo "Done. Restart Mail.app if needed."
