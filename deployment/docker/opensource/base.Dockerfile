FROM python:3.7

# Prevents Python from buffering stdout and stderr (equivalent to python -u option)
ENV PYTHONUNBUFFERED=1
# Prevents Python from writing pyc files to disc (equivalent to python -B option)
ENV PYTHONDONTWRITEBYTECODE=1
# Prevents user interfaces
ENV DEBIAN_FRONTEND=noninteractive

# Update pip
RUN pip3 install -U pip

# Set workdir and copy context in there
WORKDIR /opt/robot
COPY . .

# Install requirements
RUN pip3 install -r deployment/requirements.txt 

# Create SSH folder for ssh keypairs
RUN mkdir -p ~/.ssh

# Create images folder for robot-drive mount point
RUN mkdir -p /mnt/images

# copy settings_template.py as settings.py and move the supervisor conf to the correct place
RUN cp deployment/settings_template.py ./settings.py && mv deployment/supervisord.conf /etc && rm -rf deployment

# Set up ENV vars for the Robot script
ENV CLOUDCIX_SETTINGS_MODULE settings
ENV ROBOT_ENV dev
ENV ORGANIZATION_URL example.com
ENV POD_NAME pod
ENV COP_NAME cop
ENV ROBOT_API_USERNAME user@example.com
ENV ROBOT_API_KEY 64_characters_max
ENV ROBOT_API_PASSWORD pw
ENV EMAIL_HOST mail.example.com
ENV EMAIL_USER notifications@example.com
ENV EMAIL_PASSWORD email_pw
ENV EMAIL_PORT 25
ENV EMAIL_REPLY_TO no-reply@example.com
ENV NETWORK_PASSWORD ntw_pw
ENV PAM_NAME pam
ENV PAM_ORGANIZATION_URL example.com
ENV VIRTUAL_ROUTERS_ENABLED True
