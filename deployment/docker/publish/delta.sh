#!/bin/bash

printf "Pulling latest docker images from Gitlab"
docker login --username cloudcixdevelopers --password $DOCKERHUB_PW > /dev/null

# Pull the latest delta docker image from gitlab
IMAGE='gitlab.cloudcix.com:5005/cloudcix/robot/delta:latest'
docker pull $IMAGE

# Tag latest, and push them to docker hub
printf "Tagging and pushing images to dockerhub"
NAME='cloudcix/robot'
TAGS=("delta")

for TAG in "${TAGS[@]}"; do
    docker tag $IMAGE $NAME:$TAG
    docker push $NAME:$TAG
done
