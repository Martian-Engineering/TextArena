"""Run the TextArena decision-model pilot from the command line."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

from .prompts import PROMPT_VERSIONS
from .runner import GAME_ACTIONS, RandomPolicy, run_benchmark
from .systemone import SystemOnePolicy


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--games", default=",".join(GAME_ACTIONS))
    parser.add_argument("--policy", choices=("random", "systemone"), default="random")
    parser.add_argument("--name", default="decision-model")
    parser.add_argument("--endpoint")
    parser.add_argument("--model")
    parser.add_argument("--api-key-env")
    parser.add_argument("--episodes", type=int, default=3)
    parser.add_argument("--seed", type=int, default=100)
    parser.add_argument("--max-decisions", type=int, default=500)
    parser.add_argument("--prompt-version", choices=PROMPT_VERSIONS, default="v1")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    games = tuple(game.strip() for game in args.games.split(","))
    unknown = set(games) - GAME_ACTIONS.keys()
    if unknown:
        parser.error(f"unsupported games: {', '.join(sorted(unknown))}")
    if args.prompt_version == "v4" and any(
        not game.startswith("2048-") for game in games
    ):
        parser.error("v4 is available only for 2048; pass --games 2048-v0-super-easy")
    if args.policy == "systemone":
        if not all((args.endpoint, args.model, args.api_key_env)):
            parser.error("systemone requires --endpoint, --model, and --api-key-env")
        if not os.environ.get(args.api_key_env):
            parser.error(f"{args.api_key_env} is not set")
        policy_factory = lambda seed: SystemOnePolicy(
            name=args.name,
            endpoint=args.endpoint,
            model=args.model,
            api_key_env=args.api_key_env,
        )
    else:
        policy_factory = RandomPolicy

    result = run_benchmark(
        games,
        policy_factory,
        first_seed=args.seed,
        episodes=args.episodes,
        max_decisions=args.max_decisions,
        prompt_version=args.prompt_version,
    )
    with args.output.open("x") as output:
        json.dump(result, output, indent=2)
        output.write("\n")
    print(f"Wrote {len(result['results'])} episodes to {args.output}")
    failures = sum(
        row["terminal_reason"] == "invalid_policy_choice"
        or str(row["terminal_reason"]).startswith("policy_error:")
        for row in result["results"]
    )
    if failures:
        parser.exit(1, f"{failures} policy failures; results saved to {args.output}\n")


if __name__ == "__main__":
    main()
