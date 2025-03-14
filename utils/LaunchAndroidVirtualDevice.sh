#!/usr/bin/env bash

# Programatically launching an emulated android device without the need for booting up Android Studio.
# Assumes you have the Android SDK/platform tools installed alongside Android Studio.

# This has only been tested on Mac OS.

# Usage:
#   -h, --help         Show this help message and exit.
#   -l, --list-avds    List available Android Virtual Devices.
#   [AVD_NAME]         Launch specified Android Virtual Device.

set -Eeuo pipefail

# Default SDK path
android_SDK_directory="${ANDROID_SDK_ROOT:-/Users/$(whoami)/Library/Android/sdk}"

function print_usage() {
    echo "Usage: $0 [options] [AVD_NAME]"
    echo "Options:"
    echo "  -h                Display this help menu."
    echo "  -l                List available AVDs."
    echo "  -i                Install Android SDK platform tools if not installed."
    echo "  -s                Setup an AVD (requires manual input)."
}

function install_sdk() {
    if ! command -v brew &>/dev/null; then
        echo "Homebrew is not installed. Please install Homebrew first."
        exit 1
    fi
    echo "Installing Android SDK platform tools..."
    brew install --cask android-platform-tools
    echo "Android SDK platform tools installed."
}

function setup_avd() {
    echo "Setting up Android Virtual Device..."
    echo "Please follow the instructions here: https://developer.android.com/studio/run/managing-avds"
    open "https://developer.android.com/studio/run/managing-avds"
}

function list_avds() {
    "$android_SDK_directory/emulator/emulator" -list-avds | grep -v 'INFO'
    exit 0
}

function launch_avd() {
    if [[ -z $1 ]]; then
        echo "Error: AVD name is required if not listing AVDs."
        print_usage
        exit 1
    fi
    "$android_SDK_directory/emulator/emulator" -avd "$1" -netdelay none -netspeed full
    exit 0
}

function check_dependencies() {
    if [[ ! -x "$(command -v grep)" ]]; then
        echo "Error: grep is not installed."
        exit 1
    fi
    if [[ ! -d "$android_SDK_directory" || ! -x "$android_SDK_directory/emulator/emulator" ]]; then
        echo "Error: Android SDK or emulator not correctly set at $android_SDK_directory."
        exit 1
    fi
}

OPTIND=1
while getopts "hlis" opt; do
    case "$opt" in
        h)
            print_usage
            exit 0
            ;;
        l)
            list_avds
            ;;
        i)
            install_sdk
            exit 0
            ;;
        s)
            setup_avd
            exit 0
            ;;
        \?)
            print_usage
            exit 1
            ;;
    esac
done
shift $((OPTIND -1))

check_dependencies

# Check if an AVD name is provided as argument or environment variable
if [[ -z "${1:-}" && -z "${AVD_DEVICE_NAME:-}" ]]; then
    echo "Error: No AVD name provided."
    print_usage
    exit 1
fi

# Use command line argument as AVD name or fallback to environment variable
AVD_NAME="${1:-$AVD_DEVICE_NAME}"

launch_avd "$AVD_NAME"
