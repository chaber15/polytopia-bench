"""Generate the model's game reference from your copy of the game: reference/reference.md (filled into every
system prompt at {{REFERENCE}} when a game starts), reference/units.json and reference/tribes.md.
These are the game's own text, so they stay local (gitignored) and are never committed.

Run from the repo root:  harness\\.venv\\Scripts\\python scripts\\apply_reference.py
Inputs (local only, gitignored): reference/GameLogicData28.json, reference/loc-en.tsv (plugin `locdump`).
"""
import os, subprocess, sys
from pathlib import Path

root = Path(__file__).resolve().parents[1]
ref_dir = root / "reference"
ref = subprocess.run([sys.executable, str(ref_dir / "gen_reference.py"), str(ref_dir / "GameLogicData28.json"),
                      str(ref_dir / "loc-en.tsv"), str(ref_dir / "units.json"), str(ref_dir / "tribes.md")], capture_output=True, text=True, encoding="utf-8", check=True,
                     env={**os.environ, "PYTHONIOENCODING": "utf-8"}).stdout
(ref_dir / "reference.md").write_text(ref, encoding="utf-8")
print(f"wrote reference.md ({len(ref)} chars), units.json, tribes.md in {ref_dir}")
