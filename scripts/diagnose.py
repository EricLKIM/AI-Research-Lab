from __future__ import annotations
import importlib
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
src = PROJECT_ROOT / "src"
if str(src) not in sys.path:
    sys.path.insert(0, str(src))

print("=== AI Research Lab Diagnostic ===")
print(f"Python: {sys.executable}")
print(f"Project: {PROJECT_ROOT}")
print(f"Python version: {sys.version}")

print("[1] tkinter import")
import tkinter
print("OK: tkinter")

print("[2] app module import")
importlib.import_module("app")
print("OK: app import")

print("[3] research_lab package import")
importlib.import_module("research_lab")
print("OK: research_lab import")

print("[4] GUI launch")
import app
app.main()
