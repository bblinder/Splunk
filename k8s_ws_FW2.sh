#!/bin/bash
#
# Foundational Workshop #1 Tasks - Linux Ubuntu NOVA instance
# The following script sets all components for a kubernetes | otel workshop and sets up
# participants to start running Foundational Workshop #2
#
# author: Franco Ferrero-Poschetto
# title: Staff Solutions Engineer, Splunk
#
# revisions: Brandon Blinderman
# title: Senior Solutions Architect, Splunk
#
# version: 1.1.0
# Changelog: implementing more robust setup with error handling, function usage, and checks for idempotency.
#
# TODO: implement function to undo all changes

set -uo pipefail # bash strict mode

# check that OS is linux
if [[ "$(uname -s)" != "Linux" ]]; then
  echo "This script is intended to be run on a Linux system" >&2
  exit 1
fi


# Prints log messages with timestamps and colors
log() {
  local color=${3:-"white"}
  case $color in
    "green") color=2;;
    "red") color=1;;
    *) color=7;; # default is white
  esac
  echo -e "$(tput setaf $color)::: $(date +%F\ %T) - Workshop Setup Step: $2$(tput sgr0)"
}

# handles errors and exits the script
error_exit() {
  local line=$1
  local message=${2:-"An unspecified error occurred"}
  local status=$?
  local command=$BASH_COMMAND
  echo "::: ERROR [Line $line]: Command '$command' exited with status $status. $message" >&2
  echo "::: $(date +%F\ %T) - ERROR [Line $line]: Command '$command' exited with status $status. $message" >> ~/debug.txt
  exit $status
}

# Ensure necessary tools are installed
ensure_tools_installed() {
  local line=$1
  local tools=("curl" "git" "snapd" "dpkg" "sudo" "tee" "apt" "ec2metadata")
  for tool in "${tools[@]}"; do
    if ! command -v "$tool" &>/dev/null; then
      log "$line" "Installing $tool"
      sudo apt-get install "$tool" -y &>/dev/null || error_exit "$line" "Failed to install $tool"
    fi
  done
}

# Global variables
export WORKSHOP_NUM=1
export WS_USER="demo"
export LOCAL_IP=$(ec2metadata --local-ipv4)

# Apt update
log ${LINENO} "Updating apt..."
sudo apt update -y &>/dev/null || error_exit ${LINENO} "Failed to update apt"

# Check for necessary tools
log ${LINENO} "Checking and installing necessary tools..."
ensure_tools_installed ${LINENO}

# # Check if running as root
# if [[ $EUID -ne 0 ]]; then
#     error_exit ${LINENO} "This script must be run as root"
# fi

# Start of the main script
log ${LINENO} "Changing to home directory"
cd ~/ || error_exit ${LINENO} "Failed to change to home directory"

# Install Java
if dpkg -s "openjdk-17-jre" &>/dev/null; then
  log ${LINENO} "Java is already installed"
else
  log ${LINENO} "Installing Java..."
  sudo apt install openjdk-17-jre -y &>/dev/null || error_exit ${LINENO} "Failed to install Java"
fi

# Install Minikube
if command -v minikube &>/dev/null; then
  log ${LINENO} "Minikube is already installed"
else
  log ${LINENO} "Installing Minikube..."
  sudo curl -LO https://storage.googleapis.com/minikube/releases/latest/minikube_latest_amd64.deb &>/dev/null || error_exit ${LINENO} "Failed to download Minikube"
  sudo dpkg -i minikube_latest_amd64.deb &>/dev/null || error_exit ${LINENO} "Failed to install Minikube"
fi

# Install kubectl
if command -v kubectl &>/dev/null; then
  log ${LINENO} "kubectl is already installed"
else
  log ${LINENO} "Installing kubectl..."
  sudo snap install kubectl --classic &>/dev/null || error_exit ${LINENO} "Failed to install kubectl"
fi

# Install Helm
if command -v helm &>/dev/null; then
  log ${LINENO} "Helm is already installed"
else
  log ${LINENO} "Installing Helm..."
  sudo snap install helm --classic &>/dev/null || error_exit ${LINENO} "Failed to install Helm"
fi

# Install Docker
if command -v docker &>/dev/null; then
  log ${LINENO} "Docker is already installed"
