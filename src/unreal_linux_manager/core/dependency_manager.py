"""Detect and (with the user's consent) install the Linux dependencies that
Unreal Engine needs.

Design goals
------------
* **Never** run a system-modifying command silently. Every install plan is
  shown to the user first, and privileged steps (``sudo`` / ``rpm-ostree``)
  require explicit confirmation and support a dry-run.
* On immutable / atomic distributions (Bazzite, Fedora Atomic) prefer, in
  order: already-present tools → Flatpak (GUI apps) → Homebrew / Distrobox
  (CLI tools) → ``rpm-ostree`` only as a last resort, with a loud warning that
  it changes the system image and may need a reboot.
* Distinguish *why* a dependency matters: running Unreal, compiling C++,
  diagnostics, or optional comfort.

This module is Qt-free so it can be unit-tested headless.
"""

from __future__ import annotations

import glob
import platform
from dataclasses import dataclass, field
from pathlib import Path

from . import paths
from .command_runner import CommandRunner, which

# --------------------------------------------------------------------------- #
# Status and category vocabulary
# --------------------------------------------------------------------------- #
STATUS_OK = "ok"
STATUS_MISSING = "missing"
STATUS_OPTIONAL = "optional"
STATUS_PROBLEM = "problem"
STATUS_NA = "na"  # non applicable

STATUS_LABELS = {
    STATUS_OK: "OK",
    STATUS_MISSING: "Manquant",
    STATUS_OPTIONAL: "Optionnel",
    STATUS_PROBLEM: "Problème",
    STATUS_NA: "Non applicable",
}

# Why a dependency matters.
CAT_SYSTEM = "systeme"        # base system / package managers
CAT_RUN = "lancement"         # needed to run Unreal
CAT_COMPILE = "compilation"   # needed to compile C++ / build source
CAT_DIAGNOSE = "diagnostic"   # tools used to diagnose the machine
CAT_OPTIONAL = "confort"      # optional comfort tools

# Distribution families.
FAMILY_FEDORA = "fedora"
FAMILY_UBUNTU = "ubuntu"
FAMILY_ARCH = "arch"
FAMILY_UNKNOWN = "unknown"


# --------------------------------------------------------------------------- #
# OS detection
# --------------------------------------------------------------------------- #
@dataclass
class OSInfo:
    os_id: str = ""
    id_like: str = ""
    variant_id: str = ""
    pretty_name: str = ""
    family: str = FAMILY_UNKNOWN
    atomic: bool = False
    is_bazzite: bool = False
    has_rpm_ostree: bool = False
    has_flatpak: bool = False
    has_distrobox: bool = False
    has_brew: bool = False
    has_xdg_open: bool = False

    @property
    def label(self) -> str:
        if self.is_bazzite:
            base = "Bazzite"
        elif self.atomic and self.family == FAMILY_FEDORA:
            base = "Fedora Atomic"
        elif self.family == FAMILY_FEDORA:
            base = "Fedora"
        elif self.family == FAMILY_UBUNTU:
            base = "Ubuntu/Debian"
        elif self.family == FAMILY_ARCH:
            base = "Arch"
        else:
            base = self.pretty_name or "Linux"
        return base


def _read_os_release() -> dict[str, str]:
    data: dict[str, str] = {}
    path = Path("/etc/os-release")
    if not path.is_file():
        return data
    try:
        for line in path.read_text(encoding="utf-8").splitlines():
            if "=" in line and not line.startswith("#"):
                key, _, value = line.partition("=")
                data[key.strip()] = value.strip().strip('"')
    except OSError:
        pass
    return data


