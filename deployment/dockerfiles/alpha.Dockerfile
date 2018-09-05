FROM gitlab.cloudcix.com:5005/cloudcix/robot/base
# Move the settings and ssh keys into the correct place
RUN cp deployment/settings/alpha.py ./settings_local.py && \
    install -m 600 -o $(id -u) -g $(id -g) deployment/ssh-keys/alpha ~/.ssh/id_rsa && \
    rm -rf deployment