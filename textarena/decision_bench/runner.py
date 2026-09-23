"""A small, reproducible decision-model track over unmodified TextArena games."""

from __future__ import annotations

import hashlib
import random
import statistics
import time
from dataclasses import dataclass
from typing import Protocol

import textarena as ta

from .prompts import (
    PROMPT_VERSIONS,
    v2_criteria,
    v2_observation,
    v3_criteria,
    v3_observation,
    v4_criteria,
    v4_observation,
)

PROTOCOL_VERSION = "0.6.0"
GAME_ACTIONS = {
    "2048-v0-super-easy": ("UP", "DOWN", "LEFT", "RIGHT"),
    "2048-v0": ("UP", "DOWN", "LEFT", "RIGHT"),
    "Sokoban-v0": ("UP", "DOWN", "LEFT", "RIGHT"),
    "Blackjack-v0": ("HIT", "STAND"),
}


class CurrentBoardObservationWrapper(ta.ObservationWrapper):
    """Show game instructions and the latest player-visible state message."""

    def __init__(self, env):
        super().__init__(env)
        self._prompt = None
        self._board = None

    def observation(self, player_id, observation):
        for _, message, kind in observation:
            if kind == ta.ObservationType.PROMPT:
                self._prompt = message
            elif kind in (
                ta.ObservationType.GAME_BOARD,
                ta.ObservationType.GAME_MESSAGE,
            ):
                self._board = message
        if self._prompt is None or self._board is None:
            raise RuntimeError("missing prompt or current game state")
        return f"{self._prompt}\n\n{self._board}"


@dataclass(frozen=True)
class Decision:
    action: str
    input_tokens: int = 0
    output_tokens: int = 0


class Policy(Protocol):
    name: str

    def decide(
        self,
        observation: str,
        actions: tuple[str, ...],
        criteria: dict[str, str] | None = None,
    ) -> Decision: ...

    def metadata(self) -> dict: ...


class RandomPolicy:
    name = "random"

    def __init__(self, seed: int):
        self._rng = random.Random(seed)

    def decide(
        self,
        observation: str,
        actions: tuple[str, ...],
        criteria: dict[str, str] | None = None,
    ) -> Decision:
        return Decision(self._rng.choice(actions))

    def metadata(self) -> dict:
        return {"kind": "random_baseline"}


