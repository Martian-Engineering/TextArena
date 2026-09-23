# Verbal-only 2048 prompt pilot

This pilot compares Jev's v3 prompt with the earlier v1/v2 results and a seeded
random policy. All runs use `2048-v0-super-easy`, seeds 100–119, a 128-tile
target, a 500-decision cap, and the fork's three-consecutive-invalid-move rule.
Jev uses `jev-1.13.0` through TypeSafe System One. V3 describes the current
score, tile counts, empty cells, and each action's deterministic merge and score
outcome in words. It never sends tile positions or a board rendering. The
random tile's position remains unknown in every prompt version.

| Policy and prompt | Reached 128 | Mean game score | Decisions | Invalid moves | Input tokens |
| --- | ---: | ---: | ---: | ---: | ---: |
| Jev v1 | 0/20 | 13.8 | 178 | 20 | 82,943 |
| Jev v2 | 20/20 | 939.4 | 1,811 | 0 | 1,411,759 |
| Jev v3 | 17/20 | 950.8 | 1,892 | 0 | 1,415,794 |
| Random v3 | 2/20 | 421.2 | 1,264 | 16 | — |

Jev v3 lost seeds 100, 106, and 109 when no moves remained; all three ended
with a 64 tile. It made no invalid moves. Its mean score was slightly higher
than v2's despite winning fewer games, so score is not a substitute for target
success. With only 20 paired seeds, the 17/20 versus 20/20 difference is a
pilot observation, not a precise estimate of the prompt effect. V3 still gives
Jev a deterministic verbal preview for every action, so this does not measure
performance from a bare verbal status alone.

Raw [Jev v3](jev-v3.json) and [random v3](random-v3.json) episode data are
included here. The [v1/v2 comparison](../2048-v1-v2-seed100-20/README.md)
contains the earlier raw data and its run settings. The v3 random run has the
same game outcomes as v2 random on these seeds, as expected because prompt
formatting does not affect a random policy.
