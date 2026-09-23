"""Action previews derived from information available to the current player."""

from __future__ import annotations

from collections import Counter
from itertools import pairwise

PROMPT_VERSIONS = ("v1", "v2", "v3", "v4")
_DIRECTIONS = {"UP": (-1, 0), "DOWN": (1, 0), "LEFT": (0, -1), "RIGHT": (0, 1)}
_RANK_NAMES = {
    "2": "two",
    "3": "three",
    "4": "four",
    "5": "five",
    "6": "six",
    "7": "seven",
    "8": "eight",
    "9": "nine",
    "10": "ten",
    "J": "Jack",
    "Q": "Queen",
    "K": "King",
    "A": "Ace",
}
_SUIT_NAMES = {"♠": "spades", "♥": "hearts", "♦": "diamonds", "♣": "clubs"}


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


def v3_observation(env, game_id: str) -> str:
    """Describe visible game information without including a board rendering."""
    if game_id.startswith("2048-"):
        board = env.state.game_state["board"]
        tiles = Counter(value for row in board for value in row if value)
        tile_text = ", ".join(
            f"{count} tile{'s' if count != 1 else ''} worth {value}"
            for value, count in sorted(tiles.items())
        )
        empty = sum(value == 0 for row in board for value in row)
        return (
            f"You are playing 2048 on a {env.board_size} by {env.board_size} grid. "
            f"Reach a tile worth {env.target_tile} by sliding up, down, left, or right. "
            "Equal tiles merge. A successful slide then spawns one random tile. "
            "The third consecutive invalid or no-effect move ends the game. "
            f"Current score: {env.state.game_state['score']}. Largest tile: {max(tiles)}. "
            f"Empty spaces: {empty}. Tiles: {tile_text}. "
            f"Consecutive invalid or no-effect moves: {env.state.error_count}/3."
        )
    if game_id == "Sokoban-v0":
        row, col = map(int, env.player_position)
        goals = int((env.room_state == 3).sum())
        return (
            "You are solving Sokoban. Push all boxes onto goals by moving up, "
            "down, left, or right. Walls and other boxes block pushes; boxes "
            "cannot be pulled. "
            f"Player position: row {row + 1}, column {col + 1}. "
            f"Boxes on goals: {goals}/{env.num_boxes}. "
            f"Moves used: {env.state.turn}/{env.max_turns}."
        )
    state = env.state.game_state
    results = state["results_summary"]
    hand = ", ".join(_card_name(card) for card in state["player_hand"])
    dealer_upcard = _card_name(state["dealer_hand"][0])
    return (
        "You are playing Blackjack against the dealer. Get as close to 21 as "
        "possible without going over. Hit draws a card; stand keeps your total. "
        "The dealer draws until reaching at least 17. "
        f"Hand {state['hand_number']} of {state['num_hands']}. "
        f"Your cards: {hand}. Your total: {env._hand_score(state['player_hand'])}. "
        f"Dealer's visible card: {dealer_upcard}. The other card is hidden. "
        f"Previous hands: {results['win']} wins, {results['lose']} losses, "
        f"{results['draw']} draws."
    )


def v3_criteria(env, game_id: str, actions: tuple[str, ...]) -> dict[str, str]:
    if game_id.startswith("2048-"):
        return {
            action: _preview_2048(env, action, include_board=False)
            for action in actions
        }
    if game_id == "Sokoban-v0":
        return {action: _preview_sokoban(env, action) for action in actions}
    return {
        action: _preview_blackjack(env, action, verbal_ranks=True) for action in actions
    }


def v4_observation(env) -> str:
    """Port the Fluid demo's fixed task text without sending tile positions."""
    return (
        "Build the largest tile without filling the board. "
        "Choose the safest 2048 swipe. Preserve empty cells, ordered high tiles, "
        f"and merges. Reach a tile worth {env.target_tile}."
    )


