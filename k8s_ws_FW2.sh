#!/bin/bash
#
# Foundational Workshop #1 Tasks - Linux Ubuntu NOVA instance
#
# The following script sets all components for a kubernetes | otel workshop and sets up
# participants to start running Foundational Workshop #2
#
# author:  Franco Ferrero-Poschetto
# title:   Staff Solutions Engineer, Splunk
#
# version: 1.0.0
#
# What this script does:
#  - Foundational Workshop #1
#      - sets up all environment variables - public_ip, hostname, etc
#      - downloads | installs minikube
#      - downloads | installs kubectl
#      - configures docker for the splunk user
#      - downloads | build | containerizes the petclinic java application
#
# Global variables
export WORKSHOP_NUM=1
export WS_USER="demo"
export LOCAL_IP=$(ec2metadata --local-ipv4)
#export PUBLIC_IP=$(ec2metadata --local-ipv4)
sleep 1
#
# make sure we are in our home directory
date_string="$(date)"
echo -n "** $date_string - $WORKSHOP_NUM step - os: change to home directory"
echo "** $date_string - $WORKSHOP_NUM step - os: change to home directory" >> ~/debug.txt
cd ~/; sleep 1
if [ $? = 0 ]; then
echo " .... done"
else
echo " .... failed"
fi
#
# Install java
#
date_string="$(date)"
echo -n "** $date_string - $WORKSHOP_NUM step - os: installing java"
echo "** $date_string - $WORKSHOP_NUM step - os: installing java" >> ~/debug.txt
result="$(sudo apt install openjdk-17-jre -y &> /tmp/k8s_output.txt)"; sleep 1
if [ $? = 0 ]; then
echo " .... done"
else
echo " .... failed"
fi
#
# Install minikube
#
date_string="$(date)"
echo -n "** $date_string - $WORKSHOP_NUM step - os: installing minikube"
echo "** $date_string - $WORKSHOP_NUM step - os: installing minikube" >> ~/debug.txt
result="$(curl -LO https://storage.googleapis.com/minikube/releases/latest/minikube_latest_amd64.deb &> /tmp/k8s_output.txt)"; sleep 1
#
result="$(sudo dpkg -i minikube_latest_amd64.deb &> /tmp/k8s_output.txt)"; sleep 1
if [ $? = 0 ]; then
echo " .... done"
else
echo " .... failed"
fi
#
# Install kubectl
#
date_string="$(date)"
echo -n "** $date_string - $WORKSHOP_NUM step - os: installing kubectl"
echo "** $date_string - $WORKSHOP_NUM step - os: installing kubectl" >> ~/debug.txt
result="$(sudo snap install kubectl --classic &> /tmp/k8s_output.txt)"; sleep 1
if [ $? = 0 ]; then
echo " .... done"
else
echo " .... failed"
fi
#
# Install helm
#
date_string="$(date)"
echo -n "** $date_string - $WORKSHOP_NUM step - os: installing helm"
echo "** $date_string - $WORKSHOP_NUM step - os: installing helm" >> ~/debug.txt
result="$(sudo snap install helm --classic &> /tmp/k8s_output.txt)"; sleep 1
if [ $? = 0 ]; then
echo " .... done"
else
echo " .... failed"
fi
#
# Install docker
#
date_string="$(date)"
echo -n "** $date_string - $WORKSHOP_NUM step - os: installing docker"
echo "** $date_string - $WORKSHOP_NUM step - os: installing docker" >> ~/debug.txt
result="$(sudo apt install docker.io -y &> /tmp/k8s_output.txt)"; sleep 1
if [ $? = 0 ]; then
echo " .... done"
else
echo " .... failed"
fi
#
# Adding docker permissions to current user
#
date_string="$(date)"
echo -n "** $date_string - $WORKSHOP_NUM step - os: adding docker permissions to the current user"
echo "** $date_string - $WORKSHOP_NUM step - os: adding docker permissions to the current user" >> ~/debug.txt
result="$(sudo usermod -aG docker ${USER} &> /tmp/k8s_output.txt)"; sleep 1
result="$(sudo chmod 666 /var/run/docker.sock &> /tmp/k8s_output.txt)"; sleep 1
if [ $? = 0 ]; then
echo " .... done"
else
echo " .... failed"
fi
#
# configure minikube driver as docker
#
date_string="$(date)"
echo -n "** $date_string - $WORKSHOP_NUM step - os: configure minikube driver as docker"
echo "** $date_string - $WORKSHOP_NUM step - os: configure minikube driver as docker" >> ~/debug.txt
result="$(minikube config set driver docker &> /tmp/k8s_output.txt)"; sleep 1
if [ $? = 0 ]; then
echo " .... done"
else
echo " .... failed"
fi
#
# Delete minikube
#
date_string="$(date)"
echo -n "** $date_string - $WORKSHOP_NUM step - os: delete minikube"
echo "** $date_string - $WORKSHOP_NUM step - os: delete minikube" >> ~/debug.txt
result="$(minikube delete &> /tmp/k8s_output.txt)"; sleep 1
if [ $? = 0 ]; then
echo " .... done"
else
echo " .... failed"
fi
#
# Start minikube with docker driver
#
date_string="$(date)"
echo -n "** $date_string - $WORKSHOP_NUM step - os: Start minikube with docker driver"
echo "** $date_string - $WORKSHOP_NUM step - os: Start minikube with docker driver" >> ~/debug.txt
result="$(minikube start --no-vtx-check --driver=docker --subnet=192.168.49.0/24 &> /tmp/k8s_output.txt)"; sleep 1
if [ $? = 0 ]; then
echo " .... done"
else
echo " .... failed"
fi
#
sleep 30
#
# Apply a new certificate to minikube
#
date_string="$(date)"   
echo -n "** $date_string - $WORKSHOP_NUM step - os: Apply a new certificate to minikube"
echo "** $date_string - $WORKSHOP_NUM step - os: Apply a new certificate to minikube" >> ~/debug.txt
result="$(kubectl apply -f https://github.com/cert-manager/cert-manager/releases/download/v1.9.1/cert-manager.yaml &> /tmp/k8s_output.txt)"; sleep 1
if [ $? = 0 ]; then
echo " .... done"
else
echo " .... failed"
fi
#
# Stop minikube
#
date_string="$(date)"
echo -n "** $date_string - $WORKSHOP_NUM step - os: stop minikube"
echo "** $date_string - $WORKSHOP_NUM step - os: stop minikube" >> ~/debug.txt
result="$(minikube stop &> /tmp/k8s_output.txt)"; sleep 1
if [ $? = 0 ]; then
echo " .... done"
else
echo " .... failed"
fi
#
# Create minikube audit policy
#
date_string="$(date)"
echo -n "** $date_string - $WORKSHOP_NUM step - os: Create minikube audit policy"
echo "** $date_string - $WORKSHOP_NUM step - os: Create minikube audit policy" >> ~/debug.txt
mkdir -p ~/.minikube/files/etc/ssl/certs
#
cat <<EOF > ~/.minikube/files/etc/ssl/certs/audit-policy.yaml
# Log all requests at the Metadata level.
apiVersion: audit.k8s.io/v1
kind: Policy
rules:
- level: Metadata
EOF
#
if [ $? = 0 ]; then
echo " .... done"
else
echo " .... failed"
fi
#
# Start minikube using the newly created audit_policy.yaml configuration
#
date_string="$(date)"
echo -n "** $date_string - $WORKSHOP_NUM step - os: Start minikube using the newly created audit_policy.yaml configuration"
echo "** $date_string - $WORKSHOP_NUM step - os: Start minikube using the newly created audit_policy.yaml configuration" >> ~/debug.txt
result="$(minikube start --no-vtx-check --driver=docker --subnet=192.168.49.0/24 --extra-config=apiserver.audit-policy-file=/etc/ssl/certs/audit-policy.yaml --extra-config=apiserver.audit-log-path=-; eval $(minikube -p minikube docker-env) &> /tmp/k8s_output.txt)"; sleep 1
if [ $? = 0 ]; then
echo " .... done"
else
echo " .... failed"
fi
#
sleep 30
#
# Add minikube to the /etc/hosts file
#
date_string="$(date)"
echo -n "** $date_string - $WORKSHOP_NUM step - os: Add minikube to the /etc/hosts file"
echo "** $date_string - $WORKSHOP_NUM step - os: Add minikube to the /etc/hosts file" >> ~/debug.txt
result="$(echo -e "192.168.49.2\tminikube" | sudo tee --append /etc/hosts &> /tmp/k8s_output.txt)"; sleep 1
if [ $? = 0 ]; then
echo " .... done"
else
echo " .... failed"
fi
#
# Create the workshop directory and install the petclinic app
#
date_string="$(date)"
echo -n "** $date_string - $WORKSHOP_NUM step - os: Create the workshop directory and install the petclinic app"
echo "** $date_string - $WORKSHOP_NUM step - os: Create the workshop directory and install the petclinic app" >> ~/debug.txt
mkdir ~/k8s_workshop
#
mkdir ~/k8s_workshop/petclinic
#
cd ~/k8s_workshop/petclinic
#
if [ $? = 0 ]; then
echo " .... done" 
else
echo " .... failed"
fi
#
# download petclinic source from github
date_string="$(date)"
echo -n "** $date_string - $WORKSHOP_NUM step - petclinic: download petclinic source from github"
echo "** $date_string - $WORKSHOP_NUM step - petclinic: download petclinic source from github" >> ~/debug.txt
result="$(git -C ~/k8s_workshop/petclinic clone --branch springboot3 https://github.com/spring-projects/spring-petclinic.git &>> ~/debug.txt)"
if [ $? = 0 ]; then
echo " .... done"
else
echo " .... failed"
fi
#
# use MAVEN to build a new petclinic package
date_string="$(date)"
echo -n "** $date_string - $WORKSHOP_NUM step - petclinic: use MAVEN to build a new petclinic package"
echo "** $date_string - $WORKSHOP_NUM step - petclinic: use MAVEN to build a new petclinic package" >> ~/debug.txt
cd ~/k8s_workshop/petclinic/spring-petclinic
result="$(./mvnw package &> /tmp/k8s_output.txt)"; sleep 1
cat /tmp/k8s_output.txt >> ~/debug.txt
result="$(cat /tmp/k8s_output.txt | grep "BUILD SUCCESS" | awk '{print $3}')"; sleep 1
if [ $result = "SUCCESS" ]; then
echo " .... done"
else
echo " .... failed"
fi
#
# create dockerfile in petclinic target directory
date_string="$(date)"
echo -n "** $date_string - $WORKSHOP_NUM step - petclinic: create dockerfile in petclinic target directory"
echo "** $date_string - $WORKSHOP_NUM step - petclinic: create dockerfile in petclinic target directory" >> ~/debug.txt
sudo tee ~/k8s_workshop/petclinic/spring-petclinic/target/Dockerfile <<EOF >> ~/debug.txt
# syntax=docker/dockerfile:1

