"""
Deploy tyo GitHub

When a new file or directory is added to the top level of Robot, this will need to be added to the rynsc queue.

e.g. rsync -a new_file.py ../../github
     rsync -a new_directory/ ../../github
"""

# Ensure rsync is installed
echo "Step 1/7: Install rsync utility"
apt update && apt install -y rsync

# Scan the github host key
echo "Step 2/7: mssh-keyscan github's key"
ssh-keyscan -H github.com >> ~/.ssh/known_hosts

# Read the current version for the Robot deployment commit message
echo "Step 3/7: Read the current version"
VERSION=$(sed -n -e "s/__version__ = '\(.*\)'/\1/p" "__init__.py")

# Set up Git for the container
echo "Step 4/7: Configure git"
git config --global user.email '40232684+CloudCIX-Bot@users.noreply.github.com'
git config --global user.name 'CloudCIX-Bot'

# Clone the GitHub repo into the docker container
echo "Step 5/7: Clone the repo"
git clone git@github.com:CloudCIX/robot.git ../../github

# rsync files to the github repo
rsync -a builders/ ../../github
rsync -a deployment_sample/ ../../github
rsync -a dispatchers/ ../../github
rsync -a metrics/ ../../github
rsync -a mixins/ ../../github
rsync -a quiescers ../../github
rsync -a restarters/ ../../github
rsync -a scrubbers/ ../../github
rsync -a tasks/ ../../github
rsync -a templates/ ../../github
rsync -a updaters/ ../../github
rsync -a __init__.py ../../github
rsync -a celery_app.py ../../github
rsync -a CHANGELOG.md ../../github
rsync -a cloudcix_token.py ../../github
rsync -a email_notifier.py ../../github
rsync -a LICENSE ../../github
rsync -a README.md ../../github
rsync -a robot.py ../../github
rsync -a settings.py.template ../../github
rsync -a state.py ../../github
rsync -a utils.py ../../github

# cd to the github repo, commit and push
echo "Step 6/7:  Commit and push the docs"
cd ../../github
git add --all
git commit -m "Robot updates v$VERSION"
git push origin master

# Clean up the docker container by deleting the cloned repo
echo "Step 7/7: Clean up the container by deleting the cloned repo"
cd ..
rm -rf github