else
  log ${LINENO} "Installing Docker..."
  sudo apt install docker.io -y &>/dev/null || error_exit ${LINENO} "Failed to install Docker"
fi

# Adding docker permissions to current user
log ${LINENO} "Adding docker permissions to current user..."
sudo usermod -aG docker "${USER}" &>/dev/null || error_exit ${LINENO} "Failed to modify docker user group"
sudo chmod 666 /var/run/docker.sock &>/dev/null || error_exit ${LINENO} "Failed to change docker socket permissions"

# Configure minikube driver to docker
log ${LINENO} "Configuring minikube driver to docker..."
minikube config set driver docker &>/dev/null || error_exit ${LINENO} "Failed to set Minikube driver"

# delete minikube cluster
log ${LINENO} "Deleting minikube cluster"
minikube delete &>/dev/null || error_exit ${LINENO} "Failed to delete Minikube cluster"

# Start minikube cluster with docker driver
log ${LINENO} "Starting minikube cluster with docker driver..."
minikube start --no-vtx-check --driver=docker --subnet=192.168.49.0/24 &>/dev/null || error_exit ${LINENO} "Failed to start Minikube cluster"

# sleep for 30 seconds
log ${LINENO} "Waiting for cluster to spin up..."
sleep 30

# apply a new certificate to minikube
log ${LINENO} "Applying a new certificate to minikube"
kubectl apply -f https://github.com/cert-manager/cert-manager/releases/download/v1.9.1/cert-manager.yaml &>/dev/null || error_exit ${LINENO} "Failed to apply new certificate to Minikube"

# stop minikube cluster
log ${LINENO} "Stopping minikube cluster"
minikube stop &>/dev/null || error_exit ${LINENO} "Failed to stop Minikube cluster"

# create minikube audit policy
log ${LINENO} "Creating minikube audit policy"
mkdir -p ~/.minikube/files/etc/ssl/certs
cat <<EOF > ~/.minikube/files/etc/ssl/certs/audit-policy.yaml
# log all requests at the Metadata level.
apiVersion: audit.k8s.io/v1
kind: Policy
rules:
- level: Metadata
EOF
if [[ $? -ne 0 ]]; then
  error_exit ${LINENO} "Failed to create minikube audit policy"
fi

# start minikube with the newly created audit policy
log ${LINENO} "Starting minikube with the newly created audit policy..."
minikube start --no-vtx-check --driver=docker --subnet=192.168.49.0/24 --extra-config=apiserver.audit-policy-file=/etc/ssl/certs/audit-policy.yaml --extra-config=apiserver.audit-log-path=- &>/dev/null; eval $(minikube -p minikube docker-env) &>/dev/null || error_exit ${LINENO} "Failed to start Minikube cluster with new audit policy"

# sleep for 30 seconds
log ${LINENO} "Waiting for minikube cluster to start..."
sleep 30

# add minikube to the /etc/hosts file
log ${LINENO} "Adding minikube to /etc/hosts..."
minikube_ip=$(minikube ip)
if [[ -z $minikube_ip ]]; then
  error_exit ${LINENO} "Failed to get minikube ip address"
fi
# save original /etc/hosts file
log ${LINENO} "Saving original /etc/hosts file..."
cat /etc/hosts | sudo tee /etc/hosts.bak &>/dev/null || error_exit ${LINENO} "Failed to save original /etc/hosts file"
echo -e "$minikube_ip\tminikube" | sudo tee --append /etc/hosts &>/dev/null || error_exit ${LINENO} "Failed to add minikube to /etc/hosts file"

# create the workshop directories and installing the petclinic app
log ${LINENO} "Creating the workshop directories and installing the petclinic app"
mkdir -p ~/k8s_workshop/petclinic/k8s_deploy || error_exit ${LINENO} "Failed to create workshop directories"
cd ~/k8s_workshop/petclinic || error_exit ${LINENO} "Failed to change to petclinic directory"

# download the petclinic app from github
log ${LINENO} "Downloading the petclinic app from github"
git -C ~/k8s_workshop/petclinic clone --branch springboot3 https://github.com/spring-projects/spring-petclinic.git &>/dev/null || error_exit ${LINENO} "Failed to download the petclinic app from github"

