FROM '### BASE IMAGE URL ###'/robot/base
# Move the settings and ssh keys into the correct place
RUN cp deployment/settings/region_n+1.py ./settings.py && \
    rm -rf deployment
