#!/usr/bin/env bash
cd "$(dirname "$0")/.."
if [ -f __private__/.dashboard.pid ] && kill -0 "$(cat __private__/.dashboard.pid 2>/dev/null)" 2>/dev/null; then
	open http://localhost:8501
else
	exec .venv/bin/python3 MacOS/launcher.py
fi
