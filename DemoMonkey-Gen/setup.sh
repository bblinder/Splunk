#!/usr/bin/env bash

# This script must be run with the virtual environment activated.
# Installs and/or updates the required packages.

set -Eeuo pipefail
trap 'echo "Error at line $LINENO" >&2' ERR

script_dir=$(cd "$(dirname "${BASH_SOURCE[0]}")" &>/dev/null && pwd -P)

show_help() {
    echo "Usage: $0 [option...]"
    echo "Installs and/or updates the required packages in an activated virtual environment."
    echo ""
    echo "Options:"
    echo "  -h, --help    Show this help message and exit"
}

while [[ $# -gt 0 ]]; do
    case $1 in
        -h|--help)
            show_help
            exit 0
            ;;
        *)
            echo "Invalid option: $1"
            show_help
            exit 1
            ;;
    esac
    shift
done

# Check if the virtual environment is activated
if [[ -z "${VIRTUAL_ENV:-}" ]]; then
    echo "Please activate the virtual environment before running this script."
    echo "You can do this with the following commands:"
    echo "1. python3 -m venv venv"
    echo "2. source $script_dir/venv/bin/activate"
    exit 1
fi

python_packages(){
    if [[ ! -f "$script_dir/requirements.txt" ]]; then
        echo "requirements.txt file not found at $script_dir/requirements.txt"
        exit 1
    fi
    "$VIRTUAL_ENV/bin/pip3" install --upgrade -r "$script_dir/requirements.txt"
}

signalflow_update(){
    "$VIRTUAL_ENV/bin/pip3" install git+https://github.com/signalfx/signalflow-cli --upgrade
}

python_packages
signalflow_update
