# Full-game 2048 prompt comparison

This run measures how far Jev gets when each game continues until it reaches
the 2048 tile or loses. It uses the same 20 seeds (100–119) for v1, v2, v3,
v4, and a random-action baseline. No condition reached 2048.

| Policy | Reached 2048 | Best tile | Games reaching 512+ | Games reaching 1024 | Mean decisions | Mean game score |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| Jev v1 | 0/20 | 8 | 0/20 | 0/20 | 9.95 | 17.4 |
| Jev v2 | 0/20 | 512 | 1/20 | 0/20 | 196.35 | 2,241.6 |
| Jev v3 | 0/20 | 512 | 1/20 | 0/20 | 192.6 | 2,072.8 |
| Jev v4 | 0/20 | 1024 | 19/20 | 10/20 | 641.65 | 10,193.2 |
| Random | 0/20 | 256 | 0/20 | 0/20 | 76.3 | 559.0 |

The highest tile in each of the 20 games gives a fuller view of the spread:

| Policy | Highest-tile distribution |
| --- | --- |
| Jev v1 | 2: 2 games; 4: 10; 8: 8 |
| Jev v2 | 128: 10; 256: 9; 512: 1 |
| Jev v3 | 64: 3; 128: 11; 256: 5; 512: 1 |
| Jev v4 | 256: 1; 512: 9; 1024: 10 |
| Random | 8: 1; 16: 2; 32: 5; 64: 8; 128: 3; 256: 1 |

V4 reached a higher tile than v2 on 18 paired seeds and tied on two; it never
reached a lower tile. The same comparison holds against v3. This measures
distance reached, not wins: even a game whose largest tile was 1024 lost.
The game's partial-completion `reward` can be 1.0 on a loss, so `success` and
`max_tile` are the appropriate fields here.

The game is `2048-v0`, Jev is `jev-1.13.0`, and the decision cap is disabled
(`--max-decisions 0`). V1 shows the board with plain direction labels; v2 adds
verbal move previews; v3 removes board renderings while retaining verbal
previews; v4 uses FluidUse-inspired numeric board features without a board
rendering. The four directions remain available in every version. The fork's
three-consecutive-no-effect-moves rule applies to all policies. Every v1 game
and 17 random games ended under that rule; all v2, v3, and v4 games ended when
no moves remained. Every final episode completed without a policy error.

The run used `scripts/run_full2048.py` with four worker processes to keep each
TextArena random-number generator independent. Paired seeds fix each game's
initial randomness but do not guarantee identical later tile spawns once
policies choose different moves. The 20 seeds are a pilot sample, not a
population estimate. V4's longer games also consumed more total input tokens
(6.42 million versus 3.11 million for v2 and 2.92 million for v3).

[`manifest.json`](manifest.json) records the protocol, source digest, model,
endpoint digest, seeds, and conditions. The per-policy JSON files contain final
episode results. [`episodes.jsonl`](episodes.jsonl) is the checkpoint and audit
trail: one v4 attempt on seed 117 stopped after an HTTP 529 response, then a
resume reran that seed from the beginning and completed. The table uses only
the successful final attempt recorded in `v4.json`.
