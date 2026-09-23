import io
import json
import os
import random
import unittest
from unittest.mock import patch

import textarena as ta
from textarena.decision_bench.prompts import _slide_board, v2_criteria, v2_observation
from textarena.decision_bench.runner import (
    GAME_ACTIONS,
    CurrentBoardObservationWrapper,
    RandomPolicy,
    run_benchmark,
)
from textarena.decision_bench.systemone import SystemOnePolicy


def environment(game):
    env = CurrentBoardObservationWrapper(ta.make(f"{game}-raw"))
    env.reset(num_players=1, seed=100)
    return env


class PromptVersionTests(unittest.TestCase):
    def test_2048_preview_matches_game_move_before_random_spawn(self):
        env = environment("2048-v0-super-easy")
        rng = random.Random(42)
        try:
            for _ in range(20):
                board = [
                    [rng.choice((0, 0, 2, 4, 8)) for _ in range(4)] for _ in range(4)
                ]
                for action in GAME_ACTIONS["2048-v0-super-easy"]:
                    after, merges = _slide_board(board, action)
                    env.state.game_state["board"] = [row[:] for row in board]
                    moved, gained = env._apply_move(env.ACTIONS[f"[{action}]"])
                    self.assertEqual(env.state.game_state["board"], after)
                    self.assertEqual(moved, after != board)
                    self.assertEqual(gained, sum(value * 2 for value in merges))
        finally:
            env.close()

    def test_2048_describes_merges_score_board_and_strikes_without_mutating(self):
        env = environment("2048-v0-super-easy")
        try:
            env.state.game_state["board"] = [
                [2, 2, 0, 0],
                [0, 0, 0, 0],
                [0, 0, 0, 0],
                [0, 0, 0, 0],
            ]
            before = [row[:] for row in env.state.game_state["board"]]
            criteria = v2_criteria(env, "2048-v0-super-easy", ("LEFT", "UP"))
            self.assertIn("2+2→4", criteria["LEFT"])
            self.assertIn("score 4 (+4)", criteria["LEFT"])
            self.assertIn("14 empty cells after one random tile", criteria["LEFT"])
            self.assertIn("Board before spawn: 4 . . .", criteria["LEFT"])
            self.assertEqual(env.state.game_state["board"], before)

            env.state.game_state["board"] = [[2, 0, 0, 0]] + [[0] * 4 for _ in range(3)]
            env.state.error_count = 2
            self.assertIn(
                "board unchanged; game ends",
                v2_criteria(env, "2048-v0-super-easy", ("LEFT",))["LEFT"],
            )
            self.assertIn(
                "2/3", v2_observation(env, "2048-v0-super-easy", "visible board")
            )
        finally:
            env.close()

    def test_sokoban_previews_blocked_moves_and_goal_pushes(self):
        env = environment("Sokoban-v0")
        try:
            criteria = v2_criteria(env, "Sokoban-v0", GAME_ACTIONS["Sokoban-v0"])
            self.assertIn("blocked by a wall", criteria["UP"])
            self.assertIn("push the box onto a goal", criteria["LEFT"])
            self.assertIn("1/3 boxes on goals afterward", criteria["LEFT"])
            self.assertIn(
                "Moves used: 0/30", v2_observation(env, "Sokoban-v0", "board")
            )
        finally:
            env.close()

    def test_blackjack_previews_do_not_depend_on_hidden_card(self):
        env = environment("Blackjack-v0")
        try:
            first = v2_criteria(env, "Blackjack-v0", ("HIT", "STAND"))
            self.assertIn("5/13 equally likely ranks bust", first["HIT"])
            self.assertIn("unknown hidden card", first["STAND"])
            env.state.game_state["dealer_hand"][1] = "A♠"
            second = v2_criteria(env, "Blackjack-v0", ("HIT", "STAND"))
            self.assertEqual(first, second)
        finally:
            env.close()

    def test_systemone_uses_v2_choice_descriptions(self):
        answer = io.BytesIO(
            json.dumps({"answers": {"action": {"choice": "LEFT"}}}).encode()
        )
        policy = SystemOnePolicy(
            name="test",
            endpoint="https://example.test/v1/systemone",
            model="model-x",
            api_key_env="TEST_DECISION_KEY",
        )
        with (
            patch.dict(os.environ, {"TEST_DECISION_KEY": "secret"}),
            patch("urllib.request.urlopen", return_value=answer) as urlopen,
        ):
            policy.decide(
                "visible board", ("LEFT", "RIGHT"), {"LEFT": "merge", "RIGHT": "slide"}
            )
        payload = json.loads(urlopen.call_args.args[0].data)
        self.assertEqual(
            payload["questions"]["action"]["criteria"],
            {"LEFT": "merge", "RIGHT": "slide"},
        )

    def test_v1_is_default_and_v2_does_not_change_random_gameplay(self):
        arguments = {"first_seed": 100, "episodes": 3, "max_decisions": 20}
        old = run_benchmark(
            ("2048-v0-super-easy", "Sokoban-v0", "Blackjack-v0"),
            RandomPolicy,
            **arguments,
        )
        new = run_benchmark(
            ("2048-v0-super-easy", "Sokoban-v0", "Blackjack-v0"),
            RandomPolicy,
            prompt_version="v2",
            **arguments,
        )
        self.assertEqual(old["prompt_version"], "v1")
        self.assertEqual(new["prompt_version"], "v2")
        for first, second in zip(old["results"], new["results"]):
            first.pop("mean_latency_ms")
            second.pop("mean_latency_ms")
            self.assertEqual(first, second)


if __name__ == "__main__":
    unittest.main()
