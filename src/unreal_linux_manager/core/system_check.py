"""System diagnostics: is this Linux machine ready to run Unreal Engine?

Every check returns a :class:`CheckResult` with a simple status
(``ok`` / ``warn`` / ``error`` / ``info``) so the GUI can colour it without
any special styling logic. All checks are defensive: a missing tool produces a
``warn`` with an actionable hint, never an exception.
"""

from __future__ import annotations

import os
import platform
import shutil
from dataclasses import dataclass
from pathlib import Path

from . import paths
from .command_runner import CommandRunner, which

OK = "ok"
WARN = "warn"
ERROR = "error"
INFO = "info"


@dataclass
class CheckResult:
    name: str
    status: str
    detail: str = ""
    hint: str = ""


def _run_capture(runner: CommandRunner, cmd: list[str], timeout: float = 20) -> tuple[bool, str]:
    if which(cmd[0]) is None:
        return False, ""
    result = runner.run(cmd, timeout=timeout)
    return result.ok, result.stdout.strip()


def read_os_release() -> dict[str, str]:
    """Parse /etc/os-release into a dictionary."""
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


class SystemCheck:
    """Collection of individual diagnostic checks."""

    def __init__(self, runner: CommandRunner) -> None:
        self._runner = runner

    # -- OS ----------------------------------------------------------------- #
    def check_os(self) -> CheckResult:
        os_info = read_os_release()
        name = os_info.get("PRETTY_NAME") or os_info.get("NAME") or platform.platform()
        return CheckResult("Système d'exploitation", INFO, name)

    def is_atomic(self) -> bool:
        """Heuristic: is this an immutable / atomic (ostree) distribution?"""
        os_info = read_os_release()
        variant = (os_info.get("VARIANT_ID", "") + os_info.get("ID", "")).lower()
        if any(tag in variant for tag in ("bazzite", "silverblue", "kinoite", "atomic")):
            return True
        return Path("/run/ostree-booted").exists()

    def check_atomic(self) -> CheckResult:
        if self.is_atomic():
            return CheckResult(
                "Système atomic / immuable",
                WARN,
                "Système immuable détecté (Bazzite / Fedora Atomic).",
                "Évitez les installations système. Préférez Flatpak, AppImage, "
                "Distrobox ou des dossiers utilisateur. N'utilisez pas "
                "'dnf install' sur l'hôte ; 'rpm-ostree' en dernier recours.",
            )
        return CheckResult(
            "Système atomic / immuable", OK, "Système classique (modifiable)."
        )

    def check_rpm_ostree(self) -> CheckResult:
        if which("rpm-ostree") is None:
            return CheckResult("rpm-ostree", INFO, "Non présent (système non ostree).")
        ok, out = _run_capture(self._runner, ["rpm-ostree", "status", "--booted"])
        if ok:
            first = out.splitlines()[0] if out else "état disponible"
            return CheckResult(
                "rpm-ostree",
                WARN,
                first.strip(),
                "Système géré par rpm-ostree : ne modifiez la couche système "
                "qu'en dernier recours et après confirmation explicite.",
            )
        return CheckResult("rpm-ostree", INFO, "Présent mais état indisponible.")

    # -- display server ----------------------------------------------------- #
    def check_display_server(self) -> CheckResult:
        session_type = os.environ.get("XDG_SESSION_TYPE", "")
        wayland = os.environ.get("WAYLAND_DISPLAY")
        x11 = os.environ.get("DISPLAY")
        if session_type == "wayland" or wayland:
            return CheckResult(
                "Serveur d'affichage", INFO,
                "Wayland détecté.",
                "Unreal fonctionne, mais en cas de souci, une session X11/XWayland "
                "peut être plus stable pour l'éditeur.",
            )
        if session_type == "x11" or x11:
            return CheckResult("Serveur d'affichage", OK, "X11 détecté.")
        return CheckResult("Serveur d'affichage", WARN, "Indéterminé (session distante ?).")

    # -- GPU / Vulkan ------------------------------------------------------- #
    def check_gpu(self) -> CheckResult:
        if which("nvidia-smi"):
            ok, out = _run_capture(
                self._runner,
                ["nvidia-smi", "--query-gpu=name,driver_version",
                 "--format=csv,noheader"],
            )
            if ok and out:
                return CheckResult("GPU", OK, "NVIDIA : " + out.splitlines()[0].strip())
        if which("glxinfo"):
            ok, out = _run_capture(self._runner, ["glxinfo", "-B"])
            if ok and out:
                renderer = next(
                    (l.split(":", 1)[1].strip() for l in out.splitlines()
                     if "OpenGL renderer" in l),
                    "",
                )
                if renderer:
                    return CheckResult("GPU", OK, renderer)
        return CheckResult(
            "GPU", WARN,
            "Impossible d'identifier le GPU automatiquement.",
            "Installez 'mesa-utils' (glxinfo) ou les pilotes appropriés.",
        )

    def check_vulkan(self) -> CheckResult:
        if which("vulkaninfo") is None:
            return CheckResult(
                "Vulkan", WARN,
                "'vulkaninfo' introuvable.",
                "Installez le paquet 'vulkan-tools' (via Flatpak runtime, "
                "Distrobox ou paquet système) pour valider Vulkan. Unreal 5 "
                "requiert Vulkan.",
            )
        ok, out = _run_capture(self._runner, ["vulkaninfo", "--summary"], timeout=30)
        if ok and out:
            gpu_line = next(
                (l.strip() for l in out.splitlines() if "deviceName" in l), ""
            )
            detail = gpu_line or "Vulkan opérationnel."
            return CheckResult("Vulkan", OK, detail)
        return CheckResult(
            "Vulkan", ERROR,
            "vulkaninfo a échoué.",
            "Vérifiez l'installation des pilotes Vulkan (mesa-vulkan-drivers "
            "ou pilote NVIDIA).",
        )

    # -- hardware ----------------------------------------------------------- #
    def check_ram(self) -> CheckResult:
        total = _total_ram_bytes()
        if total <= 0:
            return CheckResult("Mémoire vive", WARN, "Impossible de mesurer la RAM.")
        gib = total / (1024 ** 3)
        detail = f"{gib:.1f} Gio"
        if gib < 8:
            return CheckResult("Mémoire vive", ERROR, detail,
                               "8 Gio minimum ; 16 Gio+ recommandé pour Unreal.")
        if gib < 16:
            return CheckResult("Mémoire vive", WARN, detail,
                               "16 Gio ou plus recommandé pour un confort d'usage.")
        return CheckResult("Mémoire vive", OK, detail)

    def check_disk_space(self, directory: str | Path) -> CheckResult:
        path = paths.expand(directory)
        probe = path
        while not probe.exists() and probe != probe.parent:
            probe = probe.parent
        try:
            usage = shutil.disk_usage(probe)
        except OSError:
            return CheckResult(f"Espace disque ({path})", WARN,
                               "Impossible de mesurer l'espace disque.")
        free_gib = usage.free / (1024 ** 3)
        detail = f"{free_gib:.1f} Gio libres sur {probe}"
        if free_gib < 50:
            return CheckResult(f"Espace disque", ERROR, detail,
                               "Un moteur Unreal + projets peut dépasser 100 Gio.")
        if free_gib < 100:
            return CheckResult(f"Espace disque", WARN, detail,
                               "Prévoyez de l'espace : une build source dépasse 100 Gio.")
        return CheckResult("Espace disque", OK, detail)

    def check_glibc(self) -> CheckResult:
        try:
            version = platform.libc_ver()
            if version and version[1]:
                return CheckResult("glibc", INFO, f"{version[0]} {version[1]}")
        except OSError:
            pass
        return CheckResult("glibc", INFO, "Version indéterminée.")

    # -- tools -------------------------------------------------------------- #
    def _tool(self, name: str, binaries: list[str], hint: str) -> CheckResult:
        for binary in binaries:
            found = which(binary)
            if found:
                return CheckResult(name, OK, found)
        return CheckResult(name, WARN, "Non installé.", hint)

    def check_vscode(self) -> CheckResult:
        return self._tool(
            "VS Code", ["code", "code-insiders"],
            "Optionnel : installez VS Code (Flatpak 'com.visualstudio.code') "
            "pour éditer le code C++/Blueprints.",
        )

    def check_distrobox(self) -> CheckResult:
        return self._tool(
            "Distrobox", ["distrobox"],
            "Optionnel mais recommandé sur systèmes atomic pour compiler "
            "Unreal depuis les sources sans toucher à l'hôte.",
        )

    def check_flatpak(self) -> CheckResult:
        return self._tool(
            "Flatpak", ["flatpak"],
            "Recommandé : Flatpak permet d'installer des outils (Epic Asset "
            "Manager, VS Code) sans modifier le système immuable.",
        )

    def check_editor_executable(self, engine_paths: list[str]) -> CheckResult:
        """Verify that at least one detected UnrealEditor binary is executable."""
        from . import unreal_detector

        checked = 0
        for raw in engine_paths:
            editor = unreal_detector.unreal_editor_path(raw)
            if editor.is_file():
                checked += 1
                if not os.access(editor, os.X_OK):
                    return CheckResult(
                        "UnrealEditor exécutable", WARN,
                        f"{editor} n'a pas le bit exécutable.",
                        "Utilisez l'onglet Moteurs (l'import corrige cela "
                        "automatiquement) ou 'chmod +x' sur le binaire.",
                    )
        if checked == 0:
            return CheckResult(
                "UnrealEditor exécutable", INFO,
                "Aucun moteur détecté à vérifier.",
            )
        return CheckResult("UnrealEditor exécutable", OK,
                           f"{checked} binaire(s) exécutable(s).")

    # -- orchestration ------------------------------------------------------ #
    def run_all(
        self,
        *,
        engine_scan_paths: list[str] | None = None,
        disk_dirs: list[str] | None = None,
    ) -> list[CheckResult]:
        """Run every check and return the ordered list of results."""
        engine_scan_paths = engine_scan_paths or []
        disk_dirs = disk_dirs or [str(Path.home())]

        results = [
            self.check_os(),
            self.check_atomic(),
            self.check_rpm_ostree(),
            self.check_display_server(),
            self.check_gpu(),
            self.check_vulkan(),
            self.check_ram(),
            self.check_glibc(),
        ]
        for directory in disk_dirs:
            results.append(self.check_disk_space(directory))
        results.append(self.check_editor_executable(engine_scan_paths))
        results.extend([
            self.check_vscode(),
            self.check_distrobox(),
            self.check_flatpak(),
        ])
        return results


def _total_ram_bytes() -> int:
    """Return total system RAM in bytes (0 if unknown)."""
    try:
        pages = os.sysconf("SC_PHYS_PAGES")
        page_size = os.sysconf("SC_PAGE_SIZE")
        if pages > 0 and page_size > 0:
            return pages * page_size
    except (ValueError, OSError):
        pass
    # Fallback via /proc/meminfo.
    try:
        for line in Path("/proc/meminfo").read_text().splitlines():
            if line.startswith("MemTotal:"):
                return int(line.split()[1]) * 1024
    except (OSError, ValueError, IndexError):
        pass
    return 0
