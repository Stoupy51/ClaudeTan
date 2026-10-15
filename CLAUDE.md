
# ClaudeTan

A voice assistant with an anime overlay (PySide6), driving a hidden Claude Code session. `README.md` says how to run it, `PLAN.md` what is done and planned.

## Layout

- `src/claudetan/app.py`: the Qt app and `Assistant`, which turns hook events and heard requests into what Claude-tan shows.
- `src/claudetan/session.py`: the hidden `claude` process in a pseudo-terminal, and the hook server.
- `src/claudetan/reload.py`: applies the hidden session's changes to the code once it has nothing running. `actions.py` and `services/` reload in place, a change reaching a module of `LIVE` restarts the app.
- `src/claudetan/launcher.py`: runs the app, starts it again after such a change, and puts the change aside in git when the app then fails to start. It imports nothing of the app.
- `src/claudetan/actions.py`: `ACTIONS`, what she does on the computer. `mcp.py` offers the same list to the session as tools.
- `src/claudetan/services/`: what the actions call (weather, programs, timers, other applications' windows in `desktop.py`). Put the code of a new action there when it is more than a few lines.
- `src/claudetan/voice/`: microphone, Whisper, wake and end phrases, meeting transcription, and her Japanese voice (`voicevox.py`). `overlay/`: avatar, bubble, tray.
- `tools/sprites/`: a separate uv project that draws `assets/claude/`. Leave it alone unless asked about sprites.

## Adding an action

1. Add one `Action(...)` to `ACTIONS` in `actions.py`, with `name`, `description` (what the session reads to choose the tool), `phrases` (a regex matched against the whole request, its named groups being the arguments), `run` (returns what she says, as `tr(english, french)` from `i18n.py`) and `parameters` when it takes arguments.
2. The same entry is then a voice phrase and the MCP tool `mcp__claudetan__<name>`. Never list an action anywhere else.
3. Add a `>>>` example to `route` or a test in `tests/` for the behaviour that could break. Mock only I/O (network, key presses), as `tests/test_services.py` does.
4. Add a row to the table in `README.md`.

Actions run on the Qt thread: keep them quick, and start a thread for anything long, as `meeting.py` does, or set `threaded=True` on a tool that answers after seconds. An effect on the session itself (typing `/model`, restarting it) goes in `Assistant.run_action`, not in the action.

Keep what must outlive a reload, such as timers, in a module of `LIVE`, as `ALARMS` is. A module of `LIVE` reaches the actions through the module (`actions.route`): taking names from it with `from ... import` would make every change to an action restart the app.

## Checks

All must pass before you report: `uv run ruff check`, `uv run pyright`, `uv run pytest --doctest-modules src tests`, `uv run stouputils check`, `uvx complexipy src --failed --max-complexity-allowed 15`.

Code style: tabs, pyright strict, a `.py` file ends with two newlines, no comments that restate the code. Never write long dashes, arrows, curly quotes or an ellipsis character.

Do not commit or push: suggest a short conventional commit message with a gitmoji, and the user commits.