FROM eclipse-temurin:17-jdk-jammy

WORKDIR /app

COPY * ./

CMD ["java", "-jar", "spring-petclinic-3.0.0-SNAPSHOT.jar"]
EOF
sleep 1
#
sudo chown -R splunker:users ~/k8s_workshop; sleep 1
echo " .... done"
#
# build the petclinic docker image into the minikube docker registry
#
date_string="$(date)"
echo -n "** $date_string - $WORKSHOP_NUM step - petclinic: build the petclinic docker image into the minikube docker registry"
echo "** $date_string - $WORKSHOP_NUM step - petclinic: build the petclinic docker image into the minikube docker registry" >> ~/debug.txt
#
result="$(sudo -H -u splunker bash -c "eval \$(minikube -p minikube docker-env); cd ~/k8s_workshop/petclinic/spring-petclinic/target; docker build --tag $WS_USER/petclinic-otel:v1 ." &> /tmp/k8s_output.txt)"; sleep 1
#
cat /tmp/k8s_output.txt >> ~/debug.txt
result="$(cat /tmp/k8s_output.txt | grep "Successfully built" | awk '{print $2}')"; sleep 1
if [ $result = "built" ]; then
echo " .... done"
else
echo " .... failed"
fi
#
# create the petclinic k8s_deploy directories
date_string="$(date)"
echo -n "** $date_string - $WORKSHOP_NUM step - petclinic: create the petclinic k8s_deploy directories"
echo "** $date_string - $WORKSHOP_NUM step - petclinic: create the petclinic k8s_deploy directories" >> ~/debug.txt
#
mkdir -p ~/k8s_workshop/petclinic/k8s_deploy; sleep 1
if [ $? = 0 ]; then
echo " .... done"
else
echo " .... failed"
fi
#
# create the manifest file used to deploy the petclinic app into kubernetes
date_string="$(date)"
echo -n "** $date_string - $WORKSHOP_NUM step - petclinic: create the manifest file used to deploy the petclinic app into kubernetes"
echo "** $date_string - $WORKSHOP_NUM step - petclinic: create the manifest file used to deploy the petclinic app into kubernetes" >> ~/debug.txt
sudo tee ~/k8s_workshop/petclinic/k8s_deploy/$WS_USER-petclinic-k8s-manifest.yml <<EOF >> ~/debug.txt
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
sleep 1
echo " .... done"
sudo chown splunker:users ~/k8s_workshop/petclinic/k8s_deploy/$WS_USER-petclinic-k8s-manifest.yml
#
# pause for 1 minute(s) to allow petclinic deployment
#
date_string="$(date)"
echo -n "** $date_string - $WORKSHOP_NUM step - petclinic: pause for 1 minute(s) to allow petclinic deployment"
echo "** $date_string - $WORKSHOP_NUM step - petclinic: pause for 1 minute(s) to allow petclinic deployment" >> ~/debug.txt
sleep 60
if [ $? = 0 ]; then
echo " .... done"
else
echo " .... failed"
fi
#
# deploy the petclinic app as the splunk user
#
date_string="$(date)"
echo -n "** $date_string - $WORKSHOP_NUM step - petclinic: deploy the petclinic app in kubernetes"
echo "** $date_string - $WORKSHOP_NUM step - petclinic: deploy the petclinic app in kubernetes" >> ~/debug.txt
#
result="$(sudo -H -u splunker bash -c "eval \$(minikube -p minikube docker-env); kubectl apply -f ~/k8s_workshop/petclinic/k8s_deploy/$WS_USER-petclinic-k8s-manifest.yml" &> /tmp/k8s_output.txt)"; sleep 1
cat /tmp/k8s_output.txt >> ~/debug.txt
result="$(cat /tmp/k8s_output.txt | awk '{print $2}' | tr -d '\n')"; sleep 1
if [ $result = "createdcreated" ] || [ $result = "createdunchanged" ] || [ $result = "unchangedcreated" ] || [ $result = "unchangedunchanged" ]; then
echo " .... done"
else
echo " .... failed"
fi
#
# Environment ready foir FW2
#
echo "Environmnet ready for foundational workshop #2"
