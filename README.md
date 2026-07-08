# Unreal Linux Manager

Application graphique **minimaliste** pour gérer Unreal Engine sur Linux
desktop — pensée d'abord pour **Bazzite / Fedora Atomic** (systèmes immuables),
mais compatible avec Fedora classique, Ubuntu et Arch.

L'interface est volontairement sobre, de style « paramètres système » : des
onglets, des boutons rectangulaires, des tableaux, des champs texte et un
panneau **Journal** en bas. Pas d'animations, pas de thème gamer, pas de CSS
compliqué — elle utilise le thème natif du système.

> **Sécurité et licence.** Ce programme ne demande **jamais** votre mot de
> passe Epic Games et n'en stocke aucun. Toute connexion Epic passe par une
> méthode sécurisée (Legendary + OAuth navigateur). Il ne télécharge ni ne
> redistribue Unreal Engine : le mode principal est l'**import d'un ZIP
> officiel** d'Unreal Engine pour Linux que vous fournissez vous-même.

---

## Fonctionnalités (V1)

- **Compte Epic** — état de connexion, installation et connexion via Legendary
  (OAuth navigateur), mode manuel sans compte. Aucun mot de passe demandé.
- **Moteurs** — scan des installations Unreal, import d'un ZIP officiel Linux
  (avec `chmod +x` automatique du binaire `UnrealEditor`), ajout d'un moteur
  existant, lancement, calcul de taille, setup toolchain C++, et instructions
  de compilation depuis les sources (mode avancé, jamais automatique).
- **Projets** — scan récursif des fichiers `.uproject`, lancement avec le
  moteur choisi, ouverture du dossier, ouverture dans VS Code, génération des
  fichiers projet.
- **Plugins / Assets** — scan des plugins de projet et du dossier Marketplace
  du moteur, ajout d'un plugin local, reconstruction du projet, intégration
  d'Epic Asset Manager (Flatpak).
- **Diagnostics** — OS, système atomic/immuable, `rpm-ostree`, Wayland/X11,
  GPU, Vulkan, RAM, glibc, espace disque, binaire exécutable, VS Code,
  Distrobox, Flatpak. Résultats colorés simplement (OK / Attention / Problème).
- **Paramètres** — dossiers par défaut, éditeur/terminal préféré, moteur par
  défaut, options de lancement (env + arguments), logs détaillés, chemins de
  scan, réinitialisation.
- **Journal** — toutes les commandes système exécutées sont tracées.

---

## Prérequis

- **Python 3.11+** (la configuration TOML utilise `tomllib`).
- **PySide6** (installé automatiquement par `install_local.sh`).
- Un **ZIP officiel d'Unreal Engine pour Linux** (récupéré via votre compte
  Epic / GitHub) pour le mode d'import principal.

Outils optionnels détectés automatiquement s'ils sont présents :
`legendary`, `flatpak`, `distrobox`, `code` (VS Code), `nvidia-smi`,
`glxinfo`, `vulkaninfo`, `rpm-ostree`.

---

## Installation et lancement

```bash
chmod +x install_local.sh run.sh
./install_local.sh
./run.sh
```

`install_local.sh` crée un environnement virtuel **isolé** dans `./.venv` et y
installe PySide6. Rien n'est installé au niveau système : c'est sûr sur les
distributions immuables (Bazzite, Fedora Atomic).

`run.sh` active `./.venv` s'il existe (sinon il utilise le Python système) et
lance l'application.

### Lancement sans script

```bash
python -m pip install -r requirements.txt        # ou dans un venv
PYTHONPATH=src python -m unreal_linux_manager.main
```

---

## Emplacements des fichiers

L'application respecte la spécification XDG et n'écrit jamais en dehors de
votre dossier personnel :

| Usage            | Chemin                                                  |
|------------------|---------------------------------------------------------|
| Configuration    | `~/.config/unreal-linux-manager/config.toml`            |
| Données          | `~/.local/share/unreal-linux-manager/`                  |
| Logs             | `~/.local/state/unreal-linux-manager/logs/`             |
| Moteurs (défaut) | `~/Games/Unreal/Engines/`                               |
| Projets (défaut) | `~/Unreal Projects/`                                    |
| Vault / assets   | `~/Games/Unreal/Vault/`                                 |

