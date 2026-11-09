#!/usr/bin/env python3
"""build.py - package anycalc for any Flet target, in the build MODE you ask for.

Why this exists: `flet build` has no --debug flag. The build mode belongs to
Flutter, not to Flet, so it has to be forwarded to the flutter build command
(`--flutter-build-args=--debug`, which is also what a bare `-- --debug`
separator ends up doing). Writing that out every time is how debug builds end up
silently built as release, so the mode lives here instead:

    ./build.py apk                 production APK (release, the default)
    ./build.py apk --debug         debug APK - what you want under adb / an
                                   emulator: builds faster and is debuggable, but
                                   the Dart side runs JIT, so it is larger and
                                   slower than the release artifact
    ./build.py aab                 Play Store bundle
    ./build.py linux               desktop artifact for this host
    ./build.py appimage            Linux bundle packaged as an AppImage
    ./build.py deb                 Debian/Ubuntu package
    ./build.py rpm                 RPM package (requires rpmbuild)

It always runs from the workspace root - [tool.flet.app] in pyproject.toml is
what makes that legal instead of having to build from src/ - and always prefers
the project's own .venv/bin/flet, so the Flet that packages the app is the same
Flet the app's dependencies are pinned to.

Application and package identity is read from pyproject.toml so the builder
doesn't maintain a second copy of the app metadata.
"""

from __future__ import annotations

import os
import platform
import shutil
import subprocess
import sys
import textwrap
import tomllib
from dataclasses import dataclass, field
from pathlib import Path
from typing import NoReturn

SCRIPT_DIR = Path(__file__).resolve().parent

# Every target this wrapper knows about. `appimage`, `deb` and `rpm` are not Flet
# targets: they build the `linux` bundle first and get packaged here.
TARGETS = (
    "appimage",
    "deb",
    "rpm",
    "apk",
    "aab",
    "ipa",
    "ios-simulator",
    "linux",
    "macos",
    "windows",
    "web",
)
LINUX_PACKAGE_TARGETS = ("appimage", "deb", "rpm")
MODE_FLAGS = {"--release": "release", "--debug": "debug", "--profile": "profile"}

DEB_DEPENDS = (
    "libc6, libstdc++6, libgcc-s1, "
    "libgtk-3-0 | libgtk-3-0t64, libglib2.0-0 | libglib2.0-0t64"
)
RPM_REQUIRES = "gtk3, glibc, libstdc++, libgcc"


@dataclass(frozen=True)
class ProjectMetadata:
    package_name: str
    version: str
    description: str
    authors: tuple[dict[str, str], ...]
    license: str
    org: str
    product: str
    categories: tuple[str, ...]

    @property
    def app_id(self) -> str:
        return f"{self.org}.{self.product}"

    @property
    def desktop_file(self) -> str:
        return f"{self.app_id}.desktop"

    @property
    def icon_file(self) -> str:
        return f"{self.app_id}.png"

    @property
    def category_entry(self) -> str:
        return ";".join(self.categories) + ";"

    @property
    def maintainer(self) -> str:
        author = self.authors[0]
        name = author["name"]
        email = author.get("email")
        return f"{name} <{email}>" if email else name


def read_project_metadata() -> ProjectMetadata:
    """Read the app and package metadata that is authoritative in pyproject.toml."""
    try:
        with (SCRIPT_DIR / "pyproject.toml").open("rb") as handle:
            config = tomllib.load(handle)
        project = config["project"]
        flet = config["tool"]["flet"]
        categories = config["tool"]["flet"]["linux"]["categories"]
        authors = project["authors"]
        metadata = ProjectMetadata(
            package_name=project["name"],
            version=project["version"],
            description=project["description"],
            authors=tuple(authors),
            license=project["license"],
            org=flet["org"],
            product=flet["product"],
            categories=tuple(categories),
        )
    except (OSError, KeyError, TypeError, tomllib.TOMLDecodeError) as exc:
        die(f"Could not read required project metadata from pyproject.toml: {exc}")

    if not all(
        (
            metadata.package_name,
            metadata.version,
            metadata.description,
            metadata.authors,
            metadata.authors[0].get("name"),
            metadata.license,
            metadata.org,
            metadata.product,
            metadata.categories,
        )
    ):
        die("Required app/package metadata is missing from pyproject.toml.")
    return metadata


