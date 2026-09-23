import io
import json
import os
import random
import unittest
import urllib.error
from unittest.mock import patch

import textarena as ta
from textarena.decision_bench.prompts import (
    _slide_board,
    v2_criteria,
    v2_observation,
    v3_criteria,
    v3_observation,
    v4_criteria,
    v4_observation,
)
from textarena.decision_bench.runner import (
    GAME_ACTIONS,
    CurrentBoardObservationWrapper,
    Decision,
    RandomPolicy,
    run_benchmark,
    run_episode,
)
from textarena.decision_bench.systemone import SystemOnePolicy


def environment(game):
    env = CurrentBoardObservationWrapper(ta.make(f"{game}-raw"))
    env.reset(num_players=1, seed=100)
    return env


class CapturePolicy:
    name = "capture"

    def decide(self, observation, actions, criteria=None):
        self.observation = observation
        self.criteria = criteria
        return Decision(actions[0])


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

    def test_systemone_retries_rate_limit_for_parallel_runs(self):
        answer = io.BytesIO(
            json.dumps({"answers": {"action": {"choice": "LEFT"}}}).encode()
        )
        limited = urllib.error.HTTPError(
            "https://example.test/v1/systemone",
            429,
            "rate limit",
            {"Retry-After": "0"},
            None,
        )
        policy = SystemOnePolicy(
            name="test",
            endpoint="https://example.test/v1/systemone",
            model="model-x",
            api_key_env="TEST_DECISION_KEY",
        )
        with (
            patch.dict(os.environ, {"TEST_DECISION_KEY": "secret"}),
            patch("urllib.request.urlopen", side_effect=[limited, answer]) as urlopen,
            patch("time.sleep") as sleep,
        ):
            decision = policy.decide("board", ("LEFT", "RIGHT"))
        self.assertEqual(decision.action, "LEFT")
        self.assertEqual(urlopen.call_count, 2)
        sleep.assert_called_once_with(0.0)

    def test_v3_2048_excludes_current_and_future_board_renderings(self):
        env = environment("2048-v0-super-easy")
        try:
            env.state.game_state["board"] = [[2, 2, 0, 0]] + [[0] * 4 for _ in range(3)]
            observation = v3_observation(env, "2048-v0-super-easy")
            criteria = v3_criteria(env, "2048-v0-super-easy", ("LEFT", "UP"))
            self.assertIn("2 tiles worth 2", observation)
            self.assertIn(
                "1 pair of tiles worth 2 merges into 1 tile worth 4", criteria["LEFT"]
            )
            self.assertNotIn("|", observation)
            self.assertNotIn("Board before spawn", str(criteria))
            self.assertNotIn(" / ", str(criteria))
            self.assertNotIn("row", observation + str(criteria))
        finally:
            env.close()

    def test_v3_runner_never_sends_a_grid_for_board_games(self):
        for game in ("2048-v0-super-easy", "Sokoban-v0"):
            with self.subTest(game=game):
                policy = CapturePolicy()
                run_episode(
                    game, policy, seed=100, max_decisions=1, prompt_version="v3"
                )
                request_text = policy.observation + str(policy.criteria)
                self.assertNotIn("Board before spawn", request_text)
                self.assertNotIn("Current Board:", request_text)
                self.assertNotIn("|", request_text)
                self.assertNotIn("# # #", request_text)
                self.assertEqual(set(policy.criteria), set(GAME_ACTIONS[game]))

    def test_v3_blackjack_spells_visible_cards_without_hidden_card(self):
        env = environment("Blackjack-v0")
        try:
            first = v3_observation(env, "Blackjack-v0")
            self.assertIn("four of clubs, nine of hearts", first)
            self.assertIn("King of clubs", first)
            self.assertNotIn("K♦", first)
            env.state.game_state["dealer_hand"][1] = "A♠"
            self.assertEqual(first, v3_observation(env, "Blackjack-v0"))
        finally:
            env.close()

    def test_v4_2048_uses_fluid_features_without_a_board(self):
        env = environment("2048-v0-super-easy")
        try:
            env.state.game_state["board"] = [[2, 8, 4, 0]] + [[0] * 4 for _ in range(3)]
            before = [row[:] for row in env.state.game_state["board"]]
            observation = v4_observation(env)
            criteria = v4_criteria(env, ("DOWN", "LEFT"))
            self.assertEqual(
                criteria["DOWN"],
                "swipe down: 13 empty cells, gain 0, largest tile away from a "
                "corner, monotonicity penalty 2, roughness 3",
            )
            self.assertIn("no board change, invalid attempt 1 of 3", criteria["LEFT"])
            self.assertIn(
                "Preserve empty cells, ordered high tiles, and merges", observation
            )
            self.assertNotIn("Current Board:", observation + str(criteria))
            self.assertNotIn("Board before spawn", observation + str(criteria))
            self.assertEqual(env.state.game_state["board"], before)
        finally:
            env.close()

    def test_v4_runner_sends_feature_labels_for_all_four_directions(self):
        policy = CapturePolicy()
        run_episode(
            "2048-v0-super-easy", policy, seed=100, max_decisions=1, prompt_version="v4"
        )
        self.assertEqual(set(policy.criteria), set(GAME_ACTIONS["2048-v0-super-easy"]))
        self.assertTrue(
            all(value.startswith("swipe ") for value in policy.criteria.values())
        )
        self.assertNotIn("Current Board:", policy.observation)
        with self.assertRaisesRegex(ValueError, "v4 is available only for 2048"):
            run_episode(
                "Sokoban-v0", policy, seed=100, max_decisions=1, prompt_version="v4"
            )

    def test_full_2048_can_run_without_a_decision_cap(self):
        result = run_episode(
            "2048-v0",
            RandomPolicy(100),
            seed=100,
            max_decisions=None,
            prompt_version="v4",
        )
        self.assertTrue(result["completed"])
        self.assertNotEqual(result["terminal_reason"], "decision_limit")
        self.assertLess(result["max_tile"], 2048)
        policy = CapturePolicy()
        run_episode("2048-v0", policy, seed=100, max_decisions=1, prompt_version="v4")
        self.assertIn("Reach a tile worth 2048", policy.observation)

    def test_prompt_versions_do_not_change_random_gameplay(self):
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
        verbal = run_benchmark(
            ("2048-v0-super-easy", "Sokoban-v0", "Blackjack-v0"),
            RandomPolicy,
            prompt_version="v3",
            **arguments,
        )
        fluid = run_benchmark(
            ("2048-v0-super-easy",),
            RandomPolicy,
            prompt_version="v4",
            **arguments,
        )
        self.assertEqual(old["prompt_version"], "v1")
        self.assertEqual(new["prompt_version"], "v2")
        self.assertEqual(verbal["prompt_version"], "v3")
        self.assertEqual(fluid["prompt_version"], "v4")
        for rows in (
            old["results"],
            new["results"],
            verbal["results"],
            fluid["results"],
        ):
            for row in rows:
                row.pop("mean_latency_ms")
        self.assertEqual(old["results"], new["results"])
        self.assertEqual(old["results"], verbal["results"])
        self.assertEqual(
            [row for row in old["results"] if row["game"].startswith("2048-")],
            fluid["results"],
        )


if __name__ == "__main__":
    unittest.main()
