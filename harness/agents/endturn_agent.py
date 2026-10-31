"""End-turn agent: takes no actions, just ends every turn. Useful as a smoke test of the loop.

python -m agents.endturn_agent --url http://localhost:7777
Run from harness/.
"""
from agents.runner import newgame_opts, parser, play
from bridge import Bridge
from gamelog import GameLog, summarize


def play_endturn(bridge, log, newgame_opts=None):
    return play(bridge, log, lambda choices: None, newgame_opts=newgame_opts)


def main(argv=None):
    args = parser("End-turn agent: ends every turn without acting.").parse_args(argv)
    with GameLog("endturn", args.log_dir) as log:
        play_endturn(Bridge(args.url), log, newgame_opts=newgame_opts(args))
    print(f"log: {log.path}")
    summarize(log.path)


if __name__ == "__main__":
    main()
