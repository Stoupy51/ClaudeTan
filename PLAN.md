
# ClaudeTan : plan

Assistant vocal personnel branché sur l'abonnement Claude (pas l'API). On dit "Hey Claude", une session Claude Code cachée exécute la demande, et Claude-tan apparaît à l'écran pour réagir. Un clic sur elle ouvre le Remote Control, un appui long la déplace.

Personnage tiré de la vidéo https://www.youtube.com/watch?v=_m38WbRlzv0 (Bright Mirror), usage personnel uniquement.

## Décisions

| Sujet | Choix |
| :- | :- |
| Mot d'activation | Whisper transcrit chaque phrase et une regex repère "Hey Claude" (FR et EN). Un vrai modèle de mot d'activation viendra plus tard. Le GPU travaille dès que quelqu'un parle près du micro, vidéos comprises. |
| Réponse | Bulle de texte et voix (TTS), la voix se coupe dans la config. |
| Permissions | Session en `--permission-mode auto`. Ce que le classifieur bloque passe par Claude-tan ou par le Remote Control. |
| Conversation | Persistante (`claude --continue`), compactée (`/compact`) à l'arrêt de l'app et après 55 min sans activité. |
| Modèle | A décider, voir [Modèle](#modèle). Proposition : Sonnet 5.5 par défaut, Opus 5.5 à la demande. |

Les 55 min viennent du cache de prompt, qui dure 1 h sur abonnement. `/compact` relit toute la conversation : tant que le cache est chaud, cette lecture coûte le tarif réduit du cache.

## Architecture

Une seule app Python (PySide6) en quatre parties :

- **voice** : micro, Silero VAD, faster-whisper sur le GPU, regex du mot d'activation. Produit une commande texte.
- **session** : Claude Code dans un pseudo-terminal caché (pywinpty) avec `--remote-control` et des hooks HTTP vers l'app. Les commandes y sont tapées comme au clavier.
- **avatar** : l'overlay, qui traduit l'état de la session en expression, bulle et voix.
- **tray** : icône de notification, config TOML, démarrage avec Windows.

Les hooks donnent l'état de la session, l'état choisit l'expression :

| Événement | État | Expression |
| :- | :- | :- |
| commande reconnue | écoute | `hello`, puis `idle` |
| `UserPromptSubmit` | réfléchit | `point` |
| `PreToolUse`, `PostToolUse` | travaille | `idle` (une expression `working` reste à créer) |
| `PermissionRequest`, `Notification` de type `permission_prompt` | demande | `please`, puis `thanks` si accepté |
| `MessageDisplay` | parle | `idle` et bouche animée |
| `Stop` | terminé | `present` ou `happy` |
| `StopFailure` | erreur | `surprised` |

## Étapes

### 0. Prototypes (fait)

- [x] `prototypes/session_demo.py` : session Remote Control cachée, envoi de prompts avec accents, événements des hooks.
- [x] `prototypes/voice_demo.py` : VAD, Whisper, mot d'activation et commande, 10/10 sur des clips FR et EN.
- [x] `prototypes/overlay_demo.py` : overlay, clignement, bouche, bulle, clic, appui long, Ctrl+C.
- [x] Sprites sur un seul canevas, yeux alignés, couleurs uniformisées (voir [Sprites](#sprites)).

### 1. MVP

- [ ] Une app qui relie voix, session et avatar par une machine à états.
- [ ] N'envoyer une commande que si la session est au repos (`Stop` reçu), sinon la mettre en file : taper pendant qu'un dialogue est ouvert casse la session.
- [ ] Lancer `claude --continue` depuis un dossier dédié, puisque `--continue` reprend la dernière conversation du dossier courant.
- [ ] Gérer au démarrage le dialogue "reprendre depuis un résumé" que Claude Code affiche sur Pro quand une grosse session reprend après une longue pause.
- [ ] `/compact` à l'arrêt et après 55 min d'inactivité, seulement quand le contexte est gros (estimé via le `transcript_path` des hooks), car la compaction est elle-même une grosse requête.
- [ ] Clic sur Claude-tan : ouvrir l'URL de session lue dans le terminal caché.
- [ ] Config TOML : langue, regex d'activation, modèle, voix on/off, position.
- [ ] Icône de notification et démarrage avec Windows.

### 2. Voix et contrôle

- [ ] TTS Edge (`fr-FR-VivienneMultilingualNeural`, `DeniseNeural`, `HenriNeural`, `RemyMultilingualNeural`), désactivable, bouche synchronisée sur l'amplitude.
- [ ] Commandes vocales "stop", "annule", "passe en Opus" (`/model opus`).
- [ ] Accepter ou refuser une permission à la voix, en répondant au hook `PermissionRequest`.

### 3. Avatar

- [ ] Expressions manquantes : travaille, réfléchit de face, triste ou erreur. Piste spéculative : éditer `idle` avec un modèle d'édition d'image (FLUX Kontext, Qwen-Image-Edit), puis passer le résultat dans le pipeline.
- [ ] Clignement et bouche sur toutes les poses, pas seulement `idle` et `hello`.
- [ ] Ranger le pipeline de sprites dans `tools/sprites/` pour pouvoir ajouter des expressions.

### 4. Plus tard

- [ ] Channels (serveur MCP) quand la fonction sortira de la research preview, pour ne plus taper dans le terminal.
- [ ] Modèle de mot d'activation dédié en FR (livekit-wakeword), pour ne plus réveiller Whisper à chaque phrase.

## Sprites

`assets/claude/` contient 16 PNG de 850x608 px. Dans toutes les images de face, les iris tombent sur les mêmes pixels à 0,3 px près : gauche (382,4 ; 288,9), droit (467,6 ; 271,1). `point` regarde de côté, ce sont donc ses yeux et non ses iris qui sont alignés.

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

Les scripts (`kit.py`, `build.py`, `color.py`, `rig.py`, `verify.py`) sont dans le dossier temporaire de Claude Code, `%TEMP%\claude\d--advanced-desktop-ClaudeTan\2d8c2515-c16e-4d3d-9d4d-c4461e549943\scratchpad\tools`. La vidéo 4K, son environnement Python (torch) et le modèle de visage anime sont dans `%TEMP%\claude\d--advanced-desktop-ClaudeAssist\0b8c00f0-0796-4834-b828-b23e6e3d1148\scratchpad`. Windows peut vider ces dossiers : l'étape 3 les rapatrie.

## Modèle

Sur Pro, la fenêtre de 5 h et la limite hebdomadaire sont communes à claude.ai et à Claude Code. Un modèle plus cher par token consomme la limite plus vite ; Anthropic ne publie pas le ratio exact, l'écart des prix API en donne l'ordre de grandeur.

| Modèle | Prix API, entrée / sortie ($ par million de tokens) | Pour l'assistant |
| :- | :- | :- |
| Haiku 5.5 | à partir de 0,10 / 0,50 | Le plus rapide, fait pour trier et router. Bien pour "ouvre Spotify", trop léger pour du vrai code. |
| Sonnet 5.5 | 2 / 10 | Rapide et capable : le bon défaut pour un assistant vocal. |
| Opus 5.5 | 4 / 20 | Défaut de Claude Code sur Pro. Pour les vraies tâches de code, à la demande. |
| Fable 5.1 | 10 / 50 | Longues tâches autonomes, lent, et facturable en crédits d'usage hors abonnement. Pas pour l'assistant. |

Les quatre acceptent le mode `auto`.

## Points d'attention

- Le repo est public alors que `assets/claude/` contient l'art de Bright Mirror : passer le repo en privé, ou retirer les PNG du suivi et de l'historique.
- `prototypes/__pycache__/` est suivi par git et change à chaque lancement : le retirer et ajouter un `.gitignore`.
- Noms à aligner sur ClaudeTan : `claude-assist` (pyproject), `ClaudeAssist` (QSettings), "Claude Assist" (nom de session), `claude_assist_hooks.json`.
- Sessions Remote Control de test à archiver sur claude.ai : "ClaudeAssist (test)" et "Claude Assist".

## Notes techniques

- L'abonnement ne fonctionne que dans Claude Code et claude.ai. L'app pilote donc le vrai CLI dans un pseudo-terminal, ce qui reste conforme.
- pywinpty : passer argv en liste (une chaîne garde ses guillemets) et lancer via `cmd.exe /c chcp 65001 >nul && claude ...`, sinon les accents arrivent en cp850.
- Retirer les variables d'une session imbriquée (`CLAUDECODE`, `CLAUDE_CODE_ENTRYPOINT`, `CLAUDE_CODE_SESSION_ID`, `CLAUDE_CODE_CHILD_SESSION`, `CLAUDE_CODE_MESSAGING_SOCKET`, `CLAUDE_CODE_MESSAGING_TOKEN`, `CLAUDE_PID`) avant de lancer `claude`.
- Répondre `\r` au dialogue de confiance du dossier. Pour envoyer un prompt : le taper, attendre 0,4 s, puis `\r`.
- Hooks `type: "http"` déclarés dans un fichier passé par `--settings`. `SessionStart` ne s'est pas déclenché en HTTP pendant les tests.
- Channels exige `--dangerously-load-development-channels`, qui pose une question interactive : inutilisable en session cachée pour l'instant.
- Whisper : `large-v3-turbo` (0,5 s) ou `small` (0,2 s) en `int8_float16` sur CUDA, `beam_size=1`, `condition_on_previous_text=False`, audio passé en numpy (le décodage par PyAV plante).
- Silero VAD : trames de 512 échantillons à 16 kHz, sortie 1-D.
- Picovoice n'a plus d'offre gratuite et le modèle openWakeWord "hey claude" n'existe qu'en anglais.
- Mesuré : démarrage de session 5,5 s, réponse simple 2,3 s, tour avec un outil 8,5 s.
- Ctrl+C dans une app Qt : la boucle d'événements ne rend pas la main à Python, d'où `signal.signal(signal.SIGINT, signal.SIG_DFL)`.

