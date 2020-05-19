FROM gitlab.cloudcix.com:5005/cloudcix/robot/base
# Move the settings and ssh keys into the correct place
RUN cp deployment/settings/netsoc-cork01.py ./settings.py && \
    rm -rf deployment
