#!/bin/bash

printf "Fetching CloudCIX Robot version\n"
VERSION_FILE='__init__.py'
V=$(sed -n -e "s/__version__ = '\(.*\)'/\1/p" $VERSION_FILE)

git remote set-url origin git@gitlab.cloudcix.com/CloudCIX/Robot.git
git config --global user.email "cloudadmin@cix.ie"
git config --global user.name "cloudadmin"
git checkout $CI_COMMIT_REF_NAME
git pull origin $CI_COMMIT_REF_NAME

# Make sure the version has been updated
GIT_V=$(git tag -l --sort=-refname | head -n 1)
if [ "$GIT_V" == "$V" ]; then
    printf "CloudCIX version in __init__.py has not been updated. A git tag already exists for this version.\n"
    exit 1
fi

# Tag the commit
git tag $V $CI_COMMIT_REF_NAME
printf "Successfully tagged commit as version $V"

# Pull the latest opensource docker image from gitlab
IMAGE='gitlab.cloudcix.com:5005/cloudcix/robot/opensource-base:latest'
docker pull $IMAGE

BASE_LIST=(`echo $V | tr '.' ' '`)
V_MAJOR=${BASE_LIST[0]}
V_MINOR=${BASE_LIST[1]}

# Tag the major, minor, and latest, and push them to docker hub
printf "Tagging and pushing images to dockerhub"
NAME='cloudcix/robot'
TAGS=($V_MAJOR $V_MAJOR.$V_MINOR "latest")

docker login --username cloudcixdevelopers --password $DOCKERHUB_PW > /dev/null
for TAG in "${TAGS[@]}"; do
    docker tag $IMAGE $NAME:$TAG
    docker push $NAME:$TAG
done
