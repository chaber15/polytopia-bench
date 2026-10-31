import pathlib
w = pathlib.Path(r"C:\Users\caleb\Workspace\projects\polytopia")
p = w / "harness" / "play.py"; s = p.read_text(encoding="utf-8")
old = 'bridge.newgame(mode=args.mode, difficulty=args.difficulty, tribe=args.tribe)'
assert old in s
s = s.replace(old, 'bridge.newgame(mode=args.mode, difficulty=args.difficulty, tribe=args.tribe,\n                       opponents=args.opponents, mapSize=args.map_size)')
old = 'p.add_argument("--tribe",'
s = s.replace(old, 'p.add_argument("--opponents", type=int, default=1)\n    p.add_argument("--map-size", type=int, default=11, help="map width: 11 Tiny, 14 Small, 16 Normal, 18 Large")\n    ' + old, 1)
p.write_text(s, encoding="utf-8")

d = (w / "prompts" / "system-domination.md").read_text(encoding="utf-8")
a = "You are playing The Battle of Polytopia (Domination mode, you vs 1 built-in CPU) through tools. Goal: **win by eliminating the CPU tribe** (capture or destroy all of its cities). There is no turn limit in Domination; this test stops at turn 60, and a game still running then counts as not won."
assert a in d
d = d.replace(a, "You are playing The Battle of Polytopia (Domination mode, Normal-size 16x16 map, you vs 3 built-in CPU tribes) through tools. Goal: **win by eliminating all three CPU tribes** (capture or destroy all of their cities). The CPUs are not allied with each other. There is no turn limit in Domination; this test stops at turn 80, and a game still running then counts as not won.")
d = d.replace("- **Losing:** if the CPU captures all your cities, you lose.", "- **Losing:** if the CPUs capture all your cities, you lose.")
d = d.replace("Max 40 tool calls per turn.", "")
(w / "prompts" / "system-domination-multi.md").write_text(d, encoding="utf-8")
print("ok")
