#!/usr/bin/env bash
set -euo pipefail

usage() {
    printf 'Usage: %s AVD_NAME\n' "${0##*/}"
    printf 'Build the APK, boot the named Android emulator if needed, install it, and launch anycalc.\n'
}

if (($# != 1)); then
    usage >&2
    exit 2
fi

avd_name=$1
case "$avd_name" in
    -h|--help)
        usage
        exit 0
        ;;
esac

script_dir=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
sdk_dir=${ANDROID_SDK_ROOT:-${ANDROID_HOME:-"$HOME/Android/Sdk"}}
adb="$sdk_dir/platform-tools/adb"
emulator="$sdk_dir/emulator/emulator"
emulator_check="$sdk_dir/emulator/emulator-check"
apk="$script_dir/build/apk/anycalc.apk"
application_id=com.github.greentruck50.anycalc

if [[ ! -x $adb || ! -x $emulator ]]; then
    printf 'Error: Android SDK tools not found under %s.\n' "$sdk_dir" >&2
    printf 'Set ANDROID_SDK_ROOT or ANDROID_HOME to the SDK directory.\n' >&2
    exit 1
fi

avd_found=false
while IFS= read -r listed_avd; do
    if [[ $listed_avd == "$avd_name" ]]; then
        avd_found=true
        break
    fi
done < <("$emulator" -list-avds)

if [[ $avd_found != true ]]; then
    printf 'Error: AVD %q is not configured in this Android SDK.\n' "$avd_name" >&2
    printf 'Available AVDs:\n' >&2
    "$emulator" -list-avds >&2
    exit 1
fi

printf 'Building Android APK...\n'
"$script_dir/build.sh" apk

if [[ ! -f $apk ]]; then
    printf 'Error: Flet build completed without producing %s.\n' "$apk" >&2
    exit 1
fi

find_running_serial() {
    local serial state extra response running_avd
    while read -r serial state extra; do
        [[ $serial == emulator-* && $state == device ]] || continue
        response=$("$adb" -s "$serial" emu avd name 2>/dev/null) || continue
        response=${response//$'\r'/}
        running_avd=${response%%$'\n'*}
        running_avd=${running_avd#avd name: }
        if [[ $running_avd == "$avd_name" ]]; then
            printf '%s\n' "$serial"
            return 0
        fi
    done < <("$adb" devices)
    return 1
}

serial=
if serial=$(find_running_serial); then
    printf 'Using running AVD %s on %s.\n' "$avd_name" "$serial"
else
    if [[ ! -x $emulator_check ]]; then
        printf 'Error: emulator-check not found under %s.\n' "$sdk_dir/emulator" >&2
        exit 1
    fi
    "$emulator_check" accel

    printf 'Starting AVD %s...\n' "$avd_name"
    "$emulator" \
        -avd "$avd_name" \
        -no-audio \
        -no-boot-anim \
        </dev/null >/dev/null 2>&1 &

    printf 'Waiting for AVD %s to connect to adb...\n' "$avd_name"
    device_deadline=$((SECONDS + 240))
    while ((SECONDS < device_deadline)); do
        if serial=$(find_running_serial); then
            break
        fi
        sleep 2
    done
    if [[ -z $serial ]]; then
        printf 'Error: AVD %s did not become available to adb in time.\n' "$avd_name" >&2
        exit 1
    fi
fi

printf 'Waiting for AVD %s to finish booting...\n' "$avd_name"
boot_complete=
boot_deadline=$((SECONDS + 240))
while ((SECONDS < boot_deadline)); do
    boot_complete=$(
        "$adb" -s "$serial" shell getprop sys.boot_completed 2>/dev/null |
            tr -d '\r'
    ) || boot_complete=
    if [[ $boot_complete == 1 ]]; then
        break
    fi
    sleep 2
done
if [[ $boot_complete != 1 ]]; then
    printf 'Error: AVD %s did not finish booting in time.\n' "$avd_name" >&2
    exit 1
fi

printf 'Installing APK on %s...\n' "$serial"
"$adb" -s "$serial" install -r "$apk"

printf 'Launching anycalc...\n'
"$adb" -s "$serial" shell am start -n "$application_id/.MainActivity"
