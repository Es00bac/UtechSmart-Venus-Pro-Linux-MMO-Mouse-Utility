"""Offline Arch payload checks; no root access, makepkg, or mouse required.

The release test double exercises source staging and package(), not a full
makepkg build. Install PyQt6 and hidapi to run the isolated GUI import check.
"""

from __future__ import annotations

import ast
import configparser
import importlib.util
import os
from pathlib import Path
import shlex
import shutil
import subprocess
import sys
from tempfile import TemporaryDirectory
import unittest
import xml.etree.ElementTree as ET


ROOT = Path(__file__).resolve().parents[1]
APP_ID = "com.github.es00bac.venusprolinux"


def local_imports(entry_point: str) -> set[str]:
    """Find the transitive repository-local imports without loading Qt or HID."""
    local_modules = {path.stem for path in ROOT.glob("*.py")}
    pending = [entry_point]
    visited = set()
    while pending:
        name = pending.pop()
        if name in visited:
            continue
        visited.add(name)
        tree = ast.parse((ROOT / f"{name}.py").read_text())
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                names = [alias.name.split(".")[0] for alias in node.names]
            elif isinstance(node, ast.ImportFrom) and node.module:
                names = [node.module.split(".")[0]]
            else:
                continue
            pending.extend((set(names) & local_modules) - visited)
    return visited


class ArchPackagingTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = TemporaryDirectory(prefix="venusprolinux-packaging-")
        cls.addClassCleanup(cls.temp.cleanup)
        work = Path(cls.temp.name)
        srcdir = work / "src"
        srcdir.mkdir()
        (srcdir / "venusprolinux").symlink_to(ROOT, target_is_directory=True)
        cls.packages = {}
        for name, recipe in (
            ("root-vcs", ROOT / "PKGBUILD"),
            ("local-vcs", ROOT / "packaging/arch/PKGBUILD"),
        ):
            pkgdir = work / name
            subprocess.run(
                ["bash", "-ec", 'source "$1"; package', "bash", str(recipe)],
                env={**os.environ, "srcdir": str(srcdir), "pkgdir": str(pkgdir)},
                check=True, capture_output=True, text=True,
            )
            cls.packages[name] = pkgdir

        # Intercept only makepkg. Run the real release builder, validate the
        # generated source checksum, and stage its generated package recipe.
        # This deliberately does not claim dependency/package-archive checks.
        bin_dir = work / "bin"
        bin_dir.mkdir()
        makepkg = bin_dir / "makepkg"
        makepkg.write_text("""#!/usr/bin/env bash
set -euo pipefail
source ./PKGBUILD
printf '%s  %s\\n' "${sha256sums[0]}" "${source[0]}" | sha256sum --check --status
srcdir="$PWD/src"
pkgdir="$PACKAGING_TEST_DEST"
mkdir -p "$srcdir"
tar -xzf "${source[0]}" -C "$srcdir"
package
""")
        makepkg.chmod(0o755)
        release_pkg = work / "release"
        subprocess.run(
            ["bash", str(ROOT / "packaging/arch/build-arch.sh"), "0.3.0"],
            env={
                **os.environ,
                "PATH": f"{bin_dir}{os.pathsep}{os.environ['PATH']}",
                "DIST_DIR": str(work / "dist"),
                "PACKAGING_TEST_DEST": str(release_pkg),
                "TMPDIR": str(work),
            },
            check=True, capture_output=True, text=True,
        )
        cls.packages["release"] = release_pkg

    def test_widgets_module_closure(self):
        for name, package in self.packages.items():
            for module in local_imports("venus_gui"):
                with self.subTest(recipe=name, module=module):
                    installed = package / "usr/share/venusprolinux" / f"{module}.py"
                    self.assertTrue(installed.is_file(), f"Missing {installed.name}")
                    self.assertEqual(installed.read_bytes(), (ROOT / installed.name).read_bytes())

    def test_desktop_icon_and_metainfo_resolve(self):
        for name, package in self.packages.items():
            with self.subTest(recipe=name):
                applications = package / "usr/share/applications"
                desktop = applications / f"{APP_ID}.desktop"
                self.assertEqual(list(applications.glob("*.desktop")), [desktop])
                parser = configparser.ConfigParser(interpolation=None)
                parser.read(desktop)
                entry = parser["Desktop Entry"]
                self.assertEqual(entry["Icon"], APP_ID)
                icons = list((package / "usr/share/icons/hicolor").glob(f"*/apps/{entry['Icon']}.png"))
                self.assertEqual(len(icons), 1)
                self.assertEqual(icons[0].read_bytes(), (ROOT / "icon.png").read_bytes())
                executable = shlex.split(entry["Exec"])[0]
                launcher = package / "usr/bin" / executable
                self.assertTrue(os.access(launcher, os.X_OK))
                metainfo = ET.parse(package / "usr/share/metainfo" / f"{APP_ID}.metainfo.xml")
                self.assertEqual(metainfo.findtext("id"), APP_ID)
                self.assertEqual(metainfo.findtext("launchable[@type='desktop-id']"), desktop.name)
                if shutil.which("desktop-file-validate"):
                    subprocess.run(["desktop-file-validate", str(desktop)], check=True)

    def test_assets_rules_and_license(self):
        for name, package in self.packages.items():
            with self.subTest(recipe=name):
                for asset in ("icon.png", "mouseimg.png"):
                    installed = package / "usr/share/venusprolinux" / asset
                    self.assertEqual(installed.read_bytes(), (ROOT / asset).read_bytes())
                self.assertTrue((package / "usr/lib/udev/rules.d/99-venus-pro.rules").is_file())
                licenses = list((package / "usr/share/licenses").glob("*/LICENSE"))
                self.assertEqual(len(licenses), 1)
                self.assertEqual(licenses[0].read_bytes(), (ROOT / "LICENSE").read_bytes())

    @unittest.skipUnless(
        importlib.util.find_spec("PyQt6") and importlib.util.find_spec("hid"),
        "Install PyQt6 and hidapi for staged GUI import checks",
    )
    def test_isolated_widgets_import(self):
        for name, package in self.packages.items():
            with self.subTest(recipe=name):
                app_dir = package / "usr/share/venusprolinux"
                result = subprocess.run(
                    [sys.executable, "-I", "-c", """
import importlib
from pathlib import Path
import sys
app_dir = Path(sys.argv[1])
sys.path.insert(0, str(app_dir))
for name in sys.argv[2:]:
    module = importlib.import_module(name)
    assert Path(module.__file__).parent == app_dir, module.__file__
""", str(app_dir), *sorted(local_imports("venus_gui"))],
                    cwd=self.temp.name, capture_output=True, text=True,
                )
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)


if __name__ == "__main__":
    unittest.main(verbosity=2)
