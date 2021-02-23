FROM gitlab.cloudcix.com:5005/cloudcix/robot/py2base:latest
# Move the settings and ssh keys into the correct place
RUN cp deployment/settings/gov_cork.py ./settings.py && \
    rm -rf deployment
