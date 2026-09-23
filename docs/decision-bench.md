# Decision-model pilot

This fork adds a fixed-choice evaluation track for decision models. It uses
TextArena's game engines, including this fork's three-strike rule for 2048. The
track contains `2048-v0-super-easy`, `Sokoban-v0`, and `Blackjack-v0`. The first two have four
syntactically valid direction commands; Blackjack has `HIT` and `STAND`.

By default, `--prompt-version v1` preserves the original request: the model sees
the game's instructions and latest player-visible game state, with short choice
labels such as `"LEFT": "Move left"`. It does not receive the environment's
internal state, past moves, or a solver-generated action shortlist. A choice can
still be a bad or blocked move; TextArena judges that move under its own rules.
In particular, 2048 and Sokoban can end on an invalid
move with a partial-completion reward. Therefore the output reports `success`,
`invalid_move`, and the raw game metric separately from `reward`. Blackjack
reports wins, losses, and draws; its `success` field is null because there is no
single binary objective across its five hands.
The action presentation order varies deterministically by game, seed, and turn.

Use `--prompt-version v2` to compare against more descriptive choice labels.
For 2048, each label previews merges, score, largest tile, remaining empty cells,
and the board after sliding but before the random tile spawns. It also shows the
current consecutive invalid-move count. For Sokoban, labels describe whether
the move is blocked, moves the player, or pushes a box onto or off a goal. For
Blackjack, labels describe the possible effect of drawing or standing using only
the visible player hand and dealer upcard; the dealer's hidden card is not used.
V2 also includes the visible move/hand count where useful. These previews do not
filter choices or change game rules. The output records `prompt_version`, so
comparisons can separate the two prompt conditions.

Install the decision-bench extra, which includes NumPy for Sokoban, then run a
seeded random pilot:

```sh
python -m pip install -e '.[decision-bench]'
python -m textarena.decision_bench --episodes 20 --seed 100 \
  --output random-decision-pilot.json
```

Run a Jev-compatible choice endpoint with the same games, seeds, and decision
cap:

```sh
python -m textarena.decision_bench --policy systemone --name jev \
  --endpoint https://api.typesafe.ai/v1/systemone --model jev-1.13.0 \
  --api-key-env TYPESAFE_API_KEY --episodes 20 --seed 100 --prompt-version v2 \
  --output jev-decision-pilot.json
```

The API key is read from the named environment variable. Output paths must not
already exist. `--games` accepts a comma-separated subset of the three supported
environment IDs, and `--max-decisions` defaults to 500. A decision-limit stop is
an incomplete episode, not a loss or a win. The JSON records the policy's model
identifier and each episode's native reward, success, invalid-move flag,
decisions, latency, and raw metric. Policy failures are saved and return a nonzero
exit status.
This pilot does not yet include multiplayer games, confidence intervals, or a
published model leaderboard.
