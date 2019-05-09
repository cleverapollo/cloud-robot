FROM python:3.7
# Set workdir and copy context in there
WORKDIR /opt/robot
COPY . .

# SSH Stuff
RUN mkdir -p ~/.ssh && install -o $(id -u) -g $(id -g) -m 600 id_rsa ~/.ssh/id_rsa && install -o $(id -u) -g $(id -g) -m 600 deployment/ssh-config ~/.ssh/config
RUN ssh-keyscan gitlab.cloudcix.com > ~/.ssh/known_hosts

# Install requirements
RUN pip3 install -r deployment/requirements.txt

# Create the celerybeat schedule file
RUN touch /opt/robot/celerybeat.schedule

# Set up ENV vars for the Robot script
ENV CLOUDCIX_SETTINGS_MODULE settings
ENV ROBOT_ENV dev

# Set the entry point as the robot script
ENTRYPOINT ["celery", "-A", "celery_app"]
CMD ["beat", "-s", "/opt/robot/celerybeat.schedule"]
