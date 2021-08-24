FROM gitlab.cloudcix.com:5005/cloudcix/robot/dev-test-base:latest
# Move the settings and ssh keys into the correct place
RUN cp deployment/settings/alpha.py ./settings.py && rm -rf deployment
