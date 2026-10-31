from pathlib import Path
w = Path(r"C:\Users\caleb\Workspace\projects\polytopia")
p = w / "prompts" / "system-might.md"
s = p.read_text(encoding="utf-8-sig")
s = s.replace("CPUs capital", "CPU's capital").replace("act, dont ask", "act, don't ask")
p.write_text(s, encoding="utf-8")
g = w / "scripts" / "game.ps1"
s = g.read_text(encoding="utf-8")
s = s.replace('# Domination with opponents > 1 uses prompts\\system-domination-multi.md, an 80-turn cap and 100 tool calls per turn.',
              '# Domination with opponents > 1 uses prompts\\system-domination-multi.md, an 80-turn cap and 100 tool calls per turn.\n'
              '# Might (win by taking the CPU capital) uses prompts\\system-might.md and a 60-turn cap.\n'
              '# -compact runs every game with play.py --compact (batched act, turn-stable ids, diff-only results).')
s = s.replace('param([string]$games, [string]$after = "", [string]$marker = "queue")',
              'param([string]$games, [string]$after = "", [string]$marker = "queue", [switch]$compact)')
s = s.replace('$prompt = if ($mode -eq "Domination") {', '$prompt = if ($mode -eq "Might") { "system-might" } elseif ($mode -eq "Domination") {')
s = s.replace('$turns = if ($mode -ne "Domination") { "--turns 30" }', '$turns = if ($mode -eq "Might") { "--turns 60 --max-minutes 240" } elseif ($mode -ne "Domination") { "--turns 30" }')
s = s.replace('$turns --claude', '$turns $(if ($compact) { "--compact" }) --claude')
g.write_text(s, encoding="utf-8")
print(p.read_text(encoding="utf-8").splitlines()[0])
print("\n".join(l for l in s.splitlines() if "Might" in l or "compact" in l))