Au premier lancement, `data/default_config.toml` est copié vers votre dossier
de configuration ; vous pouvez ensuite l'éditer à la main ou via l'onglet
**Paramètres**.

---

## Utilisation typique

1. **Obtenez** un ZIP officiel d'Unreal Engine pour Linux (via votre compte
   Epic lié à GitHub). Cette application ne le télécharge pas pour vous.
2. Onglet **Moteurs** → *Importer ZIP officiel Unreal Linux* → choisissez le
   ZIP puis le dossier de destination. L'application extrait l'archive, vérifie
   la présence de `Engine/Binaries/Linux/UnrealEditor` et le rend exécutable.
3. Onglet **Projets** → *Scanner* → sélectionnez un projet et le moteur, puis
   *Lancer*.
4. Onglet **Diagnostics** → *Diagnostic* pour vérifier que la machine est prête
   (Vulkan, GPU, RAM, espace disque…).

---

## Notes spécifiques Bazzite / Fedora Atomic

- **N'utilisez pas** `dnf install` sur l'hôte, et évitez `rpm-ostree` sauf en
  dernier recours.
- Préférez **Flatpak**, **AppImage**, **Distrobox**, Homebrew Linux ou des
  fichiers dans votre dossier utilisateur.
- L'application ne lance **aucune** commande privilégiée (`sudo`/`pkexec`) sans
  confirmation explicite, et n'en a pas besoin pour son fonctionnement normal.
- Pour compiler Unreal depuis les sources sur un système immuable, faites-le
  dans un conteneur **Distrobox** (l'onglet Moteurs fournit les commandes).

---

## Architecture

```
unreal-linux-manager/
├── README.md
├── run.sh                     # lancement
├── install_local.sh          # installation locale (venv)
├── requirements.txt
├── pyproject.toml
├── data/
│   └── default_config.toml    # configuration par défaut
└── src/
    └── unreal_linux_manager/
        ├── main.py            # point d'entrée
        ├── app_context.py     # services partagés (config, runner, managers)
        ├── ui/                # onglets PySide6 + Journal + workers QThread
        │   ├── main_window.py
        │   ├── account_tab.py
        │   ├── engines_tab.py
        │   ├── projects_tab.py
        │   ├── plugins_tab.py
        │   ├── diagnostics_tab.py
        │   ├── settings_tab.py
        │   ├── journal.py
        │   ├── workers.py
        │   └── helpers.py
        └── core/              # logique métier sans dépendance Qt
            ├── config.py
            ├── paths.py
            ├── command_runner.py
            ├── system_check.py
            ├── epic_auth.py
            ├── engine_manager.py
            ├── project_manager.py
            ├── plugin_manager.py
            └── unreal_detector.py
```

Le cœur (`core/`) ne dépend pas de Qt : il est testable et réutilisable en
ligne de commande. L'interface (`ui/`) ne bloque jamais : les opérations
longues (scan, extraction ZIP, diagnostics, sous-processus) s'exécutent sur des
`QThread` via `ui/workers.py`, et tout est tracé dans le Journal.

---

## Feuille de route (V2)

- Intégration Legendary plus poussée (liste et téléchargement de la bibliothèque).
- Intégration Epic Asset Manager comme backend d'assets.
- Gestion Marketplace / Fab.
- Téléchargement des versions d'Unreal si un backend fiable existe.
- Création automatique de projets depuis des templates.
- Packaging **AppImage** / **Flatpak**.
- Mode **Distrobox** pour la compilation depuis les sources.
- Raccourcis bureau `.desktop`.

---

## Licence

Code de l'application : MIT (voir en-tête `pyproject.toml`).
Unreal Engine reste soumis à la licence Epic Games — cette application ne
gère que des chemins locaux et ne redistribue aucun fichier du moteur.
