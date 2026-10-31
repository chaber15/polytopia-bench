"""Check for bridge step 4: new game, call only /end_turn until game over, print /result, /quit, then /newgame again.
Usage: endturn_only.py [--once]   (stdlib only)"""
import json, sys, time, urllib.request
B = "http://localhost:7777"
def call(path, body=None):
    req = urllib.request.Request(B + path, data=None if body is None else json.dumps(body).encode(), method="GET" if body is None else "POST")
    return json.loads(urllib.request.urlopen(req, timeout=300).read())
def one_game():
    t0 = time.time()
    print("newgame", call("/newgame", {}))
    n = 0
    while True:
        r = call("/end_turn", {})
        n += 1
        if not r["ok"]: print("end_turn failed", r); return False
        if r.get("phase") == "game_over": break
    dt = time.time() - t0
    print(f"game over after {n} end_turns, turn {r['turn']}, {dt:.0f}s total, {dt / n:.1f}s per end_turn")
    print("result", call("/result"))
    print("quit", call("/quit", {}))
    print("status", call("/status"))
    return True
ok = one_game()
if ok and "--once" not in sys.argv:
    ok = one_game()
sys.exit(0 if ok else 1)