def die(message: str) -> NoReturn:
    """Print an error and exit with a failure status."""
    print(f"Error: {message}", file=sys.stderr)
    raise SystemExit(1)


def run(
    command: list[str],
    *,
    env: dict[str, str] | None = None,
    capture: bool = False,
) -> str:
    """Run a command, aborting with its exit status if it fails (set -e)."""
    try:
        result = subprocess.run(
            command,
            env=env,
            check=True,
            capture_output=capture,
            text=True,
        )
    except FileNotFoundError:
        die(f"{command[0]} could not be executed.")
    except subprocess.CalledProcessError as exc:
        raise SystemExit(exc.returncode)
    return result.stdout if capture else ""


def chmod_file(path: Path, mode: int) -> None:
    path.chmod(mode)


def chmod_recursive_go_w(path: Path) -> None:
    """Drop group/other write permission recursively (chmod -R go-w)."""
    for root, dirs, files in os.walk(path):
        for name in list(dirs) + files:
            entry = Path(root) / name
            try:
                stats = entry.lstat()
            except OSError:
                continue
            if not entry.is_symlink():
                entry.chmod(stats.st_mode & ~0o022)
    path.chmod(path.stat().st_mode & ~0o022)


def copy_bundle_contents(source: Path, destination: Path) -> None:
    """`cp -a source/. destination/` - contents only, preserving attrs/links."""
    shutil.copytree(source, destination, symlinks=True, dirs_exist_ok=True)


def remove_tree(path: Path) -> None:
    """`rm -rf` a staging tree; a tree left go-w by an older run is made writable."""
    if not path.exists():
        return
    try:
        shutil.rmtree(path)
    except PermissionError:
        for root, dirs, _ in os.walk(path):
            for name in dirs:
                Path(root, name).chmod(0o700)
        shutil.rmtree(path, ignore_errors=True)


def write_text(path: Path, content: str, mode: int = 0o644) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content)
    path.chmod(mode)


USAGE = """\
Usage: ./build.py TARGET [MODE] [OPTIONS] [-- FLUTTER-ARG...]

TARGET (what this wrapper supports):
  appimage       Build the Linux bundle, then package it as an AppImage
  deb            Build the Linux bundle, then package it as a .deb
  rpm            Build the Linux bundle, then package it as an .rpm
  apk            Android APK - side-loadable; test-with-emulator.sh installs
                 the release APK in build/apk/
  aab            Android App Bundle - the upload format for Google Play
  ipa            iOS app bundle (needs signing settings; see `flet build --help`)
  ios-simulator  iOS simulator build
  linux          Linux relocatable bundle in build/linux/
  macos          macOS artifact
  windows        Windows artifact (can only run on windows)
  web            web bundle

MODE (exactly one; the default is the production build):
  --release      flutter --release: AOT-compiled, tree-shaken, the smallest and
                 fastest artifact (DEFAULT)
  --debug        flutter --debug: no Dart AOT, dev tooling attached; quick to
                 build, installable with `adb install -r`, much larger
  --profile      flutter --profile: AOT with performance overlay, for measuring

OPTIONS:
  --out DIR            copy the artifact here instead of build/TARGET
  --split-per-abi      one APK/AAB per ABI instead of one fat multi-ABI bundle
  --arch ARCH...       ABIs/architectures to package, e.g. `--arch arm64-v8a`.
                       Android names: arm64-v8a, armeabi-v7a, x86_64
  --python-version V   Python runtime shipped inside the artifact (e.g. 3.14)
  --clean              delete build/ first (`flet clean`) - do this when a stale
                       Flutter bootstrap project is suspect
  --plain              plain log output instead of the rich live display
  -v, --verbose        verbose (repeat: -vv also passes --verbose to flutter)
  -h, --help           this text

Anything after `--` is forwarded to the underlying `flutter build` command."""


