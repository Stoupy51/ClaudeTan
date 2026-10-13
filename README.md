
# 🎙️ ClaudeTan

<div align="center">

*Say "Hey Claude": Claude-tan pops up on your screen while a hidden Claude Code session, running on your Claude subscription, does the work.*

</div>

https://github.com/user-attachments/assets/84a558a3-62a4-4e16-9a47-94099be6e3ad

*The same demo [in French](https://github.com/user-attachments/assets/4ad7b61b-bd03-42bd-b620-04c7be436a48).*

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
- Tick *Start with Windows* in her tray menu to start her at logon.

## ▶️ Usage

```powershell
uv run claudetan
```

The app starts in the background with a hidden Claude Code session in this folder, prints the session's link and your plan usage once ready, and keeps running until you quit it from her tray icon.
The session stays in claude.ai's list after you quit, and the app resumes it on its next start.
Say *"Hey Claude, ..."*: she shows up as soon as she hears it, shows the sentence she understood, then what the session does and its answer.
Speak English, French or any language Whisper knows: the session answers in it, and her own lines are in French when you speak French, in English otherwise.
A request that is exactly one of the phrases below is done by the app itself, at once and without the session. Any other wording goes to the session, which has the same actions as tools (`mcp__claudetan__*`) and calls them itself.

| Action | Say | Does |
|---|---|---|
| Screenshot | *"take a screenshot of screen 2"*, *"capture l'écran 2"* | Saves the screen (1 to 3, the first by default) in `Pictures\Screenshots` |
| Start a transcription | *"transcribe the meeting"*, *"transcris la réunion"* | Writes everything the PC plays and your microphone hears into `Documents\Transcriptions`, one timed line per sentence |
| Stop the transcription | *"stop the transcription"*, *"arrête la transcription"* | Closes that file |
| Stop everything | *"stop everything"*, *"arrête tout"* | Kills the running request, its agents and the queued commands, then starts the session again on the same conversation. The app keeps running |
| Switch model | *"switch to Opus"*, *"passe en Sonnet"* | Types `/model` into the session once its current request is done |
| Context of the session | *"show me the context"*, *"le contexte"*, or the tray menu | How full the hidden session's context window is, as `/context` reports it |
| Plan usage | *"my usage"*, *"mon usage"*, or the tray menu | Share of the 5-hour window and of the week used, as `/usage` reports it |
| Timer | *"set a timer for 10 minutes"*, *"mets un minuteur de 10 minutes"* | Rings with a sound and a message when it is over |
| Weather | *"what's the weather in London"*, *"quel temps fait-il"* | Weather now and for the day, from Open-Meteo. Without a city, the `city` of the config |
| Open a program | Any request, through the session (`launch_program` tool) | Opens the program whose Start menu shortcut matches the name |
| Read Discord messages | *"read the messages from Artyu"*, *"lis les messages de Artyu"* | Shows the last direct messages with that person, read with the `discord_token` of the config. It never sends anything |
| ShadowPlay clip | *"clip that"*, *"enregistre ça"* | Presses Alt+F10 |
| Mute | *"mute"*, *"coupe le son"* | Toggles the mute |

You may pause while you speak: she sends your request after 15 s of silence, or as soon as you say *"done"* (or *"terminé"*) as a sentence of its own after a pause, or end it with *"over"* (or *"c'est tout"*). *"Cancel"* said alone, or *"cancel prompt"* at the end, drops it. The bubble reminds you of the word.

- When she asks your permission, say *"yes"* or *"no"* as a sentence of its own, within 60 s. Otherwise answer in Claude Code or on claude.ai as usual.
- A click on her opens Claude Code's Remote Control on claude.ai, a long press lets you drag her.
- Dropped on a second screen, she comes back there, and shows up on the main screen while it is unplugged.
- Her tray icon, with a left or a right click, opens the session, the config or the log of what she heard and did, toggles the start with Windows, and quits.

## ⚙️ Configuration

*Open the config* in the tray menu opens `%APPDATA%\ClaudeTan\config.toml`, which explains each key:
the speech recognition language, the wake phrase, the pause and the phrases that end a spoken request,
the models of the hidden session (Sonnet) and of the agent it hands complicated requests to (Opus), her size on screen, and your additions to the session's system prompt, such as where your folders are.
A change applies as soon as you save the file, and she tells you what changed. The agent's model and the system prompt, which Claude Code reads only when it starts, restart the hidden session on the same conversation once she has nothing running.

## 🧑‍💻 Development

```powershell
uv run pytest tests --doctest-modules claudetan
uv run ruff check .
uv run pyright
uv run prototypes/overlay_demo.py              # plays every expression in a loop
uv run scripts/demo_video/main.py              # renders dist/demo_en.mp4 and dist/demo_fr.mp4, a scripted run through her features (needs ffmpeg)
uv run prototypes/voice_demo.py --wav clip.wav # prints what the listener hears, from the microphone without --wav
```

The demo videos at the top of this file are the `_small` copies of that script's videos, uploaded with the [gh-image](https://github.com/drogers0/gh-image) extension:
`gh image dist/demo_en_small.mp4 --repo Stoupy51/ClaudeTan` prints the link to paste in place of the old one.

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