def detect_os() -> OSInfo:
    """Identify the distribution family and available package managers."""
    rel = _read_os_release()
    os_id = rel.get("ID", "").lower()
    id_like = rel.get("ID_LIKE", "").lower()
    variant_id = rel.get("VARIANT_ID", "").lower()
    pretty = rel.get("PRETTY_NAME", "") or rel.get("NAME", "")

    haystack = f"{os_id} {id_like} {variant_id} {pretty}".lower()

    if "arch" in haystack or "manjaro" in haystack:
        family = FAMILY_ARCH
    elif any(t in haystack for t in ("ubuntu", "debian", "mint", "pop")):
        family = FAMILY_UBUNTU
    elif any(t in haystack for t in ("fedora", "bazzite", "rhel", "centos", "nobara")):
        family = FAMILY_FEDORA
    else:
        family = FAMILY_UNKNOWN

    is_bazzite = "bazzite" in haystack
    has_rpm_ostree = which("rpm-ostree") is not None
    atomic = (
        is_bazzite
        or any(t in haystack for t in ("silverblue", "kinoite", "atomic", "sericea"))
        or Path("/run/ostree-booted").exists()
        or has_rpm_ostree
    )

    return OSInfo(
        os_id=os_id,
        id_like=id_like,
        variant_id=variant_id,
        pretty_name=pretty,
        family=family,
        atomic=atomic,
        is_bazzite=is_bazzite,
        has_rpm_ostree=has_rpm_ostree,
        has_flatpak=which("flatpak") is not None,
        has_distrobox=which("distrobox") is not None,
        has_brew=which("brew") is not None,
        has_xdg_open=which("xdg-open") is not None,
    )


def is_bazzite_or_atomic(os_info: OSInfo | None = None) -> bool:
    info = os_info or detect_os()
    return info.atomic or info.is_bazzite


# --------------------------------------------------------------------------- #
# Dependency catalogue
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class Dependency:
    """A single tool/library the app can detect and (optionally) install."""

    key: str
    display: str
    binary: str                       # binary looked up on PATH ("" = custom)
    category: str
    purpose: str
    # Package name per distribution family (for classic package managers).
    packages: dict[str, str] = field(default_factory=dict)
    brew: str = ""                    # Homebrew formula (atomic CLI fallback)
    flatpak: str = ""                 # Flatpak id (GUI apps)
    installable: bool = True
    optional: bool = False            # missing -> OPTIONAL, not MISSING

    def package_for(self, family: str) -> str:
        return self.packages.get(family, "")


# Package tables come straight from the V2 spec.
_ALL_FAMILIES_VULKAN = {
    FAMILY_FEDORA: "vulkan-tools",
    FAMILY_UBUNTU: "vulkan-tools",
    FAMILY_ARCH: "vulkan-tools",
}
_MESA_DEMOS = {
    FAMILY_FEDORA: "mesa-demos",
    FAMILY_UBUNTU: "mesa-utils",
    FAMILY_ARCH: "mesa-utils",
}
_PCIUTILS = {FAMILY_FEDORA: "pciutils", FAMILY_UBUNTU: "pciutils", FAMILY_ARCH: "pciutils"}
_PROCPS = {FAMILY_FEDORA: "procps-ng", FAMILY_UBUNTU: "procps", FAMILY_ARCH: "procps-ng"}


def _pkg(fedora: str, ubuntu: str, arch: str) -> dict[str, str]:
    return {FAMILY_FEDORA: fedora, FAMILY_UBUNTU: ubuntu, FAMILY_ARCH: arch}


