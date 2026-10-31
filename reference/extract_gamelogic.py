"""Copy the game's rules table (TextAsset GameLogicData28) out of your own install into reference/, read-only on the game.

Usage: python reference/extract_gamelogic.py ["<game folder>"]   (needs: pip install UnityPy)
Default folder: the Steam install on Windows. Writes reference/GameLogicData28.json (gitignored: it is the game's data).
"""
import sys
from pathlib import Path

import UnityPy

game = Path(sys.argv[1] if len(sys.argv) > 1 else r"C:\Program Files (x86)\Steam\steamapps\common\The Battle of Polytopia")
bundle = game / "Polytopia_Data" / "data.unity3d"
out = Path(__file__).resolve().parent / "GameLogicData28.json"
for obj in UnityPy.load(str(bundle)).objects:
    if obj.type.name == "TextAsset":
        asset = obj.read()
        if getattr(asset, "m_Name", getattr(asset, "name", "")) == "GameLogicData28":
            text = asset.m_Script if isinstance(asset.m_Script, str) else bytes(asset.m_Script).decode("utf-8")
            out.write_text(text, encoding="utf-8")
            print(f"wrote {out} ({len(text)} chars)")
            break
else:
    sys.exit(f"GameLogicData28 not found in {bundle} (a different game build?)")
