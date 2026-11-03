#!/usr/bin/env bash
set -euo pipefail

usage() {
    printf 'Usage: %s [--size PIXELS]\n' "${0##*/}"
    printf 'Render icon.svg to src/assets/icon.png (default: 512px square).\n'
}

size=512
while (($#)); do
    case "$1" in
        --size)
            if (($# < 2)); then
                printf 'Error: --size requires a pixel count.\n' >&2
                usage >&2
                exit 2
            fi
            size=$2
            shift 2
            ;;
        -h|--help)
            usage
            exit 0
            ;;
        *)
            printf 'Error: unknown argument: %s\n' "$1" >&2
            usage >&2
            exit 2
            ;;
    esac
done

if [[ ! $size =~ ^[1-9][0-9]*$ ]]; then
    printf 'Error: size must be a positive whole number of pixels.\n' >&2
    exit 2
fi

if ! command -v inkscape >/dev/null 2>&1; then
    printf 'Error: Inkscape is required to render the SVG icon.\n' >&2
    exit 1
fi

script_dir=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
assets_dir="$script_dir/src/assets"
temporary_png=$(mktemp "$assets_dir/.icon.XXXXXX.png")
trap 'rm -f -- "$temporary_png"' EXIT

inkscape "$script_dir/icon.svg" \
    --export-filename="$temporary_png" \
    --export-width="$size" \
    --export-height="$size"
mv -- "$temporary_png" "$assets_dir/icon.png"
trap - EXIT

printf 'Generated %s/src/assets/icon.png (%s × %s).\n' "$script_dir" "$size" "$size"
