#!/usr/bin/env bash
set -euo pipefail

# build.sh - package anycalc for any Flet target, in the build MODE you ask for.
#
# Why this exists: `flet build` has no --debug flag. The build mode belongs to
# Flutter, not to Flet, so it has to be forwarded to the flutter build command
# (`--flutter-build-args=--debug`, which is also what a bare `-- --debug`
# separator ends up doing). Writing that out every time is how debug builds end up
# silently built as release, so the mode lives here instead:
#
#   ./build.sh apk                 production APK (release, the default)
#   ./build.sh apk --debug         debug APK - what you want under adb / an
#                                  emulator: builds faster and is debuggable, but
#                                  the Dart side runs JIT, so it is larger and
#                                  slower than the release artifact
#   ./build.sh aab                 Play Store bundle
#   ./build.sh linux               desktop artifact for this host
#
# It always runs from the workspace root - [tool.flet.app] in pyproject.toml is
# what makes that legal instead of having to build from src/ - and always prefers
# the project's own .venv/bin/flet, so the Flet that packages the app is the same
# Flet the app's dependencies are pinned to.

usage() {
    cat <<'EOF'
Usage: ./build.sh TARGET [MODE] [OPTIONS] [-- FLUTTER-ARG...]

TARGET (what `flet build` accepts):
  apk            Android APK - side-loadable; test-with-emulator.sh installs
                 build/apk/anycalc.apk
  aab            Android App Bundle - the upload format for Google Play
  ipa            iOS app bundle (needs signing settings; see `flet build --help`)
  ios-simulator  iOS simulator build
  linux          Linux artifact (AppImage by default)
  macos          macOS artifact
  windows        Windows artifact
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

Anything after `--` is forwarded to the underlying `flutter build` command.
EOF
}

die() {
    printf 'Error: %s\n' "$1" >&2
    exit 1
}

script_dir=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)

target=
mode=release
out_dir=
python_version=
split_per_abi=false
clean_first=false
log_format=rich
verbosity=0
arch=()
extra_flutter_args=()

while (($#)); do
    case "$1" in
        -h | --help)
            usage
            exit 0
            ;;
        apk | aab | ipa | ios-simulator | linux | macos | windows | web)
            [[ -z $target ]] || die "one TARGET at a time (got '$target' and '$1')"
            target=$1
            ;;
        --release) mode=release ;;
        --debug) mode=debug ;;
        --profile) mode=profile ;;
        --out)
            (($# >= 2)) || die "--out needs a directory"
            out_dir=$2
            shift
            ;;
        --python-version)
            (($# >= 2)) || die "--python-version needs a version"
            python_version=$2
            shift
            ;;
        --split-per-abi) split_per_abi=true ;;
        --clean) clean_first=true ;;
        --plain) log_format=plain ;;
        -v | --verbose) verbosity=$((verbosity + 1)) ;;
        --arch)
            shift
            while (($#)) && [[ $1 != -* ]]; do
                arch+=("$1")
                shift
            done
            ((${#arch[@]})) || die "--arch needs at least one architecture"
            continue
            ;;
        --)
            shift
            extra_flutter_args=("$@")
            break
            ;;
        *)
            printf 'Unknown argument: %s\n\n' "$1" >&2
            usage >&2
            exit 2
            ;;
    esac
    shift
done

[[ -n $target ]] || {
    printf 'No TARGET given.\n\n' >&2
    usage >&2
    exit 2
}

if [[ -x "$script_dir/.venv/bin/flet" ]]; then
    flet="$script_dir/.venv/bin/flet"
elif command -v flet >/dev/null 2>&1; then
    flet=$(command -v flet)
else
    die 'Flet CLI not found; install the project dev dependencies first (pip install -e ".[dev]").'
fi

# The build has to run from the workspace root: that is where pyproject.toml
# keeps [tool.flet] and [tool.flet.app], which tell Flet the app itself is
# src/main.py.
cd -- "$script_dir"

flet_args=(build "$target" --log-format "$log_format" --yes)
(($verbosity > 0)) && flet_args+=(-v)
[[ -n $out_dir ]] && flet_args+=(--output "$out_dir")
[[ $split_per_abi == true ]] && flet_args+=(--split-per-abi)
[[ ${#arch[@]} -gt 0 ]] && flet_args+=(--arch "${arch[@]}")
[[ -n $python_version ]] && flet_args+=(--python-version "$python_version")

# The mode is a `flutter build` argument, never a `flet build` flag. Release is
# flutter's own default, so only the other two need forwarding.
case $mode in
    debug) flet_args+=(--flutter-build-args=--debug) ;;
    profile) flet_args+=(--flutter-build-args=--profile) ;;
esac

if [[ $clean_first == true ]]; then
    printf 'Cleaning build/ ...\n'
    "$flet" clean
fi

printf 'Building %s (%s) with %s\n' "$target" "$mode" "$flet"
"$flet" "${flet_args[@]}" ${extra_flutter_args[@]+"${extra_flutter_args[@]}"}

out_path=${out_dir:-build/$target}
printf '\nArtifacts in %s:\n' "$out_path"
if [[ -d $out_path ]]; then
    find "$out_path" -maxdepth 1 -type f -exec ls -lh {} +
else
    printf '  %s does not exist\n' "$out_path"
fi

