FROM gitlab.cloudcix.com:5005/cloudcix/robot/base
# Move the settings and ssh keys into the correct place
RUN cp deployment/settings/vodafone-cork01.py ./settings_local.py && \
    rm -rf deployment