@dataclass
class Options:
    """The parsed command line - one TARGET, one MODE, plus the options."""

    target: str | None = None
    mode: str = "release"
    out_dir: str | None = None
    python_version: str | None = None
    split_per_abi: bool = False
    clean_first: bool = False
    log_format: str = "rich"
    verbosity: int = 0
    arch: list[str] = field(default_factory=list)
    extra_flutter_args: list[str] = field(default_factory=list)


def parse_args(argv: list[str]) -> Options:
    """Parse the command line options for one Flet build target."""
    options = Options()
    index = 0
    while index < len(argv):
        argument = argv[index]
        if argument in ("-h", "--help"):
            print(USAGE)
            raise SystemExit(0)
        elif argument in TARGETS:
            if options.target:
                die(
                    f"one TARGET at a time (got '{options.target}' and '{argument}')"
                )
            options.target = argument
        elif argument in MODE_FLAGS:
            options.mode = MODE_FLAGS[argument]
        elif argument == "--out":
            if index + 1 >= len(argv):
                die("--out needs a directory")
            options.out_dir = argv[index + 1]
            index += 1
        elif argument == "--python-version":
            if index + 1 >= len(argv):
                die("--python-version needs a version")
            options.python_version = argv[index + 1]
            index += 1
        elif argument == "--split-per-abi":
            options.split_per_abi = True
        elif argument == "--clean":
            options.clean_first = True
        elif argument == "--plain":
            options.log_format = "plain"
        elif argument in ("-v", "--verbose"):
            options.verbosity += 1
        elif argument == "--arch":
            index += 1
            while index < len(argv) and not argv[index].startswith("-"):
                options.arch.append(argv[index])
                index += 1
            if not options.arch:
                die("--arch needs at least one architecture")
            continue
        elif argument == "--":
            options.extra_flutter_args = list(argv[index + 1 :])
            break
        else:
            print(f"Unknown argument: {argument}\n", file=sys.stderr)
            print(USAGE, file=sys.stderr)
            raise SystemExit(2)
        index += 1

    if not options.target:
        print("No TARGET given.\n", file=sys.stderr)
        print(USAGE, file=sys.stderr)
        raise SystemExit(2)
    return options


@dataclass
class HostTools:
    """Extra host binaries the packaging targets need, resolved up front."""

    appimagetool: str | None = None
    rpmbuild: str | None = None


def is_executable(path: Path) -> bool:
    return path.is_file() and os.access(path, os.X_OK)


def resolve_appimagetool() -> str:
    """Find appimagetool: $APPIMAGETOOL first, then PATH."""
    override = os.environ.get("APPIMAGETOOL")
    if override:
        if "/" in override:
            candidate = Path(override)
            if not is_executable(candidate):
                die("APPIMAGETOOL must name an executable appimagetool")
            return str(candidate.resolve())
        found = shutil.which(override)
        if found:
            return found
        die("APPIMAGETOOL must name an executable appimagetool")
    found = shutil.which("appimagetool")
    if found:
        return found
    die(
        "appimagetool is required for the appimage target; install it and "
        "ensure it is on PATH, or set APPIMAGETOOL to its executable path."
    )


def resolve_rpmbuild() -> str:
    """Find rpmbuild: PATH first, then ~/.local/bin."""
    found = shutil.which("rpmbuild")
    if found:
        return found
    home = os.environ.get("HOME", "")
    candidate = Path(home) / ".local" / "bin" / "rpmbuild" if home else None
    if candidate and is_executable(candidate):
        return str(candidate)
    die("rpmbuild is required for the rpm target; install RPM build tools first.")


def preflight(options: Options) -> HostTools:
    """Reject option combinations the target cannot honour, then resolve tools."""
    target = options.target or ""
    tools = HostTools()
    if target in LINUX_PACKAGE_TARGETS:
        if platform.system() != "Linux":
            die(f"the {target} target must be built on Linux")
        if options.split_per_abi:
            die(f"--split-per-abi is not supported for {target}")
        if options.arch:
            die(
                f"--arch is not supported for {target}; "
                "it uses the host architecture"
            )
        if target == "appimage":
            tools.appimagetool = resolve_appimagetool()
        elif target == "deb":
            if not shutil.which("dpkg-deb"):
                die("dpkg-deb is required for the deb target.")
            if not shutil.which("dpkg"):
                die("dpkg is required to determine the Debian package architecture.")
        else:
            tools.rpmbuild = resolve_rpmbuild()
    return tools


