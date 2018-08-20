FROM python:3.7
# Set workdir and copy context in there
WORKDIR /opt/robot
COPY . .

# SSH Stuff
RUN mkdir -p ~/.ssh && install -o 1 -g 1 -m 600 id_rsa ~/.ssh/id_rsa
RUN ssh-keyscan gitlab.cloudcix.com > ~/.ssh/known_hosts

# Install requirements
RUN pip3 install -r deployment/requirements.txt

# Set up ENV vars for the Robot script
ENV CLOUDCIX_SETTINGS_MODULE settings
ENV ROBOT_ENV dev

# Set the entry point as the robot script
ENTRYPOINT ["/bin/bash", "entrypoint.sh"]
