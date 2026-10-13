
# 🎙️ ClaudeTan

<div align="center">

<img src="assets/claude/hello.png" alt="Claude-tan waving" width="360">

*Say "Hey Claude": Claude-tan pops up on your screen while a hidden Claude Code session, running on your Claude subscription, does the work.*

</div>

> [!NOTE]
> Work in progress: the roadmap is in [PLAN.md](PLAN.md), in French.

## 📋 Requirements

- Windows 10 or 11 and a microphone.
- An NVIDIA GPU with the CUDA 12 runtime, which the [CUDA Toolkit 12](https://developer.nvidia.com/cuda-downloads) installs, for Whisper.
- [uv](https://docs.astral.sh/uv/getting-started/installation/), which installs Python 3.14 by itself.
- [Claude Code](https://code.claude.com/docs/en/setup), signed in with a Claude Pro or Max subscription.

## 🔧 Installation

```powershell
git clone https://github.com/Stoupy51/ClaudeTan
cd ClaudeTan
uv run claudetan-setup
```

The setup installs the dependencies, downloads Whisper (1.6 GB) and runs it once on the GPU.
Then, only when needed, it opens Claude Code's sign-in page, and Claude Code itself in this folder so that you trust it:
pick *Yes, I trust this folder*, then type `/exit`. This dialog is Claude Code's safety check before it works in a folder, so the app never answers it for you.

Optional, once:

- Windows hides new tray icons behind the `^` arrow: drag Claude-tan's next to the clock to keep it in sight.
- Tick *Démarrer avec Windows* in her tray menu to start her at logon.

## ▶️ Usage

```powershell
uv run claudetan
```

The app starts in the background with a hidden Claude Code session in this folder, prints the session's link and your plan usage once ready, and keeps running until you quit it from her tray icon.
The session stays in claude.ai's list after you quit, and the app resumes it on its next start.
Say *"Hey Claude, ..."* or *"Hé Claude, ..."*: she shows up as soon as she hears it, shows the sentence she understood, then what the session does and its answer.
A request that is exactly one of the phrases below is done by the app itself, at once and without the session. Any other wording goes to the session, which has the same actions as tools (`mcp__claudetan__*`) and calls them itself.

| Action | Say | Does |
|---|---|---|
| Screenshot | *"capture l'écran 2"*, *"screenshot"* | Saves the screen (1 to 3, the first by default) in `Pictures\Screenshots` |
| Start a transcription | *"transcris la réunion"*, *"lance la transcription"* | Writes everything the PC plays and your microphone hears into `Documents\Transcriptions`, one timed line per sentence |
| Stop the transcription | *"arrête la transcription"* | Closes that file |
| Stop everything | *"stop"*, *"arrête tout"*, *"annule ça"* | Kills the running request, its agents and the queued commands, then starts the session again on the same conversation. The app keeps running |
| ShadowPlay clip | *"enregistre ça"*, *"clip"* | Presses Alt+F10 |
| Mute | *"coupe le son"*, *"remets le son"* | Toggles the mute |

You may pause while you speak: she sends your request after 15 s of silence, or as soon as you say *"fin"* (or *"terminé"*) as a sentence of its own after a pause, or end it with *"c'est tout"*, *"envoie"* or *"over"*. *"Annule"* said alone, or *"laisse tomber"* at the end, drops it. The bubble reminds you of the word.

- A click on her opens Claude Code's Remote Control on claude.ai, a long press lets you drag her.
- Dropped on a second screen, she comes back there, and shows up on the main screen while it is unplugged.
- Her tray icon, with a left or a right click, opens the session, the config or the log of what she heard and did, toggles the start with Windows, and quits.

## ⚙️ Configuration

*Ouvrir la config* in the tray menu opens `%APPDATA%\ClaudeTan\config.toml`, which explains each key:
the speech recognition language, the wake phrase, the pause and the phrases that end a spoken request,
the models of the hidden session (Sonnet) and of the agent it hands complicated requests to (Opus), her size on screen, and your additions to the session's system prompt, such as where your folders are.
A change applies as soon as you save the file, and she tells you what changed. The agent's model and the system prompt, which Claude Code reads only when it starts, restart the hidden session on the same conversation once she has nothing running.

## 🧑‍💻 Development

```powershell
uv run pytest tests --doctest-modules claudetan
uv run ruff check .
uv run pyright
uv run prototypes/overlay_demo.py              # plays every expression in a loop
uv run prototypes/voice_demo.py --wav clip.wav # prints what the listener hears, from the microphone without --wav
```

The sprites in `assets/claude/` come out of `tools/sprites/`, a separate uv project described in [PLAN.md](PLAN.md#sprites).

### With Claude Code in auto mode

The auto mode classifier stops a session from writing and running code that starts another Claude Code session in auto mode, which is what this app does ("Create Unsafe Agents").
To let Claude Code work on that part, add this exception to your user settings, `~/.claude/settings.json`, since the classifier ignores a project's own settings:

```json
"autoMode": {
	"allow": [
		"$defaults",
		"In the ClaudeTan repository, the app starts a hidden Claude Code session with claude --remote-control --permission-mode auto and types the user's voice commands into it: writing, testing and running that launcher, including scripts that start such a session to test it, is allowed."
	]
}
```

`claude auto-mode config` shows the rules in effect. Without the exception, ask for that action explicitly in your message instead.