DEPENDENCIES: list[Dependency] = [
    # --- diagnostics / GPU ------------------------------------------------- #
    Dependency("vulkaninfo", "vulkaninfo", "vulkaninfo", CAT_DIAGNOSE,
               "Vérifie que Vulkan fonctionne sur votre GPU (requis par Unreal 5).",
               packages=_ALL_FAMILIES_VULKAN),
    Dependency("glxinfo", "glxinfo", "glxinfo", CAT_DIAGNOSE,
               "Affiche les informations OpenGL / le nom du GPU.",
               packages=_MESA_DEMOS),
    Dependency("pciutils", "lspci (pciutils)", "lspci", CAT_DIAGNOSE,
               "Liste le matériel PCI (utile pour identifier le GPU).",
               packages=_PCIUTILS),
    Dependency("procps", "ps/free (procps)", "free", CAT_DIAGNOSE,
               "Outils système de base (mémoire, processus).",
               packages=_PROCPS),
    # --- base tools -------------------------------------------------------- #
    Dependency("git", "git", "git", CAT_COMPILE,
               "Nécessaire pour cloner/compiler Unreal depuis les sources.",
               packages=_pkg("git", "git", "git"), brew="git"),
    Dependency("cmake", "cmake", "cmake", CAT_COMPILE,
               "Système de build utilisé par certains modules/plugins.",
               packages=_pkg("cmake", "cmake", "cmake"), brew="cmake"),
    Dependency("make", "make", "make", CAT_COMPILE,
               "Nécessaire pour compiler Unreal / des plugins C++.",
               packages=_pkg("make", "make", "make"), brew="make"),
    Dependency("clang", "clang", "clang", CAT_COMPILE,
               "Compilateur C++ requis pour builder Unreal depuis les sources.",
               packages=_pkg("clang", "clang", "clang"), brew="llvm"),
    Dependency("lld", "lld", "ld.lld", CAT_COMPILE,
               "Éditeur de liens LLVM utilisé lors de la compilation d'Unreal.",
               packages=_pkg("lld", "lld", "lld"), brew="lld"),
    Dependency("python3", "python3", "python3", CAT_RUN,
               "Interpréteur Python (scripts Unreal et cette application).",
               packages=_pkg("python3", "python3", "python"), brew="python"),
    Dependency("pip", "pip (python3-pip)", "pip3", CAT_OPTIONAL,
               "Gestionnaire de paquets Python (installe pipx, Legendary…).",
               packages=_pkg("python3-pip", "python3-pip", "python-pip"),
               optional=True),
    Dependency("pipx", "pipx", "pipx", CAT_OPTIONAL,
               "Installe des outils Python isolés (recommandé pour Legendary).",
               packages=_pkg("pipx", "pipx", "python-pipx"), brew="pipx",
               optional=True),
    Dependency("unzip", "unzip", "unzip", CAT_RUN,
               "Décompresse les archives ZIP (import d'un moteur Unreal).",
               packages=_pkg("unzip", "unzip", "unzip"), brew="unzip"),
    Dependency("tar", "tar", "tar", CAT_RUN,
               "Décompresse les archives tar.",
               packages=_pkg("tar", "tar", "tar")),
    Dependency("rsync", "rsync", "rsync", CAT_OPTIONAL,
               "Copie/synchronise des fichiers efficacement.",
               packages=_pkg("rsync", "rsync", "rsync"), brew="rsync", optional=True),
    Dependency("curl", "curl", "curl", CAT_OPTIONAL,
               "Télécharge des fichiers en ligne de commande.",
               packages=_pkg("curl", "curl", "curl"), brew="curl", optional=True),
    Dependency("wget", "wget", "wget", CAT_OPTIONAL,
               "Télécharge des fichiers en ligne de commande.",
               packages=_pkg("wget", "wget", "wget"), brew="wget", optional=True),
    Dependency("xdg-open", "xdg-open (xdg-utils)", "xdg-open", CAT_RUN,
               "Ouvre des dossiers/URL dans les applications par défaut.",
               packages=_pkg("xdg-utils", "xdg-utils", "xdg-utils")),
    # --- development / editors -------------------------------------------- #
    Dependency("code", "VS Code", "code", CAT_OPTIONAL,
               "Éditeur de code pour le C++/Blueprints (optionnel).",
               flatpak="com.visualstudio.code", optional=True),
    Dependency("rider", "JetBrains Rider", "rider", CAT_OPTIONAL,
               "IDE alternatif pour Unreal C++ (optionnel).",
               installable=False, optional=True),
    Dependency("mono", "mono", "mono", CAT_OPTIONAL,
               "Runtime Mono ; rarement nécessaire, ne pas installer sans raison.",
               installable=False, optional=True),
    Dependency("dotnet", ".NET (dotnet)", "dotnet", CAT_OPTIONAL,
               "Runtime .NET ; rarement nécessaire, ne pas installer sans raison.",
               installable=False, optional=True),
]


# --------------------------------------------------------------------------- #
# Hardware helpers
# --------------------------------------------------------------------------- #
def has_nvidia_gpu() -> bool:
    """Detect an NVIDIA GPU via sysfs PCI vendor IDs (0x10de)."""
    for vendor_file in glob.glob("/sys/bus/pci/devices/*/vendor"):
        try:
            if Path(vendor_file).read_text().strip().lower() == "0x10de":
                # Confirm it is a display/VGA class device when possible.
                class_file = Path(vendor_file).with_name("class")
                if class_file.is_file():
                    dev_class = class_file.read_text().strip().lower()
                    if dev_class.startswith("0x03"):  # display controller
                        return True
                else:
                    return True
        except OSError:
            continue
    return which("nvidia-smi") is not None


