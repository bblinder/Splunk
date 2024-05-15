#!/bin/bash

# Description: This script calculates the average number of containers per pod,
# the total number of containers, the total number of pods, and the total number of nodes in a Kubernetes cluster.

# Get the list of pods and their containers
pods=$(kubectl get pods --all-namespaces -o jsonpath='{range .items[*]}{.metadata.name}{" "}{.spec.containers[*].name}{"\n"}{end}')

# Count the number of containers per pod
container_counts=$(echo "$pods" | awk '{print $1}' | uniq -c | awk '{print $1}')

# Calculate the total number of containers and the number of pods
total_containers=$(echo "$container_counts" | awk '{sum += $1} END {print sum}')
total_pods=$(echo "$container_counts" | wc -l)

# Calculate the average number of containers per pod
average_containers_per_pod=$(echo "scale=2; $total_containers / $total_pods" | bc)

# Calculate the total number of containers in the cluster
total_containers_cluster=$(kubectl get pods --all-namespaces -o jsonpath='{range .items[*]}{.spec.containers[*].name}{"\n"}{end}' | wc -l)

# Calculate the total number of pods in the cluster
total_pods_cluster=$(kubectl get pods --all-namespaces --no-headers | wc -l)

# Calculate the total number of nodes in the cluster
total_nodes_cluster=$(kubectl get nodes --no-headers | wc -l)

echo "Total number of containers in the cluster: $total_containers_cluster"
echo "Total number of pods in the cluster: $total_pods_cluster"
echo "Total number of nodes in the cluster: $total_nodes_cluster"
echo "Average number of containers per pod: $average_containers_per_pod"

