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
comparisons can separate prompt conditions.

`--prompt-version v3` removes the board rendering from both the observation and
action descriptions. For 2048, the model receives a verbal summary of score,
tile counts, empty spaces, and invalid-move streak, plus verbal previews of
each slide's merges and resulting score. It never receives tile positions or a
rendered board. Sokoban likewise uses a verbal status and action outcomes
without a grid. Blackjack spells out visible cards and keeps its v2 decision
context. No version uses a hidden dealer card or future random tile location.

`--prompt-version v4 --games 2048-v0-super-easy` ports the feature labels from
[FluidUse's GLiClass 2048 demo](https://github.com/FluidInference/FluidUse/tree/main/Sources/GLiClass2048Demo).
The model receives a fixed safety goal and, for each direction, the empty-cell
count after the slide, score gain, whether the largest tile is in a corner,
monotonicity penalty, and roughness. Neither the current nor resulting board is
sent. The feature calculations follow FluidUse's `Game2048.describe` and
`Game2048.features`. This prompt-only comparison retains all four directions,
including no-effect moves. It does not apply FluidUse's heuristic shortlist,
one-move lookahead, or confidence-margin fallback, which are separate policy
choices rather than prompt text.

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

The [2048 v1/v2 prompt comparison](../benchmarks/2048-v1-v2-seed100-20/README.md)
includes its run settings, aggregate results, and raw per-episode JSON.
The [2048 v3 verbal-only pilot](../benchmarks/2048-v3-seed100-20/README.md)
compares Jev against those runs on the same 20 seeds.

The runner covers single-player games and does not calculate confidence
intervals or publish a model leaderboard.
