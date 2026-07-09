"""Onglet "Instructions" : des guides simples, écrits pour un utilisateur normal."""

from __future__ import annotations

from PySide6.QtWidgets import (
    QHBoxLayout,
    QListWidget,
    QTextBrowser,
    QWidget,
)

from ..app_context import AppContext

# Each guide is (title, plain-text body). Kept intentionally simple and free of
# jargon so a first-time user can follow along.
_GUIDES: list[tuple[str, str]] = [
    ("Installer Unreal Engine Linux",
     "1. Ouvre l'onglet « Moteurs ».\n"
     "2. Clique sur « Ouvrir la page officielle Unreal Engine ».\n"
     "3. Connecte-toi à ton compte Epic si on te le demande.\n"
     "4. Télécharge la version Linux au format .zip.\n"
     "5. Reviens dans l'application et clique sur\n"
     "   « Importer un ZIP Unreal déjà téléchargé ».\n"
     "6. Choisis le fichier .zip, puis le dossier d'installation.\n"
     "7. Attends la fin de l'extraction.\n"
     "8. Sélectionne le moteur et clique sur « Préparer ce moteur ».\n"
     "9. Clique sur « Lancer ».\n\n"
     "L'application ne télécharge pas Unreal à ta place et ne contourne jamais "
     "la connexion Epic."),

    ("Importer un ZIP Unreal",
     "1. Télécharge le ZIP officiel depuis Epic.\n"
     "2. Onglet « Moteurs » > « Importer un ZIP Unreal déjà téléchargé ».\n"
     "3. Choisis le fichier ZIP.\n"
     "4. Choisis le dossier d'installation.\n"
     "5. Attends l'extraction (cela peut prendre du temps).\n"
     "6. Clique sur « Préparer ce moteur ».\n"
     "7. Clique sur « Lancer ».\n\n"
     "L'application vérifie que le fichier\n"
     "Engine/Binaries/Linux/UnrealEditor existe et le rend exécutable."),

    ("Lancer un projet",
     "1. Onglet « Projets » > « Scanner ».\n"
     "2. Sélectionne ton projet dans la liste.\n"
     "3. Choisis le moteur à utiliser dans la liste déroulante en haut.\n"
     "4. Clique sur « Lancer avec le moteur sélectionné ».\n\n"
     "Astuce : tu peux définir un moteur par défaut avec le bouton\n"
     "« Définir par défaut »."),

    ("Installer / ajouter un plugin",
     "1. Onglet « Plugins / Assets ».\n"
     "2. Choisis le projet concerné en haut.\n"
     "3. Clique sur « Ajouter plugin local ».\n"
     "4. Sélectionne le dossier du plugin (il doit contenir un fichier .uplugin).\n"
     "5. L'application copie le plugin dans Projet/Plugins/.\n"
     "6. Clique sur « Reconstruire projet / GenerateProjectFiles » si besoin.\n\n"
     "Pour les assets du Marketplace/Fab, utilise Epic Asset Manager\n"
     "(bouton dédié dans le même onglet)."),

    ("Se connecter à Epic avec Legendary",
     "1. Onglet « Compte Epic ».\n"
     "2. Clique sur « Vérifier Legendary ». S'il est absent,\n"
     "   clique sur « Installer Legendary » (installation sans sudo).\n"
     "3. Essaie « Connexion automatique Legendary » : une page Epic\n"
     "   s'ouvre dans ton navigateur.\n"
     "4. Si ça ne marche pas, utilise « Connexion manuelle avec code » :\n"
     "   - Ouvre la page de connexion.\n"
     "   - Connecte-toi ; Epic affiche une page JSON.\n"
     "   - Copie la valeur « authorizationCode ».\n"
     "   - Colle-la dans le champ et clique sur « Valider le code ».\n"
     "5. Clique sur « Tester la connexion ».\n\n"
     "L'application ne te demande jamais ton mot de passe Epic et ne stocke\n"
     "aucun identifiant : c'est Legendary qui gère la session."),

    ("Vérifier les dépendances",
     "1. Onglet « Dépendances ».\n"
     "2. Clique sur « Vérifier les dépendances ».\n"
     "3. Lis le tableau :\n"
     "   - OK : présent.\n"
     "   - Manquant : à installer.\n"
     "   - Optionnel : utile mais pas obligatoire.\n"
     "   - Problème : à corriger avant Unreal (ex : Vulkan).\n"
     "   - Non applicable : ne te concerne pas (ex : pas de GPU NVIDIA).\n"
     "4. Clique sur « Installer les dépendances manquantes ».\n"
     "5. Choisis « Simuler » pour voir les commandes sans rien changer,\n"
     "   ou « Installer » pour les exécuter."),

    ("Que faire si Unreal ne se lance pas",
     "- Sélectionne le moteur et clique sur « Préparer ce moteur » :\n"
     "  cela corrige le bit exécutable de UnrealEditor.\n"
     "- Onglet « Dépendances » : vérifie que Vulkan est « OK ».\n"
     "  Si Vulkan est en « Problème », corrige le pilote GPU d'abord.\n"
     "- Onglet « Diagnostics » : lance un diagnostic complet et lis les\n"
     "  recommandations.\n"
     "- Vérifie l'espace disque libre (un moteur peut dépasser 100 Go).\n"
     "- Regarde le Journal en bas de la fenêtre pour le message d'erreur exact."),

    ("Bazzite : ce qu'il ne faut pas faire",
     "Bazzite et Fedora Atomic sont des systèmes « immuables ».\n\n"
     "À ÉVITER :\n"
     "- N'utilise pas « dnf install » directement sur le système hôte.\n"
     "- Évite « rpm-ostree » sauf si c'est vraiment indispensable\n"
     "  (il modifie l'image système et demande un redémarrage).\n\n"
     "À PRÉFÉRER :\n"
     "- Flatpak pour les applications graphiques (VS Code, Epic Asset Manager).\n"
     "- Homebrew ou Distrobox pour les outils en ligne de commande.\n"
     "- Les fichiers dans ton dossier personnel (dont les moteurs Unreal).\n\n"
     "L'application applique déjà ces priorités automatiquement dans l'onglet\n"
     "« Dépendances »."),
]


class InstructionsTab(QWidget):
    def __init__(self, ctx: AppContext, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._ctx = ctx
        self._build_ui()

    def _build_ui(self) -> None:
        layout = QHBoxLayout(self)

        self._list = QListWidget()
        self._list.setMaximumWidth(280)
        for title, _body in _GUIDES:
            self._list.addItem(title)
        layout.addWidget(self._list)

        self._view = QTextBrowser()
        self._view.setOpenExternalLinks(True)
        self._view.setMinimumHeight(320)
        layout.addWidget(self._view)

        self._list.currentRowChanged.connect(self._show_guide)
        self._list.setCurrentRow(0)

    def _show_guide(self, index: int) -> None:
        if 0 <= index < len(_GUIDES):
            title, body = _GUIDES[index]
            self._view.setPlainText(f"{title}\n{'=' * len(title)}\n\n{body}")
