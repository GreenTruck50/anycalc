import importlib.util
import sys
import tomllib
from dataclasses import replace
from pathlib import Path

import pytest

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