def resolve_flet() -> str:
    """The project's own .venv/bin/flet first, then whatever is on PATH."""
    venv_flet = SCRIPT_DIR / ".venv" / "bin" / "flet"
    if is_executable(venv_flet):
        return str(venv_flet)
    found = shutil.which("flet")
    if found:
        return found
    die(
        "Flet CLI not found; install the project dev dependencies first "
        '(pip install -e ".[dev]").'
    )


def run_flet_build(options: Options, flet_path: str) -> None:
    """Run the `flet build` step for the target (packaged targets build `linux`)."""
    target = options.target or ""
    flet_target = "linux" if target in LINUX_PACKAGE_TARGETS else target

    flet_args = ["build", flet_target, "--log-format", options.log_format, "--yes"]
    if options.verbosity > 0:
        flet_args.append("-v")
    if options.out_dir and target not in LINUX_PACKAGE_TARGETS:
        flet_args += ["--output", options.out_dir]
    if options.split_per_abi:
        flet_args.append("--split-per-abi")
    if options.arch:
        flet_args += ["--arch", *options.arch]
    if options.python_version:
        flet_args += ["--python-version", options.python_version]

    # The mode is a `flutter build` argument, never a `flet build` flag. Release
    # is flutter's own default, so only the other two need forwarding.
    if options.mode == "debug":
        flet_args.append("--flutter-build-args=--debug")
    elif options.mode == "profile":
        flet_args.append("--flutter-build-args=--profile")

    if options.clean_first:
        print("Cleaning build/ ...")
        run([flet_path, "clean"])

    print(f"Building {flet_target} ({options.mode}) with {flet_path}")
    run([flet_path, *flet_args, *options.extra_flutter_args])


# --- The files the Linux packages are assembled from -------------------------
# The remaining package metadata is filled from pyproject.toml.
def appimage_desktop_entry(metadata: ProjectMetadata) -> str:
    return f"""\
[Desktop Entry]
Type=Application
Name={metadata.product}
Comment={metadata.description}
Exec=AppRun
Icon={metadata.product}
Categories={metadata.category_entry}
Terminal=false
"""


def app_run(metadata: ProjectMetadata) -> str:
    return f"""\
#!/usr/bin/env bash
set -euo pipefail
appdir=${{APPDIR:-$(cd -- "$(dirname -- "$0")" && pwd)}}
cd "$appdir/usr/lib/{metadata.product}"
exec ./{metadata.product} "$@"
"""


def bin_launcher(metadata: ProjectMetadata) -> str:
    return f"""\
#!/bin/sh
cd /usr/lib/{metadata.product}
exec ./{metadata.product} "$@"
"""


def desktop_entry(metadata: ProjectMetadata) -> str:
    return f"""\
[Desktop Entry]
Type=Application
Name={metadata.product}
Comment={metadata.description}
Exec={metadata.product} %U
Icon={metadata.app_id}
Terminal=false
Categories={metadata.category_entry}
StartupWMClass={metadata.app_id}
"""


def deb_control(metadata: ProjectMetadata, deb_arch: str) -> str:
    """The DEBIAN/control file - `Description:` is what package managers show."""
    long_description = textwrap.fill(metadata.description, width=78)
    long_description = "\n".join(f" {line}" for line in long_description.splitlines())
    return f"""\
Package: {metadata.package_name}
Version: {metadata.version}
Section: utils
Priority: optional
Architecture: {deb_arch}
Maintainer: {metadata.maintainer}
Depends: {DEB_DEPENDS}
Description: {metadata.product}
{long_description}
"""


