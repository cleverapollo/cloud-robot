#!/bin/bash

ERROR () {
    # Print ERROR in red, followed by the input string
    echo -e "\e[91mERROR\e[0m: $1 \n"
}
INFO () {
    # Print INFO in yellow, followed by the input string
    echo -e "\e[93mINFO\e[0m: $1 \n"
}


INFO "Fetching CloudCIX Robot version"
VERSION_FILE='__init__.py'
VERSION=$(sed --quiet --expression "s/__version__ = '\(.*\)'/\1/p" $VERSION_FILE)

INFO "Checking-out branch"
git remote set-url origin git@gitlab.cloudcix.com:CloudCIX/Robot.git
git config --global user.email "cloudadmin@cix.ie"
git config --global user.name "cloudadmin"
git checkout $CI_COMMIT_REF_NAME
git pull --tags origin $CI_COMMIT_REF_NAME

INFO "Making sure git tag doesn't exist for this version"
NEW_TAG="v$VERSION"
GIT_TAGS=$(git tag --list $NEW_TAG)
if [ -n "$GIT_TAGS" ]; then
    ERROR "A git tag already exists for this version"
    ERROR "Please update the CloudCIX version in __init__.py"
    exit 1
fi

INFO "Tagging git commit"
git tag $NEW_TAG $CI_COMMIT_SHA
git push --tags --push-option=ci.skip # Don't trigger new pipeline
if [ "$?" -ne 0 ]; then
    ERROR "Failed to push tags back to gitlab"
    exit 1
else
    INFO "Tagged commit (${CI_COMMIT_SHA:0:8}) as $NEW_TAG"
fi

INFO "Pulling latest docker image from gitlab"
IMAGE='gitlab.cloudcix.com:5005/cloudcix/robot/opensource-base:latest'
docker pull $IMAGE

BASE_LIST=(`echo $V | tr '.' ' '`)
V_MAJOR=${BASE_LIST[0]}
V_MINOR=${BASE_LIST[1]}

# Tag the major, minor, and latest, and push them to docker hub
INFO "Tagging and pushing images to dockerhub"
NAME='cloudcix/robot'
TAGS=($V_MAJOR $V_MAJOR.$V_MINOR "latest")

docker login --username cloudcixdevelopers --password $DOCKERHUB_PW > /dev/null
for TAG in "${TAGS[@]}"; do
    docker tag $IMAGE $NAME:$TAG
    docker push $NAME:$TAG
    if [ "$?" -ne 0 ]; then
	ERROR "Couldn't push $NAME:$TAG to DockerHub"
    fi
done
