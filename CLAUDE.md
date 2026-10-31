
# ClaudeChan

A voice assistant with an anime overlay (PySide6), driving a hidden Claude Code session. `README.md` says how to run it, `PLAN.md` what is done and planned.

## Layout

- `src/claudechan/app.py`: the Qt app and `Assistant`, which turns hook events and heard requests into what Claire shows.
- `src/claudechan/session.py`: the hidden `claude` process in a pseudo-terminal, and the hook server.
- `src/claudechan/reload.py`: applies the hidden session's changes to the code in place once it has nothing running, and restarts the app only when a running loop or a live object comes from changed code.
- `src/claudechan/windows.py`: holds her avatar, pill and tray, and builds and wires them again after a reload of `overlay/`, of itself or of a sprite, while she has left.
- `src/claudechan/launcher.py`: runs the app, starts it again after such a change, and puts the change aside in git when the app then fails to start. It imports nothing of the app.
- `src/claudechan/actions.py`: `ACTIONS`, what she does on the computer. `mcp.py` offers the same list to the session as tools.
- `src/claudechan/services/`: what the actions call (weather, programs, timers, other applications' windows in `desktop.py`). Put the code of a new action there when it is more than a few lines.
- `src/claudechan/voice/`: microphone, Whisper, wake and end phrases, meeting transcription, and her Japanese voice (`speech.py`). `overlay/`: avatar, bubble, tray.
- `tools/sprites/`: a separate uv project that draws `assets/claude/`. Leave it alone unless asked about sprites.
- `tools/minecraft/`: a Fabric mod (Gradle, Java) for the test client the `minecraft_*` actions drive over HTTP (`services/minecraft.py`). `gradlew.bat runClient` starts it, its game folder is `run/`; `runClient2` starts a second player, ClaudeChan2, whose bridge listens on 47622, for tests that need two.

## Adding an action

1. Add one `Action(...)` to `ACTIONS` in `actions.py`, with `name`, `description` (what the session reads to choose the tool), `phrases` (a regex matched against the whole request, its named groups being the arguments), `run` (returns what she says, as `tr(english, french)` from `i18n.py`) and `parameters` when it takes arguments.
2. The same entry is then a voice phrase and the MCP tool `mcp__claudechan__<name>`. Never list an action anywhere else.
3. Add a `>>>` example to `route` or a test in `tests/` for the behaviour that could break. Mock only I/O (network, key presses), as `tests/test_services.py` does.
4. Add a row to the table in `README.md`.

Actions run on the Qt thread: keep them quick, and start a thread for anything long, as `meeting.py` does, or set `threaded=True` on a tool that answers after seconds. An effect on the session itself (typing `/model`, restarting it) goes in `Assistant.run_action`, not in the action.

A reload gives the live objects their class's new methods and keeps every module-level value whose line did not change, such as `ALARMS`. It restarts the app, cutting the session's work, when the change reaches a loop still running (`Listener.run`, the threads of `Voice` and `Session`, `app.run`, which wires everything) or what built a live object: its `__init__`, its signals and fields, and the constants and methods `__init__` uses. Put new logic in methods rather than there when you can.

## Checks

All must pass before you report: `uv run ruff check`, `uv run pyright`, `uv run pytest --doctest-modules src tests`, `uv run stouputils check`, `uvx complexipy src --failed --max-complexity-allowed 15`.

Code style: tabs, pyright strict, a `.py` file ends with two newlines, no comments that restate the code. Never write long dashes, arrows, curly quotes or an ellipsis character.

Do not commit or push: suggest a short conventional commit message with a gitmoji, and the user commits.

