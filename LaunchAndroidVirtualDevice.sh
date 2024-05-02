#!/usr/bin/env bash

# Programatically launching an emulated android device without the need for booting up Android Studio.
# Assumes you have the Android SDK/platform tools installed alongside Android Studio.

# This has only been tested on Mac OS.

set -Eeuo pipefail

# Check if the script is being run on a Mac
if [ "$(uname)" != "Darwin" ]; then
    echo "Error: This script is only meant to be run on Mac OS."
    exit 1
fi

android_SDK_directory="/Users/$(whoami)/Library/Android/sdk"

# Check if the Android SDK directory exists
if [[ ! -d "$android_SDK_directory" ]] ; then
    echo "Error: Android SDK not found at $android_SDK_directory."
    exit 1
fi

# Check if the AVD_DEVICE_NAME environment variable is set
if [[ -z "${AVD_DEVICE_NAME:-}" ]]; then
    echo "Error: AVD_DEVICE_NAME environment variable is not set."
    exit 1
fi

# Launch the emulator
"$android_SDK_directory"/emulator/emulator -avd $AVD_DEVICE_NAME -netdelay none -netspeed full
