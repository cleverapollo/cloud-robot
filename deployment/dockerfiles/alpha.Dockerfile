FROM gitlab.cloudcix.com:5005/cloudcix/robot/base
# Move the settings and ssh keys into the correct place
RUN cp deployment/settings/alpha.py ./settings.py && \
    rm -rf deployment
RUN pip3 install -U git+https://cloudadmin:C1xacc355@gitlab.cloudcix.com/CloudCIX/SDKs/Python@ipam-compute
