import importlib.util
import sys
import tomllib
from dataclasses import replace
from pathlib import Path
from typing import TYPE_CHECKING

import pytest

if TYPE_CHECKING:
    # Only for the type checker: the script is loaded by path below, so its names
    # exist at runtime only on the ``build`` module object.
    from build import HostTools, Options

BUILD_PATH = Path(__file__).resolve().parents[1] / "build.py"
BUILD_SPEC = importlib.util.spec_from_file_location("anycalc_build", BUILD_PATH)
if BUILD_SPEC is None or BUILD_SPEC.loader is None:
    raise ImportError(f"Unable to load build script from {BUILD_PATH}")
build = importlib.util.module_from_spec(BUILD_SPEC)
sys.modules[BUILD_SPEC.name] = build
BUILD_SPEC.loader.exec_module(build)


def test_project_metadata_matches_pyproject() -> None:
    with Path("pyproject.toml").open("rb") as project_file:
        config = tomllib.load(project_file)
    metadata = build.read_project_metadata()

    assert metadata.package_name == config["project"]["name"]
    assert metadata.version == config["project"]["version"]
    assert metadata.description == config["project"]["description"]
    assert metadata.authors == tuple(config["project"]["authors"])
    assert metadata.license == config["project"]["license"]
    assert metadata.org == config["tool"]["flet"]["org"]
    assert metadata.product == config["tool"]["flet"]["product"]
    assert metadata.categories == tuple(config["tool"]["flet"]["linux"]["categories"])


def test_package_metadata_uses_project_values() -> None:
    metadata = replace(
        build.read_project_metadata(),
        package_name="sample-package",
        version="9.8.7",
        description="A sample app description.",
        authors=({"name": "Example Maintainer"},),
        license="MIT",
        org="org.example",
        product="sample-app",
        categories=("Utility", "Calculator"),
    )

    assert metadata.app_id == "org.example.sample-app"
    assert metadata.desktop_file == "org.example.sample-app.desktop"
    assert metadata.icon_file == "org.example.sample-app.png"
    assert metadata.maintainer == "Example Maintainer"
    assert "Comment=A sample app description." in build.desktop_entry(metadata)
    assert "Exec=sample-app %U" in build.desktop_entry(metadata)
    assert "Icon=org.example.sample-app" in build.desktop_entry(metadata)
    assert "Categories=Utility;Calculator;" in build.desktop_entry(metadata)
    assert "Comment=A sample app description." in build.appimage_desktop_entry(metadata)
    assert "cd /usr/lib/sample-app" in build.bin_launcher(metadata)
    assert "Package: sample-package" in build.deb_control(metadata, "amd64")
    assert "Version: 9.8.7" in build.deb_control(metadata, "amd64")
    assert "License: MIT" in build.rpm_spec(metadata)
    assert "sample-package-payload.tar.gz" in build.rpm_spec(metadata)


def test_flet_build_forwards_mode_and_flutter_arguments(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    options = build.parse_args(
        [
            "apk",
            "--debug",
            "--arch",
            "arm64-v8a",
            "--",
            "--no-tree-shake-icons",
        ]
    )
    commands: list[list[str]] = []

    def capture_run(command: list[str]) -> str:
        commands.append(command)
        return ""

    monkeypatch.setattr(build, "run", capture_run)

    # `main` repoints ``options.target`` for the TARGET it is building, and the
    # build step reads it from there - so a single-target call has to say which.
    options.target = "apk"

    build.run_flet_build(options, "/path/to/flet")

    assert commands == [
        [
            "/path/to/flet",
            "build",
            "apk",
            "--log-format",
            "rich",
            "--yes",
            "--arch",
            "arm64-v8a",
            "--flutter-build-args=--debug",
            "--no-tree-shake-icons",
        ]
    ]


def test_targets_are_kept_in_order_without_repeats() -> None:
    options = build.parse_args(["deb", "linux", "deb", "apk"])

    assert options.targets == ["deb", "linux", "apk"]
    assert options.target == "", "no target is picked before the walk starts"


def test_an_unusable_target_list_exits_two(
    capsys: pytest.CaptureFixture[str],
) -> None:
    with pytest.raises(SystemExit) as unknown:
        build.parse_args(["apk", "win"])
    # SystemExit does not compare equal to its own status - the number lives on
    # ``code``, and ``value`` is the exception.
    assert unknown.value.code == 2

    with pytest.raises(SystemExit) as empty:
        build.parse_args(["--debug"])
    assert empty.value.code == 2
    assert "No TARGET given" in capsys.readouterr().err


def test_several_targets_each_get_their_build_and_directory(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Several TARGETs are the flow run once each, each under ``--out``/<target>."""

    seen: list[tuple[str, str | None]] = []

    def fake_build_target(
        options: "Options",
        target: str,
        flet_path: str,
        tools: "HostTools",
        metadata: object,
    ) -> Path:
        # The real flow repoints ``options.target`` for the target it is building;
        # the stand-in has to, or the walk would be recorded with no target at all.
        options.target = target
        seen.append((options.target, options.out_dir))
        return Path("build") / target

    monkeypatch.setattr(build, "read_project_metadata", lambda: None)
    monkeypatch.setattr(build, "preflight", lambda options: build.HostTools())
    monkeypatch.setattr(build, "resolve_flet", lambda: "/path/to/flet")
    monkeypatch.setattr(build, "build_target", fake_build_target)
    monkeypatch.setattr(build, "list_artifacts", lambda path: None)

    build.main(["deb", "--out", "out", "apk"])

    assert seen == [("deb", "out/deb"), ("apk", "out/apk")]

    seen.clear()
    build.main(["linux"])
    assert seen == [("linux", None)], "one TARGET keeps --out as its own directory"


def test_build_target_selects_its_own_target(monkeypatch: pytest.MonkeyPatch) -> None:
    """The single-target flow reads the target off ``options``."""

    commands: list[list[str]] = []

    def capture_run(command: list[str]) -> str:
        commands.append(command)
        return ""

    monkeypatch.setattr(build, "run", capture_run)

    options = build.parse_args(["deb", "apk"])
    produced = build.build_target(
        options,
        "apk",
        "/path/to/flet",
        build.HostTools(),
        build.read_project_metadata(),
    )

    assert options.target == "apk"
    assert commands[0][:3] == ["/path/to/flet", "build", "apk"]
    assert produced == Path("build/apk")
