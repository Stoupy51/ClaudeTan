
# ClaudeTan

A voice assistant with an anime overlay (PySide6), driving a hidden Claude Code session. `README.md` says how to run it, `PLAN.md` what is done and planned.

## Layout

- `src/claudetan/app.py`: the Qt app and `Assistant`, which turns hook events and heard requests into what Claude-tan shows.
- `src/claudetan/session.py`: the hidden `claude` process in a pseudo-terminal, and the hook server.
- `src/claudetan/actions.py`: `ACTIONS`, what she does on the computer. `mcp.py` offers the same list to the session as tools.
- `src/claudetan/voice/`: microphone, Whisper, wake and end phrases, meeting transcription. `overlay/`: avatar, bubble, tray.
- `tools/sprites/`: a separate uv project that draws `assets/claude/`. Leave it alone unless asked about sprites.

## Adding an action

1. Add one `Action(...)` to `ACTIONS` in `actions.py`, with `name`, `description` (what the session reads to choose the tool), `phrases` (a regex matched against the whole request, its named groups being the arguments), `run` (returns what she says) and `parameters` when it takes arguments.
2. The same entry is then a voice phrase and the MCP tool `mcp__claudetan__<name>`. Never list an action anywhere else.
3. Add a `>>>` example to `route` or a test in `tests/` for the behaviour that could break. Mock only I/O (network, key presses), as `tests/test_discord.py` does.
4. Add a row to the table in `README.md`.

Actions run on the Qt thread: keep them quick, and start a thread for anything long, as `meeting.py` does. An effect on the session itself (typing `/model`, restarting it) goes in `Assistant.run_action`, not in the action.

## Checks

All must pass before you report: `uv run ruff check`, `uv run pyright`, `uv run pytest --doctest-modules src tests`, `uv run stouputils check`, `uvx complexipy src --failed --max-complexity-allowed 15`.

Code style: tabs, pyright strict, a `.py` file ends with two newlines, no comments that restate the code. Never write long dashes, arrows, curly quotes or an ellipsis character.

Do not commit or push: suggest a short conventional commit message with a gitmoji, and the user commits.

