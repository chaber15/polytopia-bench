"""Game loop shared by the agents: start the game, act, end turns, log everything."""
import argparse

from bridge import DEFAULT_URL, BridgeError, apply_changes


def play(bridge, log, choose, max_actions=20, newgame_opts=None, max_errors=10):
    """Play one game to game over.

    choose(choices) gets the non-endTurn actions and returns (action, to) to send,
    or None to end the turn. `to` is the target to send, or None if the action takes none.
    """
    phase = bridge.status()["phase"]
    if phase == "menu":
        bridge.newgame(**(newgame_opts or {}))
    elif phase != "my_turn":
        raise RuntimeError(f"cannot start a game: phase is {phase}")
    state = bridge.state()
    while True:
        turn = state["turn"]
        log.turn_start(turn, state)
        taken = errors = 0
        actions = bridge.actions()
        while taken < max_actions and errors < max_errors:
            choices = [a for a in actions["actions"] if a["k"] != "endTurn"]
            picked = choose(choices) if choices else None
            if picked is None:
                break
            action, to = picked
            sent = {k: v for k, v in action.items() if k != "to"}
            if to is not None:
                sent["to"] = to
            try:
                res = bridge.act(actions["stateId"], action["id"], to)
            except BridgeError as e:
                errors += 1
                log.error(turn, str(e), action=sent)
            else:
                log.action(turn, sent, res)
                state = apply_changes(state, res.get("changes", {}))
                state["stateId"] = res["stateId"]
                taken += 1
            actions = bridge.actions()  # ids are per answer; refetch after every act
        end = bridge.end_turn()
        if end["phase"] == "game_over":
            break
        state = bridge.state()
    result = bridge.result()
    log.game_end(result)
    return result


def add_common_args(p):
    p.add_argument("--url", default=DEFAULT_URL)
    p.add_argument("--log-dir", default=None, help="default: harness/logs")
    p.add_argument("--mode")
    p.add_argument("--difficulty")
    p.add_argument("--opponents", type=int)
    p.add_argument("--mapSize", type=int)
    p.add_argument("--tribe")
    return p


def newgame_opts(args):
    """Only the newgame options given on the command line; the server fills in the rest."""
    keys = ("mode", "difficulty", "opponents", "mapSize", "tribe")
    return {k: getattr(args, k) for k in keys if getattr(args, k) is not None}


def parser(description):
    return add_common_args(argparse.ArgumentParser(description=description))
