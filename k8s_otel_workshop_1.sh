#!/usr/bin/env bash

set -Eeuo pipefail

script_dir=$(cd "$(dirname "${BASH_SOURCE[0]}")" &>/dev/null && pwd -P)

die() {
  echo "Error: $1" >&2
  exit 1
}

usage() {
  cat <<EOF
Usage: $(basename "${BASH_SOURCE[0]}") [-h] [-v] [-c]

Script to test setup of a minikube environment with audit logging and server name resolution.

Available options:

-h, --help      Print this help and exit
-v, --verbose   Print script debug info
-c, --cleanup   Perform cleanup tasks and exit
EOF
  exit
}

cleanup() {
  trap - SIGINT SIGTERM ERR EXIT

  # Stop minikube
  minikube stop || echo "Failed to stop minikube"
  # Delete all minikube configurations
  minikube delete || echo "Failed to delete minikube configurations"
  # Remove minikube hostname from /etc/hosts
  sudo sed -i '/minikube/d' /etc/hosts || echo "Failed to remove minikube hostname from /etc/hosts"
  # Remove audit policy file and directory
  rm -rf ~/.minikube/files/etc/ssl/certs || echo "Failed to remove audit policy file and directory"
}

setup_minikube() {
  # Set minikube driver to docker
  minikube config set driver docker

  # Delete all minikube configurations
  minikube delete || die "Failed to delete minikube configurations"

  # Start a new minikube environment from scratch
  minikube start --no-vtx-check --driver=docker --subnet=192.168.49.0/24 || die "Failed to start minikube"

  # Test that minikube is running
  minikube status || die "Minikube is not running"

  # Check configured minikube nodes
  kubectl get nodes || die "Failed to get minikube nodes"

  # Install a new cert-manager
  kubectl apply -f \
   https://github.com/cert-manager/cert-manager/releases/download/v1.9.1/cert-manager.yaml || die "Failed to install cert-manager"

  # Stop minikube
  minikube stop || die "Failed to stop minikube"

  # Create directory where our Audit Policy will live: ~/.minikube/files/etc/ssl/certs
  mkdir -p ~/.minikube/files/etc/ssl/certs || die "Failed to create directory for audit policy"

  # Create a VERY basic audit-policy.yaml file
  cat <<EOF > ~/.minikube/files/etc/ssl/certs/audit-policy.yaml
# Log all requests at the Metadata level.
apiVersion: audit.k8s.io/v1
kind: Policy
rules:
- level: Metadata
EOF

  # Restart our minikube environment with the new audit policy configuration
  minikube start --no-vtx-check --driver=docker --subnet=192.168.49.0/24 \
   --extra-config=apiserver.audit-policy-file=/etc/ssl/certs/audit-policy.yaml \
   --extra-config=apiserver.audit-log-path=- || die "Failed to restart minikube with audit policy"

  eval $(minikube -p minikube docker-env) || die "Failed to set minikube docker environment"
}

setup_name_resolution() {
  # Check the IP address of minikube and add it to /etc/hosts
  minikube_ip=$(minikube ip)
  if [[ -z "$minikube_ip" ]]; then
    die "Failed to get minikube IP address"
  fi

  # Add the minikube IP address to /etc/hosts
  echo -e "$minikube_ip\tminikube" | sudo tee --append /etc/hosts || die "Failed to add minikube IP to /etc/hosts"

  # Test our new name resolution
  nslookup minikube || die "Failed to resolve minikube hostname"
}

prompt_cleanup() {
  read -p "Do you want to run cleanup tasks now? This will remove any minikube clusters. [y/N]: " -r
  if [[ $REPLY =~ ^[Yy]$ ]]; then
    trap cleanup SIGINT SIGTERM ERR EXIT
  fi
}

main() {
  # Ensuring this will only run on Linux
  if [[ "$OSTYPE" != "linux-gnu"* ]]; then
    die "This script is intended to run on Linux only"
  fi

  # Check that minikube and kubectl are installed
  if ! command -v minikube &>/dev/null; then
    die "minikube is required"
  fi

  if ! command -v kubectl &>/dev/null; then
    die "kubectl is required"
  fi

  local cleanup=false
  local verbose=false

  while :; do
    case "${1-}" in
    -h | --help) usage ;;
    -v | --verbose) verbose=true ;;
    -c | --cleanup) cleanup=true ;;
    -?*) die "Unknown option: $1" ;;
    *) break ;;
    esac
    shift
  done

  args=("$@")

  [[ $verbose == true ]] && set -x

  if [[ $cleanup == true ]]; then
    cleanup
    exit 0
  fi

  setup_minikube
  setup_name_resolution

  prompt_cleanup
}

main "$@"
