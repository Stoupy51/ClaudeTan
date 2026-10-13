
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
- lancer une app, météo du jour (Open-Meteo, sans clé), minuteur ;
- usage du forfait (fenêtre de 5 h, semaine) et tokens de la session, lus dans les données de la statusline (voir [Notes techniques](#notes-techniques)).

Un routeur choisit qui répond, du moins cher au plus cher : des règles exactes pour les phrases connues, puis un petit modèle local avec appel de fonctions via Ollama (à réinstaller, il n'est plus sur le disque ; Qwen3 4B ou équivalent tient en 3 Go de VRAM environ à côté de Whisper), puis Claude pour tout le reste. Claude appelle les mêmes actions par un serveur MCP local, donc chaque outil ajouté sert aux deux.

### Auto-amélioration

La session cachée travaille dans le repo ClaudeTan. "Crée-toi un outil pour X" devient une nouvelle action que Claude écrit dans le registre, avec sa description et un test, validée par ruff, pyright et stouputils check. Un `CLAUDE.md` explique à la session comment faire. L'app recharge le registre à chaud et ne se relance, en reprenant la session, que si son cœur a changé. Un lanceur minimal surveille cette relance : si l'app plante juste après un changement, il annule ce changement (`git stash` ou `git revert`), relance l'app et prévient, sans quoi l'assistant cassé ne pourrait plus se réparer lui-même.

Le mode se règle dans la config : changements laissés à relire, commités sur une branche dédiée, ou "auto-suffisant", commités directement sur main sans relecture. "À relire" reste le défaut tant que le lanceur n'existe pas. `~/.claude/CLAUDE.md` interdit de commiter sans demande : l'app donne donc le mode à la session cachée par `--append-system-prompt`, et non dans le CLAUDE.md du repo, que lisent aussi les sessions de développement.

### Applications connectées

Claude-tan lit d'autres applications sans jamais y écrire, à commencer par Discord. Exemple : "Artyu m'a MP pour une PR, tu peux aller la résoudre stp ?" La session retrouve le dernier MP d'Artyu, y lit le lien de la PR et confie la correction au sous-agent Opus. C'est l'utilisateur qui répond sur Discord. Chaque application connectée devient une action du registre, donc aussi un outil MCP pour Claude. GitHub passe déjà par `gh`, que la session sait utiliser.

Les MP sont lus avec le compte de l'utilisateur, par l'API HTTP que le client Discord utilise lui-même, en lecture seule : l'app n'envoie jamais rien. Discord interdit d'automatiser un compte utilisateur, même en lecture ; l'utilisateur accepte ce risque pour son compte. Le jeton du compte se met dans la config, à la main.

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
| phrase transcrite | la demande comprise jusque-là dans la bulle, envoyée après 15 s de silence ou dès que tu dis "fin" seul après une pause ou finis par "c'est tout" ("annule" seul l'annule). Délai et formules se règlent dans la config. |
| action locale exécutée | `present` et le résultat |
| `UserPromptSubmit` | `thinking` : elle réfléchit |
| `PreToolUse` | `working` et l'action en cours dans la bulle ("écrit main.py"), sans répéter la même |
| `SubagentStart`, ou tâche de plus de 20 s | elle se réduit en pastille animée dans un coin |
| `PermissionRequest`, `Notification` de type `permission_prompt` | `please`, puis `thanks` si accepté |
| `MessageDisplay` | elle parle : `idle` avec une bouche ouverte tirée au hasard pour tout le message, et voix |
| `Stop` | son, `present` si des outils ont servi, sinon `happy`. Si un sous-agent tourne encore, elle redevient pastille. |
| `SubagentStop` | rien : la session annonce le résultat dans le tour qu'elle lance ensuite |
| `StopFailure` | `sad` et le type d'erreur |

## Étapes

### Priorité

- [x] `scripts/demo_video.py` : une vidéo de démonstration refaisable d'une commande, où l'overlay réel joue un scénario (réveil, dictée, requête avec outils, actions locales, minuteur, permission, contexte, météo). Une horloge manuelle et un hasard fixé donnent la même vidéo à chaque fois. Rien n'est exécuté pour de vrai. Ajouter une scène au scénario quand une fonction mérite d'être montrée.

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
- [x] Sous-agent des tâches compliquées passé par `--agents`, avec les modèles de la session et du sous-agent dans la config.
- [x] Mini system prompt passé par `--append-system-prompt-file` : où l'app est installée et comment elle a lancé la session, puis les ajouts de l'utilisateur (clé `prompt` de la config, par exemple où sont ses dossiers).
- [x] Dialogue "Resume from summary" que Claude Code affiche sur Pro quand une grosse session reprend après une longue pause : Entrée choisit le résumé, l'option par défaut.
- [x] `/compact` à l'arrêt et après 55 min d'inactivité, seulement au-delà de 100k tokens de contexte (lus dans le `transcript_path` des hooks), car la compaction est elle-même une grosse requête et une session neuve pèse déjà 50k. Le hook `PostCompact` dit quand elle est finie.
- [x] Clic sur Claude-tan : ouvrir l'URL de session lue dans le terminal caché, au lieu de la liste des sessions de claude.ai/code.
- [x] Notifications push : `inputNeededNotifEnabled` ("Push when actions required") dans le `--settings` de la session. `agentPushNotifEnabled` ("Push when Claude decides") est déjà actif dans les réglages utilisateur.
- [x] Config TOML dans `%APPDATA%\ClaudeTan\config.toml`, copiée au premier lancement : langue et regex d'activation. Les modèles y entrent avec la session, la voix avec le TTS.
- [x] Claude-tan revient où on l'a déposée. Si cet écran est débranché, elle apparaît sur l'écran principal sans oublier sa place, et y retourne quand il est rebranché.
- [x] Icône de notification, avec le même menu au clic gauche et au clic droit, et démarrage avec Windows.
- [x] README et `uv run claudetan-setup` : Whisper téléchargé et testé sur le GPU, puis, au besoin, connexion à Claude Code et dialogue de confiance du dossier, que le script ouvre et où l'utilisateur répond.

### 2. Avatar

- [x] Expressions travaille, réfléchit et triste, et poses `hello`, `present`, `please` et `thanks` redessinées depuis `idle` par Qwen-Image-Edit-2511, pour un style uniforme.
- [x] Clignement sur toutes les poses, yeux fermés redessinés sur la pose elle-même. Seules `idle` et `hello` parlent, avec une bouche ouverte tirée au hasard et gardée toute la réponse.
- [x] Bords coupés par le cadre fondus sur 90 px, comme le bas.
- [x] Rendu : halo chaud qui respire, apparition avec rebond et gerbe d'étincelles, fondu entre expressions, étincelles quand elle est contente ou présente un résultat, bulle à étiquette dont le texte s'écrit lettre par lettre, pastille en comète.
- [x] Pipeline de sprites dans `tools/sprites/`, pour pouvoir ajouter des expressions.

### 3. Auto-amélioration

- [x] `CLAUDE.md` du repo : la disposition, comment ajouter une action avec son test, les contrôles.
- [x] Config rechargée dès qu'elle est enregistrée, avec une réaction de Claude-tan : la voix et la taille tout de suite, le modèle par `/model`, le modèle du sous-agent et le prompt, que Claude Code ne lit qu'au démarrage, par une relance de la seule session sur la même conversation dès qu'elle n'a plus rien en cours.
- [ ] Rechargement à chaud du registre, et relance de l'app avec reprise de la session quand son cœur change.
- [ ] Lanceur qui annule le dernier changement et relance l'app quand elle plante juste après.
- [ ] Mode dans la config : à relire (défaut tant que le lanceur manque), branche dédiée ou auto-suffisant (commits directs sur main), transmis à la session par `--append-system-prompt`.

### 4. Actions locales

- [x] Registre d'actions (`actions.py`) et routeur à règles exactes : capture de l'écran 1 à 3, Alt+F10 pour ShadowPlay, coupure du son. Une phrase d'action part sans attendre la fin de la dictée.
- [x] Transcription de réunion jusqu'à ce qu'on l'arrête : son du PC (loopback WASAPI) et micro, chacun sur son fil, dans un fichier de `Documents\Transcriptions`.
- [x] ShadowPlay accepte le Alt+F10 simulé par `keybd_event`.
- [x] Actions `timer`, `weather` (Open-Meteo, `city` de la config) et `launch_program` (raccourcis du menu Démarrer, par la session seulement : "ouvre" ne doit pas avaler "ouvre le site").
- [x] Actions `context` et `plan_usage` (`services/claude.py`) : `claude -p "/context" --resume ... --fork-session` et `claude -p "/usage"`, sans rien taper dans la session cachée. Aussi dans le menu de l'icône.
- [ ] Petit modèle local via Ollama entre les règles et Claude.
- [ ] Analyse d'une capture par un modèle de vision local ou par Claude, au choix dans la config.
- [x] Serveur MCP local (`mcp.py`, HTTP sur 127.0.0.1) : chaque action de `ACTIONS` est aussi un outil `mcp__claudetan__*` de la session, qui reçoit `--mcp-config` et `--allowedTools`.

### 5. Voix et contrôle

- [ ] TTS désactivable, en japonais par défaut : traduction locale et VOICEVOX (à installer), bouche sur les voyelles. Seulement les premières phrases des longues réponses, jamais le code. Langue de la voix dans la config, voix Edge pour les autres langues (`fr-FR-VivienneMultilingualNeural`, `DeniseNeural`, `HenriNeural`, `RemyMultilingualNeural`), bouche sur l'amplitude.
- [x] Dictée : les pauses ne coupent plus la demande, envoyée après 15 s de silence, sur "fin" dit seul ou "c'est tout" en fin de phrase, et annulée par "annule" seul. Les mots courts ne comptent que seuls : "jusqu'à la fin" ne coupe rien.
- [x] Action "stop" : tue le tour en cours, ses agents et la file, puis relance la session sur la même conversation.
- [x] Action "model" ("passe en Opus", `/model` tapé entre deux tours), aussi outil MCP.
- [x] Permission à la voix : le hook `PermissionRequest` attend (60 s) un "oui" ou "non" seul, puis renvoie allow ou deny ; sans réponse, le dialogue reste à l'utilisateur. Mots dans la config (`allow`, `deny`).

### 6. Applications connectées

- [x] Action `discord_messages` (`discord.py`) : les derniers MP avec une personne, lus avec `discord_token` de la config, jamais envoyés.
- [ ] Donner à la session cachée l'accès au navigateur de l'utilisateur (Claude in Chrome) pour lire les pages qui demandent une connexion, comme le portail de Survisland, au lieu de s'arrêter devant la page de connexion.
- [ ] Piloter une application sans API, en dernier recours : capture et clics par vision, ou arbre d'accessibilité Windows (UI Automation, pauvre sur Electron). À décider avant : clics autorisés à chaque fois ou limités à certaines applications, car un mauvais clic peut envoyer ou supprimer.

### 7. Plus tard

- [ ] Page web pour parler à Claude-tan depuis l'iPhone (voix et avatar), joignable via Tailscale.
- [ ] Channels (serveur MCP) quand la fonction sortira de la research preview, pour ne plus taper dans le terminal.
- [ ] Modèle de mot d'activation dédié en FR (livekit-wakeword), pour ne plus réveiller Whisper à chaque phrase.

## Sprites

`assets/claude/` contient 23 PNG de 850x608 px. Dans toutes les images, les iris tombent sur les mêmes pixels à 0,5 px près : gauche (382,4 ; 288,9), droit (467,6 ; 271,1).

| Sprite | Source | Usage |
| :- | :- | :- |
| `idle` | image 3771 de la vidéo (30 images/s), redessinée au propre | repos, main sur le coeur |
| `idle_talk_open`, `idle_talk_o`, `idle_talk_wide` | bouches dessinées sur `idle` | `idle` qui parle |
| `happy` | dessiné depuis `idle` | grand sourire |
| `hello` | dessiné depuis `idle`, main gardée d'un dessin précédent | salut de la main |
| `hello_talk_open`, `hello_talk_wide` | bouches dessinées sur `hello` | `hello` qui parle |
| `present` | dessiné depuis `idle`, main gardée d'un dessin précédent | "voilà", paume ouverte |
| `please` | dessiné depuis `idle` | demande, mains jointes |
| `thanks` | dessiné depuis `idle` | merci, mains sur les joues |
| `thinking` | dessiné depuis `idle` | réfléchit, doigt sur le menton |
| `working` | dessiné depuis `idle`, mains gardées d'un dessin précédent | travaille, tape sur un clavier |
| `sad` | dessiné depuis `idle` | erreur, main sur la tête |
| `<pose>_blink`, pour chaque pose | yeux fermés dessinés sur la pose | clignement |

Le pipeline, dans l'ordre :

1. Détourage ToonOut (BiRefNet affiné sur l'anime) en deux passes.
2. Iris trouvés par corrélation avec ceux d'`idle`, puis une similitude pose les deux yeux sur les pixels cibles.
3. Couleurs du personnage séparées du fond sur les bords (blur fusion).
4. Fondu de 90 px partout où le cadre la coupe, et fondu commun en bas (lignes 430 à 604).
5. Reflets violets des néons repeints couleur cheveux, puis `idle` redessinée au propre par Qwen-Image-Edit-2511.
6. Les autres poses dessinées depuis `idle`, puis détourées et alignées comme l'image de la vidéo. Les mains de `hello`, `present` et `working` sont celles de calques gardés dans `tools/sprites/hands/`, que l'éditeur dessinait mieux à partir de l'image de la vidéo.
7. Bouches et yeux fermés dessinés sur la pose, puis greffés sur elle après un alignement local.
8. Le reflet en croix que l'éditeur met dans les pupilles est effacé et remplacé par une étoile blanche à 7 branches comme la fleur de ses cheveux (`spark.svg`), sauf sur les yeux fermés.
9. Couleurs de chaque sprite ramenées sur celles d'`idle`, mesurées là où les deux dessins montrent la même chose, car l'éditeur les réchauffe un peu.

Le pipeline est dans `tools/sprites/`, un projet uv à part en Python 3.13 qui garde torch hors de l'app. `uv run build.py` dans ce dossier régénère `assets/claude/` (ffmpeg et node sur le PATH, GPU CUDA de 12 Go) et affiche l'écart de chaque iris à sa cible. Le premier lancement télécharge environ 20 Go de modèles et dessine 23 images en 40 min, les suivants réutilisent les dessins en cache. La vidéo, les images décodées, les poids des modèles, les détourages et les dessins sont gardés dans `tools/sprites/.work/`, ignoré par git. Un dessin est refait quand son prompt ou l'image dont il part change. Ajouter une expression revient à ajouter une ligne à `DRAWINGS` dans `build.py`, qui lui donne aussi son clignement.

Les dessins tournent sur Nunchaku en int4 avec le LoRA Lightning 4 étapes fusionné, 20 blocs sur 60 gardés sur le GPU et les autres chargés depuis la RAM. L'image de départ est agrandie 4 fois par Real-ESRGAN anime et le dessin est fait au double du canevas, pour que bouches et yeux restent nets : 90 s par image et 10,3 Gio au plus. `edit.py` corrige Nunchaku 1.3, plus ancien que 2511 et que diffusers 0.41 : rang SVD propre à chaque couche du checkpoint, et modulation au pas de temps 0 des jetons de l'image de référence (`zero_cond_t`).

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
- `--agents` passe par `cmd.exe` avec le reste de la commande : le texte de l'agent ne doit contenir aucun de `& | < > ^ % ( )`.
- Un `/compact` tapé ne déclenche pas `UserPromptSubmit` : seulement `PreCompact` et `PostCompact` (`trigger: manual`), avec un `SubagentStop` sans `SubagentStart` pour l'agent qui résume. Claude Code compacte aussi seul pendant un tour (`trigger: auto`).
- Channels exige `--dangerously-load-development-channels`, qui pose une question interactive : inutilisable en session cachée pour l'instant.
- Whisper : `large-v3-turbo` (0,5 s) ou `small` (0,2 s) en `int8_float16` sur CUDA, `beam_size=1`, `condition_on_previous_text=False`, audio passé en numpy (le décodage par PyAV plante). cuDNN vient de la roue de ctranslate2, cuBLAS du CUDA Toolkit 12 sur le PATH.
- Silero VAD : trames de 512 échantillons à 16 kHz, sortie 1-D.
- Picovoice n'a plus d'offre gratuite et le modèle openWakeWord "hey claude" n'existe qu'en anglais.
- Mesuré : démarrage de session 5,5 s, réponse simple 2,3 s, tour avec un outil 8,5 s.
- Ctrl+C dans une app Qt : la boucle d'événements ne rend pas la main à Python, d'où `signal.signal(signal.SIGINT, signal.SIG_DFL)`.
- Captures hors écran (`QT_QPA_PLATFORM=offscreen`) : sans `QT_QPA_FONTDIR=C:/Windows/Fonts`, le texte s'affiche en carrés.