def v4_criteria(env, actions: tuple[str, ...]) -> dict[str, str]:
    board = env.state.game_state["board"]
    result = {}
    for action in actions:
        after, merges = _slide_board(board, action)
        if after == board:
            strike = env.state.error_count + 1
            result[action] = (
                f"swipe {action.lower()}: no board change, invalid attempt {strike} of 3"
            )
            continue
        maximum = max(map(max, after))
        corners = (after[0][0], after[0][-1], after[-1][0], after[-1][-1])
        location = (
            "largest tile in a corner"
            if maximum in corners
            else "largest tile away from a corner"
        )
        empty = sum(value == 0 for row in after for value in row)
        gain = sum(value * 2 for value in merges)
        monotonicity = sum(_line_monotonicity_penalty(row) for row in after)
        monotonicity += sum(
            _line_monotonicity_penalty([row[col] for row in after])
            for col in range(len(after))
        )
        roughness = 0
        for row in range(len(after)):
            for col in range(len(after[row])):
                value = after[row][col]
                if not value:
                    continue
                if col + 1 < len(after[row]) and after[row][col + 1]:
                    roughness += abs(
                        _tile_exponent(value) - _tile_exponent(after[row][col + 1])
                    )
                if row + 1 < len(after) and after[row + 1][col]:
                    roughness += abs(
                        _tile_exponent(value) - _tile_exponent(after[row + 1][col])
                    )
        result[action] = (
            f"swipe {action.lower()}: {empty} empty cells, gain {gain}, "
            f"{location}, monotonicity penalty {monotonicity}, roughness {roughness}"
        )
    return result


def _tile_exponent(value: int) -> int:
    return value.bit_length() - 1 if value else 0


def _line_monotonicity_penalty(line: list[int]) -> int:
    exponents = [_tile_exponent(value) for value in line]
    increasing = sum(max(0, left - right) for left, right in pairwise(exponents))
    decreasing = sum(max(0, right - left) for left, right in pairwise(exponents))
    return min(increasing, decreasing)


def _card_name(card: str) -> str:
    return f"{_RANK_NAMES[card[:-1]]} of {_SUIT_NAMES[card[-1]]}"


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


def _preview_2048(env, action: str, *, include_board: bool = True) -> str:
    board = env.state.game_state["board"]
    after, merges = _slide_board(board, action)
    if after == board:
        strike = env.state.error_count + 1
        if not include_board:
            consequence = (
                "The game would end."
                if strike == 3
                else f"This would be invalid attempt {strike} of 3."
            )
            return f"Sliding {action.lower()} has no effect. {consequence}"
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
    if not include_board:
        merge_prose = (
            ", ".join(
                f"{count} pair{'s' if count != 1 else ''} of tiles worth {value} "
                f"{'merge' if count != 1 else 'merges'} into "
                f"{count} tile{'s' if count != 1 else ''} worth {value * 2}"
                for value, count in sorted(counts.items())
            )
            if merges
            else "no tiles merge"
        )
        target_prose = (
            f" This reaches the {env.target_tile} target."
            if max_tile >= env.target_tile
            else ""
        )
        return (
            f"Sliding {action.lower()}: {merge_prose}. The score would be {score}, "
            f"gaining {gain} points. The largest tile would be {max_tile}. "
            f"After a random tile appears, {open_after_spawn} spaces would remain empty. "
            f"The new tile is worth 2 with 90 percent probability or 4 with 10 percent probability."
            f"{target_prose}"
        )
    description = (
        f"Slide {action.lower()}: {merge_text}; score {score} (+{gain}); "
        f"largest tile {max_tile}{target}; {open_after_spawn} empty cells after one random "
        "tile spawns (2: 90%, 4: 10%)."
    )
    compact_board = " / ".join(
        " ".join(str(value) if value else "." for value in row) for row in after
    )
    return f"{description} Board before spawn: {compact_board}."


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


def _preview_blackjack(env, action: str, *, verbal_ranks: bool = False) -> str:
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
    bust_text = (
        ", ".join(_RANK_NAMES[rank] if verbal_ranks else rank for rank in busts)
        if busts
        else "none"
    )
    if verbal_ranks:
        return (
            f"Hitting on {total} draws one random card. {len(busts)} of 13 equally likely "
            f"ranks would bust: {bust_text}. Otherwise, the total would be from "
            f"{safe[0]} to {safe[-1]}."
            if safe
            else f"Hitting on {total} draws one random card, and every rank would bust."
        )
    return (
        f"Hit on {total}: draw one random card. {len(busts)}/13 equally likely ranks "
        f"bust ({bust_text}); non-bust totals range {safe_text}."
    )
