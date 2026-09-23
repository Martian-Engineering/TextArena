# 2048: Jev v1 versus v2 prompts

Run on September 23, 2026 using the Martian Engineering TextArena fork at commit
`76b218a7`, decision-bench protocol `0.3.0`, and the three-strike 2048 rule.
Each policy played `2048-v0-super-easy` (target tile 128) on seeds 100–119 with a
500-decision cap. Jev used model `jev-1.13.0` through the TypeSafe System One
choice API. V1 used the original short action labels. V2 described each move's
deterministic slide, merges, score, and board before the random tile spawn, and
showed the current invalid-move streak. Random ignored the prompt wording.

| Policy | Wins | Invalid-move endings | Mean score | Mean decisions |
| --- | ---: | ---: | ---: | ---: |
| [Jev v2](textarena-jev-2048-v2-seed100-20.json) | **20/20** | 0/20 | **939.4** | 90.5 |
| [Jev v1](textarena-jev-2048-v1-three-strikes-seed100-20.json) | 0/20 | 20/20 | 13.8 | 8.9 |
| [Random](textarena-random-2048-v2-seed100-20.json) | 2/20 | 16/20 | 421.2 | 63.2 |

V2 scored higher than v1 on all 20 paired seeds, by 925.6 points on average.
A 20,000-resample paired bootstrap gives a 95% interval of 873.0–982.8 points
for that score difference. V2 scored higher than random on 18/20 seeds, by
518.2 points on average (paired bootstrap 95% interval 374.2–656.6).
Wilson 95% intervals for win rates are 83.9–100% for v2, 0–16.1% for v1, and
2.8–30.1% for random.

All 40 Jev episodes completed with zero API or policy errors. V2 made 1,811
decisions, using 1,411,759 input and 81,495 output tokens; v1 made 178
decisions, using 82,943 input and 8,010 output tokens. V2's richer prompts and
longer games therefore used substantially more tokens. The runner records
outcomes rather than each chosen action, so this run does not establish which
specific v2 preview changed Jev's decisions. Paired seeds fix initial
conditions, but later random tile spawns can diverge after policies choose
different moves. The 20-seed result is strong for this target tile and prompt,
but does not establish performance on harder 2048 variants.
