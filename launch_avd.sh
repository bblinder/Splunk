#!/usr/bin/env bash

# Programatically launching an emulated android device without the need for booting up Android Studio.
# Assumes you have the Android SDK/platform tools installed alongside Android Studio.

# This has only been tested on Mac OS.

set -Eeuo pipefail

if [ "$(uname)" != "Darwin" ]; then
    echo "This script is only meant to be run on Mac OS."
    exit 1
fi

android_SDK_directory="/Users/$(whoami)/Library/Android/sdk"

if [[ ! -d "$android_SDK_directory" ]] ; then
    echo "::: Android SDK not found."
    exit 1
fi

# export the AVD device name as an environmental variable.
# ex: "Pixel_4_XL_Android_12"
"$android_SDK_directory"/emulator/emulator -avd $AVD_DEVICE_NAME -netdelay none -netspeed full