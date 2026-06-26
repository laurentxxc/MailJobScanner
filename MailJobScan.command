#!/usr/bin/env bash
cd "$(dirname "$0")"
if [ -f .dashboard.pid ] && kill -0 "$(cat .dashboard.pid 2>/dev/null)" 2>/dev/null; then
	open http://localhost:8501
else
	exec .venv/bin/python3 launcher.py
fi