def run_episode(
    game_id: str,
    policy: Policy,
    *,
    seed: int,
    max_decisions: int | None = 500,
    prompt_version: str = "v1",
) -> dict:
    """Use only the observation returned to the current player by TextArena."""
    if game_id not in GAME_ACTIONS:
        raise ValueError(f"unsupported decision-bench game: {game_id}")
    if max_decisions is not None and max_decisions < 1:
        raise ValueError("max_decisions must be positive")
    if prompt_version not in PROMPT_VERSIONS:
        raise ValueError(f"unsupported prompt version: {prompt_version}")
    if prompt_version == "v4" and not game_id.startswith("2048-"):
        raise ValueError("v4 is available only for 2048")

    env = CurrentBoardObservationWrapper(ta.make(f"{game_id}-raw"))
    env.reset(num_players=1, seed=seed)
    actions = GAME_ACTIONS[game_id]
    latencies = []
    usage = {"input_tokens": 0, "output_tokens": 0}
    terminal_reason = None
    done = False
    closed = False
    try:
        while not done and (max_decisions is None or len(latencies) < max_decisions):
            player_id, observation = env.get_observation()
            if player_id != 0 or not isinstance(observation, str):
                raise RuntimeError("expected a single-player text observation")
            presented_actions = _ordered_actions(actions, game_id, seed, len(latencies))
            if prompt_version == "v2":
                observation = v2_observation(env, game_id, observation)
                criteria = v2_criteria(env, game_id, presented_actions)
            elif prompt_version == "v3":
                observation = v3_observation(env, game_id)
                criteria = v3_criteria(env, game_id, presented_actions)
            elif prompt_version == "v4":
                observation = v4_observation(env)
                criteria = v4_criteria(env, presented_actions)
            started = time.perf_counter()
            try:
                if prompt_version != "v1":
                    decision = policy.decide(observation, presented_actions, criteria)
                else:
                    decision = policy.decide(observation, presented_actions)
            except Exception as error:  # noqa: BLE001 - policy failures are episode results
                latencies.append((time.perf_counter() - started) * 1000)
                terminal_reason = f"policy_error: {type(error).__name__}: {error}"
                break
            latencies.append((time.perf_counter() - started) * 1000)
            if decision.action not in presented_actions:
                terminal_reason = "invalid_policy_choice"
                break
            usage["input_tokens"] += decision.input_tokens
            usage["output_tokens"] += decision.output_tokens
            done, _ = env.step(f"[{decision.action}]")

        if not done and terminal_reason is None:
            terminal_reason = "decision_limit"
        rewards, game_info = env.close()
        closed = True
        reward = rewards.get(0) if rewards is not None else None
        invalid_move = bool(game_info[0].get("invalid_move", False))
        if game_id.startswith("2048-"):
            board = env.state.game_state["board"]
            max_tile = max(map(max, board))
            metrics = {
                "game_score": env.state.game_state["score"],
                "max_tile": max_tile,
            }
            success = done and not invalid_move and max_tile >= env.target_tile
        elif game_id == "Sokoban-v0":
            boxes_on_goals, all_boxes_on_goals = env._check_if_all_boxes_on_target()
            metrics = {"boxes_on_goals": boxes_on_goals, "total_boxes": env.num_boxes}
            success = done and not invalid_move and all_boxes_on_goals
        else:
            metrics = dict(env.state.game_state["results_summary"])
            success = None

        return {
            "game": game_id,
            "policy": policy.name,
            "seed": seed,
            "completed": done,
            "success": success,
            "reward": reward,
            "invalid_move": invalid_move,
            "terminal_reason": terminal_reason or game_info[0].get("reason"),
            "decisions": len(latencies),
            "mean_latency_ms": round(statistics.fmean(latencies), 3)
            if latencies
            else None,
            **usage,
            **metrics,
        }
    finally:
        if not closed:
            env.close()


def _ordered_actions(
    actions: tuple[str, ...], game_id: str, seed: int, turn: int
) -> tuple[str, ...]:
    order_seed = int.from_bytes(
        hashlib.sha256(f"{game_id}:{seed}:{turn}".encode()).digest()[:8], "big"
    )
    ordered = list(actions)
    random.Random(order_seed).shuffle(ordered)
    return tuple(ordered)


def run_benchmark(
    game_ids: tuple[str, ...],
    policy_factory,
    *,
    first_seed: int,
    episodes: int,
    max_decisions: int | None = 500,
    prompt_version: str = "v1",
) -> dict:
    if episodes < 1:
        raise ValueError("episodes must be positive")
    if not game_ids:
        raise ValueError("at least one game is required")
    if prompt_version not in PROMPT_VERSIONS:
        raise ValueError(f"unsupported prompt version: {prompt_version}")
    results = []
    policy_metadata = None
    for game_id in game_ids:
        for seed in range(first_seed, first_seed + episodes):
            policy = policy_factory(seed)
            if policy_metadata is None:
                policy_metadata = policy.metadata()
            results.append(
                run_episode(
                    game_id,
                    policy,
                    seed=seed,
                    max_decisions=max_decisions,
                    prompt_version=prompt_version,
                )
            )
    return {
        "protocol_version": PROTOCOL_VERSION,
        "prompt_version": prompt_version,
        "textarena_version": ta.__version__,
        "policy_metadata": policy_metadata,
        "first_seed": first_seed,
        "episodes_per_game": episodes,
        "max_decisions": max_decisions,
        "results": results,
    }
