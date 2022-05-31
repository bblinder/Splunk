#!/usr/bin/env bash

# Programatically launching an emulated android device without the need for booting up Android Studio.
# Assumes you have the Android SDK/platform tools installed alongside Android Studio.

set -euo pipefail

android_SDK_directory="/Users/$(whoami)/Library/Android/sdk"

if [[ ! -d "$android_SDK_directory" ]] ; then
    echo "::: Android SDK not found."
    exit 1
fi

# export the AVD device name as an environmental variable.
# ex: "Pixel_4_XL_Android_12"
"$android_SDK_directory"/emulator/emulator -avd $AVD_DEVICE_NAME -netdelay none -netspeed full