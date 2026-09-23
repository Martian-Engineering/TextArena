import unittest

from textarena.envs.Game2048.env import Game2048Env


class Game2048InvalidStreakTests(unittest.TestCase):
    def setUp(self):
        self.env = Game2048Env(target_tile=128)
        self.env.reset(num_players=1, seed=100)
        self.env.state.game_state["board"] = [
            [2, 0, 0, 0],
            [0, 0, 0, 0],
            [0, 0, 0, 0],
            [0, 0, 0, 0],
        ]

    def test_third_consecutive_no_effect_move_ends_game(self):
        for expected_count in (1, 2):
            done, _ = self.env.step("[Left]")
            self.assertFalse(done)
            self.assertEqual(self.env.state.error_count, expected_count)

        done, _ = self.env.step("[Left]")
        self.assertTrue(done)
        self.assertTrue(self.env.state.game_info[0]["invalid_move"])

    def test_valid_move_resets_streak(self):
        self.env.step("[Left]")
        self.env.step("[Left]")
        done, _ = self.env.step("[Right]")
        self.assertFalse(done)
        self.assertEqual(self.env.state.error_count, 0)

        for expected_count in (1, 2):
            done, _ = self.env.step("invalid")
            self.assertFalse(done)
            self.assertEqual(self.env.state.error_count, expected_count)

        done, _ = self.env.step("invalid")
        self.assertTrue(done)
        self.assertTrue(self.env.state.game_info[0]["invalid_move"])


if __name__ == "__main__":
    unittest.main()
