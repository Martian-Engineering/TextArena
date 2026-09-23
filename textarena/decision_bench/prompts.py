"""Action previews derived from information available to the current player."""

from __future__ import annotations

from collections import Counter

PROMPT_VERSIONS = ("v1", "v2")
_DIRECTIONS = {"UP": (-1, 0), "DOWN": (1, 0), "LEFT": (0, -1), "RIGHT": (0, 1)}


def v2_observation(env, game_id: str, observation: str) -> str:
    if game_id.startswith("2048-"):
        return f"{observation}\n\nConsecutive no-effect/invalid moves: {env.state.error_count}/3."
    if game_id == "Sokoban-v0":
        return f"{observation}\n\nMoves used: {env.state.turn}/{env.max_turns}."
    results = env.state.game_state["results_summary"]
    return (
        f"{observation}\n\nPrevious hands: {results['win']} wins, "
        f"{results['lose']} losses, {results['draw']} draws."
    )


def v2_criteria(env, game_id: str, actions: tuple[str, ...]) -> dict[str, str]:
    if game_id.startswith("2048-"):
        return {action: _preview_2048(env, action) for action in actions}
    if game_id == "Sokoban-v0":
        return {action: _preview_sokoban(env, action) for action in actions}
    return {action: _preview_blackjack(env, action) for action in actions}


def _slide_line(line: list[int]) -> tuple[list[int], list[int]]:
    tiles = [value for value in line if value]
    output = []
    merges = []
    index = 0
    while index < len(tiles):
        if index + 1 < len(tiles) and tiles[index] == tiles[index + 1]:
            merges.append(tiles[index])
            output.append(tiles[index] * 2)
            index += 2
        else:
            output.append(tiles[index])
            index += 1
    return output + [0] * (len(line) - len(output)), merges


def _slide_board(
    board: list[list[int]], action: str
) -> tuple[list[list[int]], list[int]]:
    size = len(board)
    after = [row[:] for row in board]
    merges = []
    for offset in range(size):
        if action == "LEFT":
            cells = [(offset, col) for col in range(size)]
        elif action == "RIGHT":
            cells = [(offset, col) for col in reversed(range(size))]
        elif action == "UP":
            cells = [(row, offset) for row in range(size)]
        else:
            cells = [(row, offset) for row in reversed(range(size))]
        line, line_merges = _slide_line([board[row][col] for row, col in cells])
        merges.extend(line_merges)
        for (row, col), value in zip(cells, line):
            after[row][col] = value
    return after, merges


def _preview_2048(env, action: str) -> str:
    board = env.state.game_state["board"]
    after, merges = _slide_board(board, action)
    if after == board:
        strike = env.state.error_count + 1
        outcome = "game ends" if strike == 3 else f"invalid streak becomes {strike}/3"
        return f"Slide {action.lower()}: board unchanged; {outcome}."

    gain = sum(value * 2 for value in merges)
    score = env.state.game_state["score"] + gain
    open_before_spawn = sum(value == 0 for row in after for value in row)
    open_after_spawn = max(0, open_before_spawn - 1)
    counts = Counter(merges)
    merge_text = (
        ", ".join(
            f"{count}× {value}+{value}→{value * 2}"
            if count > 1
            else f"{value}+{value}→{value * 2}"
            for value, count in sorted(counts.items())
        )
        if merges
        else "no merges"
    )
    max_tile = max(map(max, after))
    target = "; target reached" if max_tile >= env.target_tile else ""
    compact_board = " / ".join(
        " ".join(str(value) if value else "." for value in row) for row in after
    )
    return (
        f"Slide {action.lower()}: {merge_text}; score {score} (+{gain}); "
        f"largest tile {max_tile}{target}; {open_after_spawn} empty cells after one random "
        f"tile spawns (2: 90%, 4: 10%). Board before spawn: {compact_board}."
    )


def _preview_sokoban(env, action: str) -> str:
    board = env.room_state
    row, col = map(int, env.player_position)
    dr, dc = _DIRECTIONS[action]
    next_row, next_col = row + dr, col + dc
    prefix = f"Move {action.lower()}: "

    def in_bounds(r: int, c: int) -> bool:
        return 0 <= r < board.shape[0] and 0 <= c < board.shape[1]

    if not in_bounds(next_row, next_col) or board[next_row, next_col] == 0:
        return prefix + "blocked by a wall; position unchanged."
    next_cell = board[next_row, next_col]
    goals = int((board == 3).sum())
    if next_cell in (3, 4):
        box_row, box_col = next_row + dr, next_col + dc
        if not in_bounds(box_row, box_col) or board[box_row, box_col] not in (1, 2):
            return prefix + "box cannot be pushed into the occupied space or wall."
        goals += int(board[box_row, box_col] == 2) - int(next_cell == 3)
        origin = "off a goal " if next_cell == 3 else ""
        destination = "onto a goal" if board[box_row, box_col] == 2 else "onto floor"
        return (
            prefix + f"push the box {origin}{destination} at row {box_row + 1}, "
            f"column {box_col + 1}; {goals}/{env.num_boxes} boxes on goals afterward."
        )
    destination = "goal" if next_cell == 2 else "floor"
    return (
        prefix
        + f"walk onto {destination} at row {next_row + 1}, column {next_col + 1}; "
        f"{goals}/{env.num_boxes} boxes on goals afterward."
    )


def _preview_blackjack(env, action: str) -> str:
    hand = env.state.game_state["player_hand"]
    total = env._hand_score(hand)
    if action == "STAND":
        return (
            f"Stand on {total}: draw no more cards. Dealer resolves from the visible "
            "upcard and an unknown hidden card, drawing until at least 17."
        )
    scores = {rank: env._hand_score([*hand, f"{rank}♠"]) for rank in env.ranks}
    busts = [rank for rank, score in scores.items() if score > 21]
    safe = sorted({score for score in scores.values() if score <= 21})
    safe_text = f"{safe[0]}–{safe[-1]}" if safe else "none"
    bust_text = ", ".join(busts) if busts else "none"
    return (
        f"Hit on {total}: draw one random card. {len(busts)}/13 equally likely ranks "
        f"bust ({bust_text}); non-bust totals range {safe_text}."
    )
