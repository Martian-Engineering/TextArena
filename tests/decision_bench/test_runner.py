import io
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import textarena as ta
from textarena.decision_bench.runner import (
    CurrentBoardObservationWrapper,
    Decision,
    RandomPolicy,
    _ordered_actions,
    run_benchmark,
    run_episode,
)
from textarena.decision_bench.systemone import SystemOnePolicy


class InvalidChoicePolicy:
    name = "invalid-choice"

    def decide(self, observation, actions):
        return Decision("NOT_A_MOVE")


class ObservationPolicy:
    name = "observation-check"

    def decide(self, observation, actions):
        assert "Your goal is to reach a 128 tile" in observation
        assert "Score:" in observation
        assert "[GAME]" not in observation
        return Decision(actions[0])


class DecisionBenchTests(unittest.TestCase):
    def test_current_board_observation_excludes_player_action_history(self):
        env = CurrentBoardObservationWrapper(ta.make("2048-v0-super-easy-raw"))
        env.reset(num_players=1, seed=100)
        player_id, observation = env.get_observation()
        self.assertEqual(player_id, 0)
        self.assertIn("Score: 0", observation)
        env.state.add_observation(
            message="secret player action history",
            observation_type=ta.ObservationType.PLAYER_ACTION,
        )
        _, observation = env.get_observation()
        self.assertNotIn("secret player action history", observation)
        env.close()

    def test_invalid_policy_choice_does_not_reach_game(self):
        result = run_episode("2048-v0-super-easy", InvalidChoicePolicy(), seed=100)
        self.assertFalse(result["completed"])
        self.assertEqual(result["terminal_reason"], "invalid_policy_choice")
        self.assertEqual(result["game_score"], 0)

    def test_random_runs_are_reproducible_on_paired_seeds(self):
        def run():
            return run_benchmark(
                ("2048-v0-super-easy", "Sokoban-v0"),
                RandomPolicy,
                first_seed=100,
                episodes=2,
                max_decisions=10,
            )

        first, second = run(), run()
        for result in (*first["results"], *second["results"]):
            result.pop("mean_latency_ms")
        self.assertEqual(first, second)

    def test_action_order_changes_reproducibly_without_changing_choices(self):
        actions = ("UP", "DOWN", "LEFT", "RIGHT")
        orders = [
            _ordered_actions(actions, "2048-v0-super-easy", 100, turn)
            for turn in range(8)
        ]
        self.assertGreater(len(set(orders)), 1)
        self.assertTrue(all(set(order) == set(actions) for order in orders))
        self.assertEqual(
            orders,
            [
                _ordered_actions(actions, "2048-v0-super-easy", 100, turn)
                for turn in range(8)
            ],
        )

    def test_model_sees_only_wrapped_observation(self):
        result = run_episode(
            "2048-v0-super-easy", ObservationPolicy(), seed=100, max_decisions=1
        )
        self.assertEqual(result["terminal_reason"], "decision_limit")

    def test_blackjack_hides_dealers_second_card(self):
        env = CurrentBoardObservationWrapper(ta.make("Blackjack-v0-raw"))
        env.reset(num_players=1, seed=100)
        _, observation = env.get_observation()
        self.assertIn("Dealer shows: K♣", observation)
        self.assertNotIn("K♦", observation)
        env.close()

    def test_systemone_choice_request_uses_visible_text(self):
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
            decision = policy.decide("visible board", ("LEFT", "RIGHT"))
        self.assertEqual(decision.action, "LEFT")
        request = urlopen.call_args.args[0]
        payload = json.loads(request.data)
        self.assertEqual(payload["state"], {"observation": "visible board"})
        self.assertEqual(
            set(payload["questions"]["action"]["criteria"]), {"LEFT", "RIGHT"}
        )

    def test_cli_saves_policy_failures_and_exits_nonzero(self):
        from textarena.decision_bench.__main__ import main

        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "result.json"
            failed = {
                "results": [{"terminal_reason": "invalid_policy_choice"}],
            }
            with (
                patch.object(sys, "argv", ["decision-bench", "--output", str(output)]),
                patch(
                    "textarena.decision_bench.__main__.run_benchmark",
                    return_value=failed,
                ),
                self.assertRaises(SystemExit) as exit_status,
            ):
                main()
            self.assertEqual(exit_status.exception.code, 1)
            self.assertTrue(output.exists())

    def test_unsupported_game_fails_before_loading(self):
        with patch("textarena.decision_bench.runner.ta.make") as make:
            with self.assertRaises(ValueError):
                run_episode("Chess-v0", RandomPolicy(1), seed=1)
            make.assert_not_called()


if __name__ == "__main__":
    unittest.main()