def rpm_spec(metadata: ProjectMetadata) -> str:
    """The rpmbuild spec - `Summary:` plus `%description` are its texts."""
    return f"""\
Name: {metadata.package_name}
Version: {metadata.version}
Release: 1%{{?dist}}
Summary: {metadata.product}
License: {metadata.license}
Source0: {metadata.package_name}-payload.tar.gz
AutoReqProv: no
Requires: {RPM_REQUIRES}

%description
{metadata.description}

%prep

%install
mkdir -p %{{buildroot}}
tar -xzf %{{SOURCE0}} -C %{{buildroot}}

%files
%license /usr/share/licenses/{metadata.package_name}/LICENSE
/usr/bin/{metadata.product}
/usr/lib/{metadata.product}
/usr/share/doc/{metadata.package_name}/copyright
/usr/share/applications/{metadata.desktop_file}
/usr/share/icons/hicolor/512x512/apps/{metadata.icon_file}
"""


def package_appimage(
    options: Options, appimagetool: str, metadata: ProjectMetadata
) -> Path:
    """Wrap build/linux in an AppDir and run appimagetool over it."""
    linux_bundle = Path("build/linux")
    if not is_executable(linux_bundle / metadata.product):
        die(f"Linux bundle executable not found: {linux_bundle}/{metadata.product}")
    icon = Path("src/assets/icon.png")
    if not icon.is_file():
        die("AppImage icon not found: src/assets/icon.png")

    appdir = Path("build/appimage/.AppDir")
    output_dir = Path(options.out_dir or "build/appimage")
    appimage_arch = platform.machine()
    output_file = output_dir / f"{metadata.product}-{appimage_arch}.AppImage"

    remove_tree(appdir)
    bundle_dir = appdir / "usr/lib" / metadata.product
    bundle_dir.mkdir(parents=True, exist_ok=True)
    output_dir.mkdir(parents=True, exist_ok=True)
    copy_bundle_contents(linux_bundle, bundle_dir)
    shutil.copy2(icon, appdir / f"{metadata.product}.png")
    chmod_file(appdir / f"{metadata.product}.png", 0o644)
    write_text(appdir / metadata.desktop_file, appimage_desktop_entry(metadata))
    write_text(appdir / "AppRun", app_run(metadata), 0o755)
    chmod_recursive_go_w(appdir)

    print(f"Packaging Linux bundle as {output_file}")
    env = dict(os.environ)
    env["ARCH"] = appimage_arch
    # ${APPIMAGE_EXTRACT_AND_RUN:-1}: unset or empty both mean 1.
    env["APPIMAGE_EXTRACT_AND_RUN"] = (
        os.environ.get("APPIMAGE_EXTRACT_AND_RUN") or "1"
    )
    run([appimagetool, str(appdir), str(output_file)], env=env)
    return output_dir


def copy_file(source: Path, destination: Path) -> None:
    """`cp source destination` - failing the build the way cp would."""
    try:
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, destination)
    except (FileNotFoundError, shutil.SameFileError):
        die(f"Package file not found: {source}")


