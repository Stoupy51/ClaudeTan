""" The words of the demo video in each language it is made in. """
# Imports
from screenplay import Chapter, Words

# Constants
ENGLISH: Words = Words(
	language="en",
	tagline="Talk to Claude Code. She answers on your screen.",
	outro="Runs on your Claude subscription, with Whisper on your GPU.",
	you="You",
	chapters=(
		Chapter(title="Ask out loud", subtitle="Whisper transcribes you locally, Claude Code does the work"),
		Chapter(title="Permissions by voice", subtitle="Say yes or no without touching the keyboard"),
		Chapter(title="Background work", subtitle="Long tasks go to an agent while she waits as a pill"),
		Chapter(title="Any language", subtitle="Whisper detects it, Claude answers in it"),
	),
	question="Hey Claude, what's on my screen? Done.",
	reply=("You have VS Code open on actions.py, ", "and my icon is by the clock."),
	cleanup="Hey Claude, delete the build folder, over.",
	cleanup_tool="Delete the build folder",
	yes="Yes.",
	cleaned="The build folder is gone, 212 MB freed.",
	dark_mode="Hey Claude, add a dark mode, over.",
	dark_mode_task="Add a dark mode to the settings page",
	handed_off="An agent is on it, I'll tell you when it's done.",
	dark_mode_done="Dark mode is in, and the tests pass.",
	abroad="fr",
	weather_abroad="Hé Claude, quel temps fait-il à Rennes ?",
)
FRENCH: Words = Words(
	language="fr",
	tagline="Parle à Claude Code. Elle te répond à l'écran.",
	outro="Avec ton abonnement Claude, et Whisper sur ton GPU.",
	you="Toi",
	chapters=(
		Chapter(title="Demande à voix haute", subtitle="Whisper te transcrit en local, Claude Code fait le travail"),
		Chapter(title="Permissions à la voix", subtitle="Dis oui ou non sans toucher au clavier"),
		Chapter(title="Travail en arrière-plan", subtitle="Les longues tâches partent à un agent, elle attend en pastille"),
		Chapter(title="Toutes les langues", subtitle="Whisper la détecte, Claude y répond"),
	),
	question="Hé Claude, qu'est-ce qu'il y a sur mon écran ? Terminé.",
	reply=("Tu as VS Code ouvert sur actions.py, ", "et mon icône est près de l'horloge."),
	cleanup="Hé Claude, supprime le dossier build, c'est tout.",
	cleanup_tool="Supprimer le dossier build",
	yes="Oui.",
	cleaned="Le dossier build est supprimé, 212 Mo libérés.",
	dark_mode="Hé Claude, ajoute un mode sombre, c'est tout.",
	dark_mode_task="Ajouter un mode sombre aux réglages",
	handed_off="Un agent s'en charge, je te préviens quand c'est fini.",
	dark_mode_done="Le mode sombre est là, et les tests passent.",
	abroad="en",
	weather_abroad="Hey Claude, what's the weather in London?",
)
LANGUAGES: dict[str, Words] = {"en": ENGLISH, "fr": FRENCH}

