FROM python:3.7
# Set workdir and copy context in there
WORKDIR /opt/robot
COPY . .

# Install the gitlab SSH key so we can
RUN mkdir -p ~/.ssh && install -o $(id -u) -g $(id -g) -m 600 id_rsa ~/.ssh/id_rsa && install -o $(id -u) -g $(id -g) -m 600 deployment/ssh-config ~/.ssh/config
RUN ssh-keyscan gitlab.cloudcix.com > ~/.ssh/known_hosts

# Install requirements
RUN pip3 install -r deployment/requirements.txt

# Move the supervisor conf to the correct place
RUN mv deployment/supervisord.conf /etc

# Install the Robot ssh key
RUN mkdir -p ~/.ssh && mv id_rsa ~/.ssh/id_rsa && printf '\n10.1.1.2 gitlab.cloudcix.com\n' >> /etc/hosts && ssh-keyscan gitlab.cloudcix.com > ~/.ssh/known_hosts && chmod 600 ~/.ssh/id_rsa
RUN install -o $(id -u) -g $(id -g) -m 600 deployment/ssh-key ~/.ssh/id_rsa && rm -r  ~/.ssh 

# Set up ENV vars for the Robot script
ENV CLOUDCIX_SETTINGS_MODULE settings
