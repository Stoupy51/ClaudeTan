
# ClaudeTan : plan

Assistant vocal personnel branché sur l'abonnement Claude (pas l'API). On dit "Hey Claude", une session Claude Code cachée exécute la demande, et Claude-tan apparaît à l'écran pour réagir. Un clic sur elle ouvre le Remote Control, un appui long la déplace.

Personnage tiré de la vidéo https://www.youtube.com/watch?v=_m38WbRlzv0 (Bright Mirror).

## Décisions

| Sujet | Choix |
| :- | :- |
| Mot d'activation | Whisper transcrit chaque phrase et une regex repère "Hey Claude" (FR et EN). Un vrai modèle de mot d'activation viendra plus tard. Le GPU travaille dès que quelqu'un parle près du micro, vidéos comprises. |
| Réponse | Bulle de texte et voix (TTS). La voix parle japonais par défaut, sous-titrée par la bulle. Sa langue se règle dans la config, où elle se coupe aussi. Voir [Voix japonaise](#voix-japonaise). |
| Permissions | Session en `--permission-mode auto`. Ce que le classifieur bloque passe par Claude-tan ou par le Remote Control. |
| Conversation | Persistante (`--resume` de la conversation dont l'app garde l'id), compactée (`/compact`) à l'arrêt de l'app et après 55 min sans activité. |
| Modèles | Tâches compliquées confiées à Opus 5.5 par défaut. Session principale sur un modèle rapide, Sonnet 5.5 proposé. Les deux se règlent dans la config, voir [Modèle](#modèle). |

Les 55 min viennent du cache de prompt, qui dure 1 h sur abonnement. `/compact` relit toute la conversation : tant que le cache est chaud, cette lecture coûte le tarif réduit du cache.

## Fonctionnalités

### Retour immédiat

Chaque demande doit être visiblement prise en compte tout de suite, puis suivie jusqu'au bout, même quand Claude part sur un gros chantier : son et apparition dès le mot d'activation, phrase comprise dans la bulle, action en cours, pastille discrète pendant une tâche longue, puis Claude-tan qui réapparaît avec un petit son à la fin, sans notification Windows. Le détail par événement est dans [Architecture](#architecture).

### Opus pour les tâches compliquées

La session principale délègue les tâches compliquées (code, recherche, plusieurs étapes) à un sous-agent que l'app lui passe par `--agents`, avec le modèle de la config et `background: true`. Un fichier dans `.claude/agents/` ajouterait aussi ce sous-agent aux sessions de développement lancées dans le repo. C'est la description du sous-agent qui dit à la session quand déléguer. Le sous-agent tourne en arrière-plan, la session reste libre pour les petites demandes, et `SubagentStart` / `SubagentStop` alimentent le retour immédiat.

### Actions simples sans quota Claude

Un registre d'actions Python, chacune avec un nom, une description, ses paramètres et des exemples de phrases :

- capture de l'écran 1 ou 2 (mss), analysée par un modèle de vision local ou par Claude selon la config ;
- raccourci clavier, par exemple Alt+F10 pour l'enregistrement instantané ShadowPlay (à tester : NVIDIA accepte-t-il une touche simulée par SendInput) ;
- lancer une app, météo du jour (Open-Meteo, sans clé), volume et lecture média, minuteur ;
- usage du forfait (fenêtre de 5 h, semaine) et tokens de la session, lus dans les données de la statusline (voir [Notes techniques](#notes-techniques)).

Un routeur choisit qui répond, du moins cher au plus cher : des règles exactes pour les phrases connues, puis un petit modèle local avec appel de fonctions via Ollama (à réinstaller, il n'est plus sur le disque ; Qwen3 4B ou équivalent tient en 3 Go de VRAM environ à côté de Whisper), puis Claude pour tout le reste. Claude appelle les mêmes actions par un serveur MCP local, donc chaque outil ajouté sert aux deux.

### Auto-amélioration

La session cachée travaille dans le repo ClaudeTan. "Crée-toi un outil pour X" devient une nouvelle action que Claude écrit dans le registre, avec sa description et un test, validée par ruff, pyright et stouputils check. Un `CLAUDE.md` explique à la session comment faire. L'app recharge le registre à chaud et ne se relance, en reprenant la session, que si son cœur a changé. Un lanceur minimal surveille cette relance : si l'app plante juste après un changement, il annule ce changement (`git stash` ou `git revert`), relance l'app et prévient, sans quoi l'assistant cassé ne pourrait plus se réparer lui-même.

Le mode se règle dans la config : changements laissés à relire, commités sur une branche dédiée, ou "auto-suffisant", commités directement sur main sans relecture. "À relire" reste le défaut tant que le lanceur n'existe pas. `~/.claude/CLAUDE.md` interdit de commiter sans demande : l'app donne donc le mode à la session cachée par `--append-system-prompt`, et non dans le CLAUDE.md du repo, que lisent aussi les sessions de développement.

### Depuis l'iPhone

Possible dès le MVP, sans serveur. Grâce au Remote Control, l'app Claude iOS parle déjà à la session cachée (texte ou dictée), avec tous ses outils locaux. Claude Code envoie aussi des notifications push au téléphone à la fin d'une tâche longue ou quand il faut décider (`/config` : "Push when Claude decides" et "Push when actions required"). Pour avoir la voix et l'avatar sur le téléphone, piste à creuser : une page web servie par l'app et joignable via Tailscale (réseau privé, rien d'ouvert sur Internet) plutôt qu'un serveur public.

### Voix japonaise

Pour l'immersion, Claude-tan parle japonais par défaut, même quand la bulle est dans une autre langue : la bulle sert alors de sous-titres. Quand la langue de la voix diffère de celle de la bulle, un modèle local traduit le texte, sans quota Claude : TranslateGemma 4B (Ollama, 3,3 Go), spécialisé dans la traduction, ou le modèle du routeur si la VRAM manque, puisque les 12 Go de la RTX 3060 servent aussi à Whisper, au routeur et aux jeux. Sur une longue réponse, la voix ne dit que les premières phrases et jamais le code : traduire tout le texte avec un modèle de 4B serait lent et approximatif.

En japonais, la voix vient de VOICEVOX, un moteur local aux voix d'anime piloté par une API HTTP. Il donne aussi la durée de chaque voyelle, donc la bouche peut suivre les voyelles plutôt que l'amplitude. AivisSpeech offre la même API avec des voix plus naturelles, mais sans ces durées. Edge n'a que deux voix japonaises (Nanami et Keita), sans style anime, et sert aux autres langues.

## Architecture

Une seule app Python (PySide6) en six parties :

- **voice** : micro, Silero VAD, faster-whisper sur le GPU, regex du mot d'activation. Produit une commande texte.
- **router** : décide si la commande est une action locale ou part dans la session (règles exactes, puis petit modèle local).
- **actions** : le registre d'actions, utilisé par le routeur et, via MCP, par Claude.
- **session** : Claude Code dans un pseudo-terminal caché (pywinpty) avec `--remote-control` et des hooks HTTP vers l'app. Les commandes y sont tapées comme au clavier.
- **avatar** : l'overlay, qui montre où en est la demande par l'expression, la bulle et la voix.
- **tray** : icône de notification, config TOML, démarrage avec Windows.

Ce que montre Claude-tan à chaque étape :

| Événement | Retour |
| :- | :- |
| mot d'activation détecté | petit son et apparition en écoute, avant la fin de la phrase : son début est transcrit dès 1,3 s |
| phrase transcrite | la phrase comprise dans la bulle |
| action locale exécutée | `present` et le résultat |
| `UserPromptSubmit` | `point` : elle réfléchit |
| `PreToolUse` | l'action en cours dans la bulle ("écrit main.py"), sans répéter la même |
| `SubagentStart`, ou tâche de plus de 20 s | elle se réduit en pastille animée dans un coin |
| `PermissionRequest`, `Notification` de type `permission_prompt` | `please`, puis `thanks` si accepté |
| `MessageDisplay` | elle parle : `idle`, bouche animée et voix |
| `Stop` | son, `present` si des outils ont servi, sinon `happy`. Si un sous-agent tourne encore, elle redevient pastille. |
| `SubagentStop` | rien : la session annonce le résultat dans le tour qu'elle lance ensuite |
| `StopFailure` | `surprised` et le type d'erreur |

## Étapes

### 0. Prototypes (fait)

- [x] `prototypes/session_demo.py` : session Remote Control cachée, envoi de prompts avec accents, événements des hooks.
- [x] `prototypes/voice_demo.py` : VAD, Whisper, mot d'activation et commande, 10/10 sur des clips FR et EN.
- [x] `prototypes/overlay_demo.py` : overlay, clignement, bouche, bulle, clic, appui long, Ctrl+C.
- [x] Sprites sur un seul canevas, yeux alignés, couleurs uniformisées (voir [Sprites](#sprites)).

### 1. MVP

- [x] App `claudetan` : machine à états entre la voix, l'avatar et les hooks HTTP de la session, testée sur des événements simulés.
- [x] Retour immédiat : son au mot d'activation, phrase dans la bulle, suivi des hooks, pastille pour les tâches longues, retour de Claude-tan avec un son à la fin.
- [x] N'envoyer une commande qu'entre deux tours (de `UserPromptSubmit` à `Stop`), sinon la mettre en file : taper pendant qu'un dialogue est ouvert casse la session.
- [x] Session cachée lancée par l'app dans le repo : `--session-id` au premier lancement, puis `--resume` avec l'id gardé par l'app, puisque `--continue` reprendrait la dernière conversation du dossier, souvent une session de développement.
- [ ] Sous-agent des tâches compliquées passé par `--agents`, avec les modèles de la session et du sous-agent dans la config.
- [x] Mini system prompt passé par `--append-system-prompt-file` : où l'app est installée et comment elle a lancé la session, puis les ajouts de l'utilisateur (clé `prompt` de la config, par exemple où sont ses dossiers).
- [ ] Dialogue "Resume from summary" que Claude Code affiche sur Pro quand une grosse session reprend après une longue pause : Entrée choisit le résumé, l'option par défaut.
- [ ] `/compact` à l'arrêt et après 55 min d'inactivité, seulement quand le contexte est gros (estimé via le `transcript_path` des hooks), car la compaction est elle-même une grosse requête. Le hook `PostCompact` dit quand elle est finie.
- [x] Clic sur Claude-tan : ouvrir l'URL de session lue dans le terminal caché, au lieu de la liste des sessions de claude.ai/code.
- [ ] Notifications push : `inputNeededNotifEnabled` ("Push when actions required") dans le `--settings` de la session. `agentPushNotifEnabled` ("Push when Claude decides") est déjà actif dans les réglages utilisateur.
- [x] Config TOML dans `%APPDATA%\ClaudeTan\config.toml`, copiée au premier lancement : langue et regex d'activation. Les modèles y entrent avec la session, la voix avec le TTS.
- [x] Claude-tan revient où on l'a déposée. Si cet écran est débranché, elle apparaît sur l'écran principal sans oublier sa place, et y retourne quand il est rebranché.
- [x] Icône de notification, avec le même menu au clic gauche et au clic droit, et démarrage avec Windows.
- [x] README et `uv run claudetan-setup` : Whisper téléchargé et testé sur le GPU, puis, au besoin, connexion à Claude Code et dialogue de confiance du dossier, que le script ouvre et où l'utilisateur répond.

### 2. Voix et contrôle

- [ ] TTS désactivable, en japonais par défaut : traduction locale et VOICEVOX (à installer), bouche sur les voyelles. Seulement les premières phrases des longues réponses, jamais le code. Langue de la voix dans la config, voix Edge pour les autres langues (`fr-FR-VivienneMultilingualNeural`, `DeniseNeural`, `HenriNeural`, `RemyMultilingualNeural`), bouche sur l'amplitude.
- [ ] Commandes vocales "stop", "annule", "passe en Opus" (`/model opus`).
- [ ] Accepter ou refuser une permission à la voix, en répondant au hook `PermissionRequest`.

### 3. Actions locales

- [ ] Registre d'actions et premières actions : capture de l'écran 1 ou 2, raccourcis clavier (Alt+F10 pour ShadowPlay), lancer une app, météo, volume et média, minuteur, usage du forfait.
- [ ] Routeur : règles exactes, puis petit modèle local via Ollama, puis Claude.
- [ ] Analyse d'une capture par un modèle de vision local ou par Claude, au choix dans la config.
- [ ] Serveur MCP local pour que Claude appelle les mêmes actions.

### 4. Auto-amélioration

- [ ] `CLAUDE.md` du repo qui explique à la session comment ajouter une action, avec son test et les contrôles.
- [ ] Rechargement à chaud du registre, et relance de l'app avec reprise de la session quand son cœur change.
- [ ] Lanceur qui annule le dernier changement et relance l'app quand elle plante juste après.
- [ ] Mode dans la config : à relire (défaut tant que le lanceur manque), branche dédiée ou auto-suffisant (commits directs sur main), transmis à la session par `--append-system-prompt`.

### 5. Avatar

- [ ] Expressions manquantes : travaille, réfléchit de face, triste ou erreur. Piste spéculative : éditer `idle` avec un modèle d'édition d'image (FLUX Kontext, Qwen-Image-Edit), puis passer le résultat dans le pipeline.
- [ ] Clignement et bouche sur toutes les poses, pas seulement `idle` et `hello`.
- [x] Pipeline de sprites dans `tools/sprites/`, pour pouvoir ajouter des expressions.

### 6. Plus tard

- [ ] Page web pour parler à Claude-tan depuis l'iPhone (voix et avatar), joignable via Tailscale.
- [ ] Channels (serveur MCP) quand la fonction sortira de la research preview, pour ne plus taper dans le terminal.
- [ ] Modèle de mot d'activation dédié en FR (livekit-wakeword), pour ne plus réveiller Whisper à chaque phrase.

## Sprites

`assets/claude/` contient 16 PNG de 850x608 px. Dans toutes les images de face, les iris tombent sur les mêmes pixels à 0,4 px près : gauche (382,4 ; 288,9), droit (467,6 ; 271,1). `point` regarde de côté, ce sont donc ses yeux et non ses iris qui sont alignés.

| Sprite | Image source (vidéo à 30 images/s) | Usage |
| :- | :- | :- |
| `idle` | 3771 | repos, main sur le coeur |
| `idle_talk_open`, `idle_talk_o`, `idle_talk_wide` | bouches de 3785, 3789, 3757 | `idle` qui parle |
| `idle_blink` | yeux de 1998 | clignement |
| `happy` | 3764 | grand sourire |
| `surprised` | 3760 | surprise |
| `hello` | 72 | salut de la main |
| `hello_talk_open`, `hello_talk_o`, `hello_talk_wide` | bouches de 93, 82, 67 | `hello` qui parle |
| `present` | 134, super-résolution x4 | "voilà" |
| `please` | 5987 | demande, mains jointes |
| `thanks` | 5979 | merci, mains jointes |
| `point` | 3512, super-résolution x4 | doigt levé, regard de côté |
| `stand` | 3489, super-résolution x4 | sourire bouche ouverte |

Le pipeline, dans l'ordre :

1. Détourage ToonOut (BiRefNet affiné sur l'anime) en deux passes.
2. Iris trouvés par corrélation avec ceux d'`idle`, puis une similitude pose les deux yeux sur les pixels cibles.
3. Couleurs du personnage séparées du fond sur les bords (blur fusion), super-résolution Real-ESRGAN anime pour les plans larges.
4. Fondu de 40 px partout où le cadre ou le décor la coupe, et fondu commun en bas (lignes 430 à 604).
5. Reflets violets des néons repeints couleur cheveux, puis couleurs ramenées sur celles d'`idle`, peau, cheveux et reste séparément.
6. Bouches et yeux greffés sur la pose de base après un alignement local.

Le pipeline est dans `tools/sprites/`, un projet uv à part qui garde torch hors de l'app. `uv run build.py` dans ce dossier régénère `assets/claude/` en 3 min (ffmpeg et node sur le PATH, GPU CUDA) et affiche l'écart de chaque iris à sa cible. La vidéo, les images décodées, les poids des modèles et les détourages sont gardés dans `tools/sprites/.work/`, ignoré par git. Ajouter une expression revient à ajouter une ligne à `POSES` ou à `RIGS` dans `build.py`.

## Modèle

Sur Pro, la fenêtre de 5 h et la limite hebdomadaire sont communes à claude.ai et à Claude Code. Un modèle plus cher par token consomme la limite plus vite ; Anthropic ne publie pas le ratio exact, l'écart des prix API en donne l'ordre de grandeur.

| Modèle | Prix API, entrée / sortie ($ par million de tokens) | Pour l'assistant |
| :- | :- | :- |
| Haiku 5.5 | à partir de 0,10 / 0,50 | Le plus rapide, fait pour trier et router. Option économe pour la session principale, trop léger pour du vrai code. |
| Sonnet 5.5 | 2 / 10 | Rapide et capable : proposé pour la session principale. |
| Opus 5.5 | 4 / 20 | Défaut de Claude Code sur Pro. Le sous-agent des tâches compliquées. |
| Fable 5.1 | 10 / 50 | Longues tâches autonomes, lent, et facturable en crédits d'usage hors abonnement. Pas pour l'assistant. |

Les quatre acceptent le mode `auto`. Les demandes simples ne consomment rien : le routeur les traite en local avant Claude.

## Points d'attention

- Sessions Remote Control de test à archiver sur claude.ai : "ClaudeAssist (test)" et "Claude Assist".

## Notes techniques

- L'abonnement ne fonctionne que dans Claude Code et claude.ai. L'app pilote donc le vrai CLI dans un pseudo-terminal, ce qui reste conforme.
- pywinpty : passer argv en liste (une chaîne garde ses guillemets) et lancer via `cmd.exe /c chcp 65001 >nul && claude ...`, sinon les accents arrivent en cp850.
- Retirer les variables d'une session imbriquée (`CLAUDECODE`, `CLAUDE_CODE_ENTRYPOINT`, `CLAUDE_CODE_SESSION_ID`, `CLAUDE_CODE_CHILD_SESSION`, `CLAUDE_CODE_MESSAGING_SOCKET`, `CLAUDE_CODE_MESSAGING_TOKEN`, `CLAUDE_PID`) avant de lancer `claude`.
- Remote Control archive la session sur claude.ai quand Claude Code se ferme proprement : l'app le tue (`taskkill /F /T`) pour qu'elle reste dans la liste, et `--resume` la rattache.
- Claude Code ne redessine que les caractères qui changent : l'app lit son terminal à travers un écran `pyte`, par exemple `/usage` au démarrage.
- uv 0.12 avec Python 3.14 fait du `pythonw.exe` d'un venv une copie du `python.exe` console : un gui-script ouvre donc une console. `claudetan` est un script console qui relance l'app avec `CREATE_NO_WINDOW` et rend la main.
- Le dialogue de confiance du dossier propose "No, exit" par défaut. L'app n'y répond pas : la session tourne dans le repo, déjà approuvé, et s'il s'affiche, il faut lancer `claude` une fois dans le repo pour l'accepter. Pour envoyer un prompt : le taper, attendre 0,4 s, puis `\r`.
- Hooks `type: "http"` déclarés dans un fichier passé par `--settings`. `SessionStart` n'accepte que les hooks `command` et `mcp_tool`.
- `--append-system-prompt` est enregistré à la première requête de la conversation, puis réutilisé tel quel jusqu'à la prochaine compaction, même si un lancement suivant passe un autre texte (`--system-prompt-snapshot`, actif par défaut). Un changement de mode d'auto-amélioration ne vaut donc qu'après un `/compact`, ou avec `--system-prompt-snapshot off`.
- Statusline : sa commande, déclarée dans le même fichier `--settings` que les hooks, reçoit en JSON `rate_limits.five_hour` et `rate_limits.seven_day` (`used_percentage`, `resets_at`), `cost.total_cost_usd` et `context_window`, et les transmet à l'app. `rate_limits` n'apparaît qu'après la première réponse de la session et ne change qu'à ses réponses, alors que la limite est partagée avec claude.ai et les autres sessions : `/usage` (alias `/cost` et `/stats`) donne le chiffre frais.
- Channels exige `--dangerously-load-development-channels`, qui pose une question interactive : inutilisable en session cachée pour l'instant.
- Whisper : `large-v3-turbo` (0,5 s) ou `small` (0,2 s) en `int8_float16` sur CUDA, `beam_size=1`, `condition_on_previous_text=False`, audio passé en numpy (le décodage par PyAV plante). cuDNN vient de la roue de ctranslate2, cuBLAS du CUDA Toolkit 12 sur le PATH.
- Silero VAD : trames de 512 échantillons à 16 kHz, sortie 1-D.
- Picovoice n'a plus d'offre gratuite et le modèle openWakeWord "hey claude" n'existe qu'en anglais.
- Mesuré : démarrage de session 5,5 s, réponse simple 2,3 s, tour avec un outil 8,5 s.
- Ctrl+C dans une app Qt : la boucle d'événements ne rend pas la main à Python, d'où `signal.signal(signal.SIGINT, signal.SIG_DFL)`.
- Captures hors écran (`QT_QPA_PLATFORM=offscreen`) : sans `QT_QPA_FONTDIR=C:/Windows/Fonts`, le texte s'affiche en carrés.