# use MAVEN to build the petclinic app
log ${LINENO} "Using MAVEN to build the petclinic app... this may take a while..."
cd ~/k8s_workshop/petclinic/spring-petclinic || error_exit ${LINENO} "Failed to change to petclinic directory"

# Run the build command
./mvnw package &>/tmp/k8s_output.txt || error_exit ${LINENO} "Failed to build the petclinic app"
build_status=$?

if [ $build_status -eq 0 ] && grep -q "BUILD SUCCESS" /tmp/k8s_output.txt; then
  log ${LINENO} "Build completed successfully"
else
  error_exit ${LINENO} "Build did not complete successfully, check /tmp/k8s_output.txt for details"
fi

# create dockerfile in petclinic target directory
log ${LINENO} "Creating dockerfile in petclinic target directory"
sudo tee ~/k8s_workshop/petclinic/spring-petclinic/target/Dockerfile <<EOF &>/dev/null
# syntax=docker/dockerfile:1

FROM eclipse-temurin:17-jdk-jammy

WORKDIR /app

COPY * ./

CMD ["java", "-jar", "spring-petclinic-3.0.0-SNAPSHOT.jar"]
EOF

if [[ $? -ne 0 ]]; then
  error_exit ${LINENO} "Failed to create dockerfile in petclinic target directory"
fi

# changing ownership of the petclinic directory
log ${LINENO} "Changing ownership of the petclinic directory"
sudo chown -R splunker:users ~/k8s_workshop || error_exit ${LINENO} "Failed to change ownership of the petclinic directory"

# build the petclinic docker image
log ${LINENO} "Building the petclinic docker image"
result="$(sudo -H -u splunker bash -c "eval \$(minikube -p minikube docker-env); cd ~/k8s_workshop/petclinic/spring-petclinic/target; docker build --tag $WS_USER/petclinic-otel:v1 ." &>/tmp/k8s_output.txt)"
result="$(grep "Successfully built" /tmp/k8s_output.txt | awk '{print $2}')"
if [[ "$result" == "built" ]]; then
  log ${LINENO} "Petclinic docker image built successfully"
else
  log ${LINENO} "Petclinic docker image build failed"
fi

# create the manifest file for the petclinic deployment
log ${LINENO} "Creating the manifest file for the petclinic deployment"
sudo tee ~/k8s_workshop/petclinic/k8s_deploy/$WS_USER-petclinic-k8s-manifest.yml <<EOF &>/dev/null
apiVersion: v1
kind: Service
metadata:
  name: $WS_USER-petclinic-srv
spec:
  selector:
    app: $WS_USER-petclinic-otel-app
  ports:
  - protocol: TCP
    port: 8080
    nodePort: 30000
  type: NodePort
---
apiVersion: apps/v1
kind: Deployment
metadata:
   name: $WS_USER-petclinic-otel-deployment
   labels:
      app: $WS_USER-petclinic-otel-app
spec:
  selector:
    matchLabels:
      app: $WS_USER-petclinic-otel-app
  template:
    metadata:
      labels:
        app: $WS_USER-petclinic-otel-app
    spec:
      containers:
      - name: $WS_USER-petclinic-otel-container01
        image: $WS_USER/petclinic-otel:v1
        ports:
        - containerPort: 8080
EOF
if [[ $? -ne 0 ]]; then
  error_exit ${LINENO} "Failed to create the manifest file for the petclinic deployment"
fi

# deploy the petclnic app as the splunk user
log ${LINENO} "Deploying the petclinic app in the k8s cluster"
sudo -H -u splunker bash -c "eval \$(minikube -p minikube docker-env); kubectl apply -f ~/k8s_workshop/petclinic/k8s_deploy/$WS_USER-petclinic-k8s-manifest.yml" &>/tmp/k8s_output.txt
if [[ $? -ne 0 ]]; then
  error_exit ${LINENO} "Failed to deploy the petclinic app in the k8s cluster"
fi

if [[ $? -ne 0 ]]; then
  error_exit ${LINENO} "Failed to deploy the petclinic app in the k8s cluster" "red"
fi

log ${LINENO} "Environment ready for Foundational Workshop #2" "green"