def total_ram_bytes() -> int:
    try:
        import os

        pages = os.sysconf("SC_PHYS_PAGES")
        page_size = os.sysconf("SC_PAGE_SIZE")
        if pages > 0 and page_size > 0:
            return pages * page_size
    except (ValueError, OSError):
        pass
    try:
        for line in Path("/proc/meminfo").read_text().splitlines():
            if line.startswith("MemTotal:"):
                return int(line.split()[1]) * 1024
    except (OSError, ValueError, IndexError):
        pass
    return 0


# --------------------------------------------------------------------------- #
# Dependency checking
# --------------------------------------------------------------------------- #
@dataclass
class DependencyResult:
    dependency: Dependency
    status: str
    detail: str = ""
    hint: str = ""

    @property
    def status_label(self) -> str:
        return STATUS_LABELS.get(self.status, self.status)

    @property
    def can_install(self) -> bool:
        return (
            self.status in (STATUS_MISSING, STATUS_OPTIONAL)
            and self.dependency.installable
        )


class DependencyManager:
    """Facade the GUI uses to check and install dependencies."""

    def __init__(self, runner: CommandRunner) -> None:
        self._runner = runner
        self._os_info: OSInfo | None = None

    # -- OS ----------------------------------------------------------------- #
    def os_info(self, refresh: bool = False) -> OSInfo:
        if self._os_info is None or refresh:
            self._os_info = detect_os()
        return self._os_info

    def is_bazzite_or_atomic(self) -> bool:
        return is_bazzite_or_atomic(self.os_info())

    # -- checks ------------------------------------------------------------- #
    def _vulkan_status(self, dep: Dependency) -> DependencyResult:
        """Special handling for Vulkan: distinguish missing vs. broken."""
        if which("vulkaninfo") is None:
            return DependencyResult(
                dep, STATUS_MISSING,
                "L'outil 'vulkaninfo' est absent.",
                "Installez 'vulkan-tools' pour vérifier Vulkan. Unreal 5 "
                "requiert un GPU compatible Vulkan.",
            )
        result = self._runner.run(["vulkaninfo", "--summary"], timeout=30)
        if result.ok and "deviceName" in result.stdout:
            device = next(
                (l.split("=", 1)[-1].strip()
                 for l in result.stdout.splitlines() if "deviceName" in l),
                "",
            )
            return DependencyResult(dep, STATUS_OK,
                                    f"Vulkan opérationnel. {device}".strip())
        return DependencyResult(
            dep, STATUS_PROBLEM,
            "vulkaninfo est présent mais échoue.",
            "Vulkan ne semble pas fonctionnel : vérifiez le pilote GPU "
            "(mesa-vulkan-drivers ou pilote NVIDIA) AVANT de lancer Unreal.",
        )

    def check_dependencies(self) -> list[DependencyResult]:
        """Check every catalogued dependency and return typed results."""
        results: list[DependencyResult] = []
        nvidia = has_nvidia_gpu()

        for dep in DEPENDENCIES:
            if dep.key == "vulkaninfo":
                results.append(self._vulkan_status(dep))
                continue

            present = which(dep.binary) is not None if dep.binary else False

            if present:
                path = which(dep.binary)
                results.append(DependencyResult(dep, STATUS_OK, path or "présent"))
                continue

            # Absent: decide the right status.
            if dep.optional:
                results.append(DependencyResult(
                    dep, STATUS_OPTIONAL, "Non installé (optionnel).", dep.purpose))
            else:
                results.append(DependencyResult(
                    dep, STATUS_MISSING, "Non installé.", dep.purpose))

        # nvidia-smi is special: not applicable without an NVIDIA GPU.
        nvidia_present = which("nvidia-smi") is not None
        if nvidia:
            if nvidia_present:
                driver = self._nvidia_driver()
                detail = f"GPU NVIDIA détecté. {driver}".strip()
                status = STATUS_OK
                hint = ""
            else:
                detail = "GPU NVIDIA détecté mais 'nvidia-smi' est absent."
                status = STATUS_PROBLEM
                hint = ("Installez le pilote NVIDIA propriétaire et ses outils "
                        "pour de bonnes performances Unreal.")
        else:
            detail = "Aucun GPU NVIDIA détecté."
            status = STATUS_NA
            hint = ""
        results.append(DependencyResult(
            Dependency("nvidia-smi", "nvidia-smi", "nvidia-smi", CAT_DIAGNOSE,
                       "Affiche l'état du GPU NVIDIA et la version du pilote.",
                       installable=False),
            status, detail, hint,
        ))

        return results

    def _nvidia_driver(self) -> str:
        if which("nvidia-smi") is None:
            return ""
        result = self._runner.run(
            ["nvidia-smi", "--query-gpu=driver_version", "--format=csv,noheader"],
            timeout=15,
        )
        if result.ok and result.stdout.strip():
            return f"Pilote : {result.stdout.strip().splitlines()[0]}"
        return ""

    def missing_installable(
        self, results: list[DependencyResult], *, include_optional: bool = False
    ) -> list[DependencyResult]:
        out = []
        for r in results:
            if not r.can_install:
                continue
            if r.status == STATUS_OPTIONAL and not include_optional:
                continue
            out.append(r)
        return out

    # -- install plan ------------------------------------------------------- #
    def build_install_plan(
        self,
        missing: list[DependencyResult],
        os_info: OSInfo | None = None,
    ) -> "InstallPlan":
        """Turn a list of missing dependencies into an ordered install plan."""
        info = os_info or self.os_info()
        plan = InstallPlan(os_info=info)

        flatpak_ids: list[str] = []
        brew_formulas: list[str] = []
        system_pkgs: list[str] = []

        for res in missing:
            dep = res.dependency
            if not dep.installable:
                continue

            if info.atomic:
                # Priority: Flatpak (GUI) -> Homebrew (CLI) -> rpm-ostree.
                if dep.flatpak and info.has_flatpak:
                    flatpak_ids.append(dep.flatpak)
                    continue
                if dep.brew and info.has_brew:
                    brew_formulas.append(dep.brew)
                    continue
                pkg = dep.package_for(FAMILY_FEDORA)
                if pkg:
                    system_pkgs.append(pkg)
                continue

            # Classic distributions.
            if dep.flatpak and info.has_flatpak and dep.key == "code":
                # Prefer Flatpak for VS Code even on classic distros.
                flatpak_ids.append(dep.flatpak)
                continue
            pkg = dep.package_for(info.family)
            if pkg:
                system_pkgs.append(pkg)

        # Flatpak step (safe, user-space).
        if flatpak_ids:
            ids = _dedup(flatpak_ids)
            plan.steps.append(InstallStep(
                description="Installer les applications via Flatpak (sans risque système).",
                command=["flatpak", "install", "-y", "flathub", *ids],
                method="flatpak",
                needs_confirm=False,
            ))

        # Homebrew step (user-space on atomic).
        if brew_formulas:
            formulas = _dedup(brew_formulas)
            plan.steps.append(InstallStep(
                description="Installer les outils CLI via Homebrew (sans modifier le système).",
                command=["brew", "install", *formulas],
                method="brew",
                needs_confirm=False,
            ))

        # System packages: dnf / apt / pacman / rpm-ostree.
        if system_pkgs:
            pkgs = _dedup(system_pkgs)
            if info.atomic:
                plan.steps.append(InstallStep(
                    description=(
                        "Installer des paquets système via rpm-ostree. "
                        "ATTENTION : cela modifie l'image système et demandera "
                        "probablement un redémarrage. À utiliser seulement si "
                        "nécessaire (Vulkan/GPU). Sur Bazzite, préférez Distrobox "
                        "pour les outils de développement."
                    ),
                    command=["rpm-ostree", "install", *pkgs],
                    method="rpm-ostree",
                    needs_confirm=True,
                    dangerous=True,
                    reboot_hint=True,
                    distrobox_alternative=_distrobox_hint(info, pkgs),
                ))
            elif info.family == FAMILY_FEDORA:
                plan.steps.append(InstallStep(
                    description="Installer les paquets système via dnf (nécessite sudo).",
                    command=["sudo", "dnf", "install", "-y", *pkgs],
                    method="dnf", needs_confirm=True,
                ))
            elif info.family == FAMILY_UBUNTU:
                plan.steps.append(InstallStep(
                    description="Mettre à jour l'index puis installer via apt (nécessite sudo).",
                    command=["sudo", "apt", "install", "-y", *pkgs],
                    pre_command=["sudo", "apt", "update"],
                    method="apt", needs_confirm=True,
                ))
            elif info.family == FAMILY_ARCH:
                plan.steps.append(InstallStep(
                    description="Installer les paquets via pacman (nécessite sudo).",
                    command=["sudo", "pacman", "-S", "--needed", "--noconfirm", *pkgs],
                    method="pacman", needs_confirm=True,
                ))
            else:
                plan.steps.append(InstallStep(
                    description=(
                        "Distribution non reconnue : installez manuellement ces "
                        "paquets avec votre gestionnaire : " + " ".join(pkgs)
                    ),
                    command=[],
                    method="manual", needs_confirm=False,
                ))

        return plan

    def confirm_before_system_install(self, plan: "InstallPlan") -> bool:
        """True if the plan contains any step needing explicit confirmation."""
        return any(step.needs_confirm for step in plan.steps)

    def copy_install_commands(self, plan: "InstallPlan") -> str:
        """Return the plan as copy-pasteable shell text."""
        return plan.as_shell_text()

    def install_dependencies(self, plan: "InstallPlan", *, dry_run: bool = False) -> bool:
        """Execute the plan's commands sequentially (blocking).

        Intended to be run from a background worker (the GUI wraps this in a
        QThread). Returns True if every command succeeded (or in dry-run).
        """
        commands: list[list[str]] = []
        for step in plan.steps:
            if step.pre_command:
                commands.append(step.pre_command)
            if step.command:
                commands.append(step.command)
        if not commands:
            self._runner.log("warning", "Aucune commande à exécuter dans ce plan.")
            return False

        if dry_run:
            self._runner.log(
                "info", "Simulation (dry-run) : les commandes ne sont pas exécutées.")

        previous_dry = self._runner.dry_run
        previous_sudo = self._runner.allow_sudo
        self._runner.dry_run = dry_run
        # The user has confirmed via the GUI, so privileged commands are allowed
        # for the duration of this plan only. In dry-run nothing is executed
        # (the runner short-circuits), so allowing sudo simply lets the user
        # preview the exact privileged commands instead of a "blocked" message.
        self._runner.allow_sudo = True
        all_ok = True
        try:
            for cmd in commands:
                result = self._runner.run(cmd)
                if not result.ok and not dry_run:
                    all_ok = False
                    self._runner.log(
                        "error",
                        "Une commande a échoué ; arrêt du plan d'installation.",
                    )
                    break
        finally:
            self._runner.dry_run = previous_dry
            self._runner.allow_sudo = previous_sudo

        if plan.needs_reboot and not dry_run and all_ok:
            self._runner.log(
                "warning",
                "Des paquets système ont été installés via rpm-ostree : un "
                "redémarrage est probablement nécessaire pour les activer.",
            )
        return all_ok


