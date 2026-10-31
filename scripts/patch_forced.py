import re, pathlib
h = pathlib.Path(r"C:\Users\caleb\Workspace\projects\polytopia\harness")

def sub(path, old, new, count=1):
    p = h / path; s = p.read_text(encoding="utf-8")
    assert s.count(old) >= 1, (path, old[:60])
    p.write_text(s.replace(old, new, count), encoding="utf-8")

# 1. Bridge helper: pick the first option of any pending forced choice.
p = h / "bridge.py"; s = p.read_text(encoding="utf-8")
anchor = "\ndef apply_changes("
helper = '''
    def resolve_forced(self, max_steps=5):
        """Pick the first option of any pending forced choice (city reward), so a turn can end.
        Only for when the harness must end the turn itself; returns the actions picked."""
        picked = []
        for _ in range(max_steps):
            a = self.actions()
            if not a.get("forced"):
                break
            opt = next((x for x in a["actions"] if x["k"] != "endTurn"), None)
            if opt is None:
                break
            self.act(a["stateId"], opt["id"])
            picked.append(opt)
        return picked

'''
assert anchor in s
s = s.replace(anchor, helper + anchor, 1)
p.write_text(s, encoding="utf-8")

# 2. MCP server: explicit end_turn with a pending choice gets a clear error; forced ends resolve it first.
sub("mcp_poly.py",
    '''    def _do_end_turn(self):
        res = self.bridge.end_turn()''',
    '''    def _do_end_turn(self, force=False):
        if force:
            self.resolved = self.bridge.resolve_forced()
        elif self.bridge.actions().get("forced"):
            raise BridgeError("A forced choice (city reward) is pending: pick one of the REWARD actions "
                              "first, then call end_turn.")
        res = self.bridge.end_turn()''')
sub("mcp_poly.py",
    '''        out = self._do_end_turn()
        return (prefix''',
    '''        out = self._do_end_turn(force=True)
        return (prefix''')

# 3. play.py fallback: resolve before ending the turn itself.
sub("play.py",
    '''            try:
                res = bridge.end_turn()''',
    '''            try:
                for opt in bridge.resolve_forced():
                    log.error(turn, f"harness picked forced choice for the model: {opt}")
                res = bridge.end_turn()''')

# 4. Louder prompt line.
sub("render.py",
    '''lines = ["FORCED choice pending: resolve it first."] if forced else []''',
    '''lines = ["FORCED CHOICE PENDING: pick one REWARD below before any other action; end_turn is refused until you do."] if forced else []''')
print("patched")
