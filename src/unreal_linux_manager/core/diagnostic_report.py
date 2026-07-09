"""Build a human-readable, sectioned diagnostic report.

The report deliberately contains **no** Epic tokens or other secrets — only the
account username (if Legendary reports it) and boolean connection state.
"""

from __future__ import annotations

from datetime import datetime

from . import dependency_manager as dm
from .system_check import CheckResult


def _find(results: list[CheckResult], name_contains: str) -> CheckResult | None:
    for r in results:
        if name_contains.lower() in r.name.lower():
            return r
    return None


def _dep(results: list["dm.DependencyResult"], key: str):
    for r in results:
        if r.dependency.key == key:
            return r
    return None


def build_report(
    *,
    os_info: "dm.OSInfo",
    sys_results: list[CheckResult],
    dep_results: list["dm.DependencyResult"],
    engines: list,
    projects: list,
    epic_state,
    config,
) -> str:
    """Assemble the full diagnostic text from already-gathered data."""
    lines: list[str] = []
    add = lines.append

    add("Rapport de diagnostic — Unreal Linux Manager")
    add("=" * 46)
    add(f"Généré le : {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    add("")

    # --- Système ----------------------------------------------------------- #
    add("Système")
    add("-" * 7)
    add(f"* OS : {os_info.pretty_name or os_info.label}")
    add(f"* Type : {os_info.label}")
    session = _find(sys_results, "affichage")
    add(f"* Session : {session.detail if session else 'inconnue'}")
    add(f"* Flatpak : {'OK' if os_info.has_flatpak else 'absent'}")
    add(f"* Distrobox : {'OK' if os_info.has_distrobox else 'absent'}")
    add(f"* Homebrew : {'OK' if os_info.has_brew else 'absent'}")
    if os_info.has_rpm_ostree:
        add("* rpm-ostree : présent, mais à éviter sauf nécessité")
    add("")

    # --- GPU / Vulkan ------------------------------------------------------ #
    add("GPU / Vulkan")
    add("-" * 12)
    gpu = _find(sys_results, "GPU")
    add(f"* GPU : {gpu.detail if gpu else 'inconnu'}")
    nvidia = _dep(dep_results, "nvidia-smi")
    if nvidia:
        add(f"* nvidia-smi : {nvidia.status_label} — {nvidia.detail}")
    vulkan_dep = _dep(dep_results, "vulkaninfo")
    if vulkan_dep:
        add(f"* Vulkan : {vulkan_dep.status_label} — {vulkan_dep.detail}")
    add("")

    # --- Unreal Engine ----------------------------------------------------- #
    add("Unreal Engine")
    add("-" * 13)
    add(f"* Moteurs trouvés : {len(engines)}")
    for eng in engines:
        exec_ok = "exécutable" if getattr(eng, "exists", False) else "NON exécutable"
        add(f"    - {eng.name} ({exec_ok})")
    disk = _find(sys_results, "disque")
    if disk:
        add(f"* Espace disque : {disk.status.upper()} — {disk.detail}")
    ram = _find(sys_results, "vive")
    if ram:
        add(f"* Mémoire vive : {ram.status.upper()} — {ram.detail}")
    add("")

    # --- Projets ----------------------------------------------------------- #
    add("Projets")
    add("-" * 7)
    add(f"* Projets trouvés : {len(projects)}")
    for proj in projects[:20]:
        assoc = getattr(proj, "engine_association", "") or "—"
        add(f"    - {proj.name} (moteur : {assoc})")
    add("")

    # --- Compte Epic / Legendary ------------------------------------------ #
    add("Compte Epic / Legendary")
    add("-" * 23)
    from .epic_auth import EpicAuth

    legendary = EpicAuth.find_legendary()
    add(f"* Legendary : {legendary or 'introuvable'}")
    add(f"* Connexion : {'Connecté' if epic_state.logged_in else 'Non connecté'}")
    if epic_state.username:
        add(f"* Compte : {epic_state.username}")
    if not epic_state.logged_in:
        add("* Action proposée : Connexion manuelle via navigateur "
            "(onglet Compte Epic).")
    add("")

    # --- Dépendances ------------------------------------------------------- #
    add("Dépendances")
    add("-" * 11)
    critical = [r for r in dep_results
                if r.status in (dm.STATUS_MISSING, dm.STATUS_PROBLEM)
                and not r.dependency.optional]
    optional_missing = [r for r in dep_results if r.status == dm.STATUS_OPTIONAL]
    if critical:
        add("* Manquantes / problématiques (importantes) :")
        for r in critical:
            add(f"    - {r.dependency.display} : {r.status_label}")
    else:
        add("* Aucune dépendance importante manquante.")
    if optional_missing:
        add("* Optionnelles absentes : "
            + ", ".join(r.dependency.display for r in optional_missing))
    add("")

    # --- Recommandations --------------------------------------------------- #
    add("Recommandations")
    add("-" * 15)
    recs: list[str] = []
    if not engines:
        recs.append("Télécharge Unreal Linux depuis la page officielle, puis "
                    "importe le ZIP (onglet Moteurs).")
    if os_info.atomic:
        recs.append("Sur Bazzite / Fedora Atomic, évite rpm-ostree sauf si "
                    "indispensable ; préfère Flatpak, Homebrew ou Distrobox.")
    if vulkan_dep and vulkan_dep.status in (dm.STATUS_MISSING, dm.STATUS_PROBLEM):
        recs.append("Si Vulkan échoue ou est manquant, vérifie le pilote GPU "
                    "avant de lancer Unreal.")
    if ram and ram.status in ("warn", "error"):
        recs.append("Ajoute de la mémoire vive si possible : 16 Gio minimum, "
                    "32 Gio recommandé pour Unreal.")
    if disk and disk.status in ("warn", "error"):
        recs.append("Libère de l'espace disque : un moteur + projets peut "
                    "dépasser 100 Gio.")
    if not legendary:
        recs.append("Installe Legendary (onglet Compte Epic) pour te connecter "
                    "à Epic, ou reste en mode manuel (import ZIP).")
    if not recs:
        recs.append("Ton système semble prêt pour Unreal Engine. Bon dev !")
    for rec in recs:
        add(f"* {rec}")
    add("")

    return "\n".join(lines)