# --------------------------------------------------------------------------- #
# Install plan data structures
# --------------------------------------------------------------------------- #
@dataclass
class InstallStep:
    description: str
    command: list[str]
    method: str
    needs_confirm: bool = False
    dangerous: bool = False
    reboot_hint: bool = False
    pre_command: list[str] | None = None
    distrobox_alternative: str = ""


@dataclass
class InstallPlan:
    os_info: OSInfo
    steps: list[InstallStep] = field(default_factory=list)

    @property
    def is_empty(self) -> bool:
        return not self.steps

    @property
    def needs_reboot(self) -> bool:
        return any(step.reboot_hint for step in self.steps)

    def as_shell_text(self) -> str:
        lines: list[str] = ["# Plan d'installation des dépendances", ""]
        if self.is_empty:
            lines.append("# (rien à installer)")
            return "\n".join(lines)
        for step in self.steps:
            lines.append(f"# {step.description}")
            if step.distrobox_alternative:
                lines.append(f"# Alternative : {step.distrobox_alternative}")
            if step.pre_command:
                lines.append(CommandRunner.format_command(step.pre_command))
            if step.command:
                lines.append(CommandRunner.format_command(step.command))
            else:
                lines.append("# (à faire manuellement)")
            lines.append("")
        if self.needs_reboot:
            lines.append("# Après rpm-ostree, un redémarrage peut être nécessaire.")
        return "\n".join(lines)


def _distrobox_hint(os_info: OSInfo, pkgs: list[str]) -> str:
    if not os_info.has_distrobox:
        return ""
    return ("distrobox create -n unreal-tools -i fedora:latest ; "
            "distrobox enter unreal-tools -- sudo dnf install -y " + " ".join(pkgs))


def _dedup(items: list[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for item in items:
        if item not in seen:
            seen.add(item)
            out.append(item)
    return out
