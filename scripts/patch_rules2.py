from pathlib import Path
old = "Units count against the city that trained them."
new = ("Units count against the city that trained them: a city holds at most level+1 units, and it can train only "
       "while it is below that and no unit stands on its tile. The state shows each city's total population and the "
       "total at which it reaches the next level.")
for p in sorted(Path(r"C:\Users\caleb\Workspace\projects\polytopia\prompts").glob("system*.md")):
    s = p.read_text(encoding="utf-8-sig")
    if new in s: print("already", p.name); continue
    assert s.count(old) == 1, p.name
    p.write_text(s.replace(old, new), encoding="utf-8"); print("patched", p.name)
a = Path(r"C:\Users\caleb\Workspace\projects\polytopia\spec\API.md"); s = a.read_text(encoding="utf-8")
s = s.replace("`popMax` = level+1 (assumption, unverified).",
              "`pop` is the game's running population total (level L+1 is reached at (L+1)(L+2)/2 - 1, checked on 319/328 city-turns); `popMax` = level+1, which is really the city's unit limit.")
s = s.replace("- v1.1, 25 Oct 2026:", "- v1.2, 27 Oct 2026: `/resume`; opponents carry `rel` (peace, cooldown) and `out`; actions `peace` (forced accept/decline) and `diplomacy`; `pop`/`popMax` meaning corrected.\n- v1.1, 25 Oct 2026:")
a.write_text(s, encoding="utf-8"); print("spec updated")
