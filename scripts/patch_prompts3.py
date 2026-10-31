from pathlib import Path
old = "`move` (a unit, many destinations)"
new = "`move` (a unit and its destinations; `(1-3,5)` means x 1 to 3 at y 5)"
for p in sorted(Path(r"C:\Users\caleb\Workspace\projects\polytopia\prompts").glob("system*.md")):
    s = p.read_text(encoding="utf-8-sig")
    if new in s: print("already", p.name); continue
    assert s.count(old) == 1, p.name
    p.write_text(s.replace(old, new), encoding="utf-8"); print("patched", p.name)
