from pathlib import Path
old = "`reward` (forced choice), "
new = ("`reward` / `peace` (forced choices: a city reward, or answering a CPU's peace offer with accept or decline), "
       "`diplomacy` (e.g. `BreakPeace` ends a peace treaty, `PeaceTreaty` offers one; while at peace you can't attack that tribe), ")
for p in sorted(Path(r"C:\Users\caleb\Workspace\projects\polytopia\prompts").glob("system*.md")):
    s = p.read_text(encoding="utf-8-sig")
    if new in s: print("already", p.name); continue
    assert s.count(old) == 1, p.name
    s = s.replace(old, new).replace("If a `reward` (forced choice) is listed", "If a `reward` or `peace` (forced choice) is listed")
    p.write_text(s, encoding="utf-8"); print("patched", p.name)
