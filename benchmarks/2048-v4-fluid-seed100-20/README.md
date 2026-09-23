# Fluid-style 2048 feature prompt pilot

This pilot adapts the candidate labels in FluidUse's [Game2048 engine](https://github.com/FluidInference/FluidUse/blob/e0d4215ae395a877e9d11bbb75bb26413137ab05/Sources/Game2048/Game2048.swift) and the goal text in its [GLiClass demo](https://github.com/FluidInference/FluidUse/blob/e0d4215ae395a877e9d11bbb75bb26413137ab05/Sources/GLiClass2048Demo/Game2048Model.swift) for Jev's fixed-choice API. V4 shows no grid. For each swipe, it describes the resulting empty-cell count, score gain, whether the largest tile is in a corner, a monotonicity penalty, and adjacent-tile roughness. A no-effect swipe is labeled invalid.

The experiment isolates the feature-label prompt: all four directions remain available, and Jev makes the final choice. FluidUse's demo also uses a one-move expectimax heuristic to shortlist the top two legal moves by default and a confidence-margin fallback to the heuristic leader. Those policy steps are outside this v4 test.

All rows below use TextArena `2048-v0-super-easy`, seeds 100–119, a 128-tile target, a 500-decision cap, and the three-consecutive-invalid-move rule. Jev uses `jev-1.13.0` through TypeSafe System One.

| Policy and prompt | Reached 128 | Mean score at stop | Decisions | Invalid moves | Input tokens |
| --- | ---: | ---: | ---: | ---: | ---: |
| Jev v2, full board and move previews | 20/20 | 939.4 | 1,811 | 0 | 1,411,759 |
| Jev v3, verbal move previews | 17/20 | 950.8 | 1,892 | 0 | 1,415,794 |
| **Jev v4, Fluid-style features** | **20/20** | **847.0** | **1,540** | **0** | **771,132** |
| Random v4 | 2/20 | 421.2 | 1,264 | 16 | — |

V4 tied v2's 20/20 success rate and used 271 fewer decisions (15.0%) and 640,627 fewer input tokens (45.4%) across the paired runs. V4 required fewer decisions on 16 seeds, the same number on one, and more on three. The lower mean score at stop is consistent with reaching the 128 target in fewer moves; both policies stop immediately at that target. This 20-seed pilot does not establish performance at larger targets or isolate which of the five features helps most.

Raw [Jev v4](jev-v4.json) and [random v4](random-v4.json) episodes are included here. Earlier [v1/v2](../2048-v1-v2-seed100-20/README.md) and [v3](../2048-v3-seed100-20/README.md) runs provide the paired comparison data. The random v4 outcomes match the earlier random outcomes on every seed, confirming that prompt formatting does not change random gameplay.
