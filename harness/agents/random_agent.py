"""Random agent: each turn, random non-endTurn actions up to a cap, then end the turn.

python -m agents.random_agent --url http://localhost:7777 --seed 1 --max-actions 20
Run from harness/.
"""
import random

from agents.runner import newgame_opts, parser, play
from bridge import Bridge
from gamelog import GameLog, summarize


def play_random(bridge, log, seed=None, max_actions=20, newgame_opts=None):
    rng = random.Random(seed)

    def choose(choices):
        action = rng.choice(choices)
        to = action.get("to")
        if to and isinstance(to[0], list):  # grouped move: pick one of its targets
            to = rng.choice(to)
        return action, to

    return play(bridge, log, choose, max_actions=max_actions, newgame_opts=newgame_opts)


def main(argv=None):
    p = parser("Random agent: plays a full game against the PolyBridge API.")
    p.add_argument("--seed", type=int, default=None)
    p.add_argument("--max-actions", type=int, default=20)
    args = p.parse_args(argv)
    with GameLog("random", args.log_dir) as log:
        play_random(Bridge(args.url), log, seed=args.seed, max_actions=args.max_actions,
                    newgame_opts=newgame_opts(args))
    print(f"log: {log.path}")
    summarize(log.path)


if __name__ == "__main__":
    main()