def package_linux_distribution(
    options: Options, rpmbuild: str | None, metadata: ProjectMetadata
) -> Path:
    """Stage build/linux as a filesystem root, then build the .deb or the .rpm."""
    target = options.target or ""
    linux_bundle = Path("build/linux")
    if not is_executable(linux_bundle / metadata.product):
        die(f"Linux bundle executable not found: {linux_bundle}/{metadata.product}")
    icon = Path("src/assets/icon.png")
    if not icon.is_file():
        die("Package icon not found: src/assets/icon.png")

    package_root = Path(f"build/packages/{target}/root")
    output_dir = Path(options.out_dir or f"build/{target}")
    package_name = metadata.package_name
    product = metadata.product

    remove_tree(package_root)
    for directory in (
        package_root / "usr/lib" / product,
        package_root / "usr/bin",
        package_root / "usr/share/applications",
        package_root / "usr/share/doc" / package_name,
        package_root / "usr/share/icons/hicolor/512x512/apps",
        package_root / "usr/share/licenses" / package_name,
    ):
        directory.mkdir(parents=True, exist_ok=True)
    output_dir.mkdir(parents=True, exist_ok=True)

    copy_bundle_contents(linux_bundle, package_root / "usr/lib" / product)
    icon_target = (
        package_root / "usr/share/icons/hicolor/512x512/apps" / metadata.icon_file
    )
    copy_file(icon, icon_target)
    copyright_target = package_root / "usr/share/doc" / package_name / "copyright"
    copy_file(Path("LICENSE"), copyright_target)
    license_target = package_root / "usr/share/licenses" / package_name / "LICENSE"
    copy_file(Path("LICENSE"), license_target)
    for path in (icon_target, copyright_target, license_target):
        chmod_file(path, 0o644)
    write_text(package_root / "usr/bin" / product, bin_launcher(metadata), 0o755)
    write_text(
        package_root / "usr/share/applications" / metadata.desktop_file,
        desktop_entry(metadata),
    )
    chmod_recursive_go_w(package_root)

    if target == "deb":
        deb_arch = run(["dpkg", "--print-architecture"], capture=True).strip()
        write_text(
            package_root / "DEBIAN/control",
            deb_control(metadata, deb_arch),
        )
        output_file = output_dir / f"{package_name}_{metadata.version}_{deb_arch}.deb"
        print(f"Packaging Linux bundle as {output_file}")
        run(
            [
                "dpkg-deb",
                "--build",
                "--root-owner-group",
                str(package_root),
                str(output_file),
            ]
        )
    else:
        if rpmbuild is None:
            rpmbuild = resolve_rpmbuild()
        # Absolute because rpmbuild gets it as `--define _topdir ...`; a relative
        # path lands the RPMDB under "/" instead of under the workspace.
        rpm_work = SCRIPT_DIR / "build/packages/rpm/rpmbuild"
        rpm_sources = rpm_work / "SOURCES"
        for directory in (rpm_sources, rpm_work / "SPECS", rpm_work / "RPMDB"):
            directory.mkdir(parents=True, exist_ok=True)
        run(
            [
                "tar",
                "-C",
                str(package_root),
                "-czf",
                str(rpm_sources / f"{package_name}-payload.tar.gz"),
                "usr",
            ]
        )
        spec_path = rpm_work / "SPECS" / f"{package_name}.spec"
        write_text(spec_path, rpm_spec(metadata))
        print("Packaging Linux bundle as an RPM")
        run(
            [
                rpmbuild,
                "-bb",
                "--define",
                f"_dbpath {rpm_work / 'RPMDB'}",
                "--define",
                f"_topdir {rpm_work}",
                str(spec_path),
            ]
        )
        pattern = f"*/{package_name}-{metadata.version}-1*.rpm"
        rpm_files = sorted((rpm_work / "RPMS").glob(pattern))
        if len(rpm_files) != 1:
            die(f"Expected one RPM package in {rpm_work / 'RPMS'}.")
        output_file = output_dir / rpm_files[0].name
        shutil.copy2(rpm_files[0], output_file)

    return output_dir


def list_artifacts(out_path: Path) -> None:
    """Report artifact file sizes from the output directory."""
    print(f"\nArtifacts in {out_path}:")
    if not out_path.is_dir():
        print(f"  {out_path} does not exist")
        return
    artifacts = sorted(
        entry for entry in out_path.iterdir() if entry.is_file()
    )
    for artifact in artifacts:
        size = artifact.stat().st_size
        for unit in ("B", "KB", "MB", "GB"):
            if size < 1024 or unit == "GB":
                print(f"  {size:7.1f} {unit}  {artifact}")
                break
            size /= 1024


def main(argv: list[str] | None = None) -> None:
    options = parse_args(list(sys.argv[1:] if argv is None else argv))
    metadata = read_project_metadata()
    tools = preflight(options)
    flet_path = resolve_flet()

    # The build has to run from the workspace root: that is where pyproject.toml
    # keeps [tool.flet] and [tool.flet.app], which tell Flet the app itself is
    # src/main.py.
    os.chdir(SCRIPT_DIR)

    run_flet_build(options, flet_path)

    target = options.target or ""
    if target == "appimage":
        out_path = package_appimage(
            options, tools.appimagetool or "appimagetool", metadata
        )
    elif target in ("deb", "rpm"):
        out_path = package_linux_distribution(options, tools.rpmbuild, metadata)
    else:
        out_path = Path(options.out_dir or f"build/{target}")

    list_artifacts(out_path)


if __name__ == "__main__":
    main()