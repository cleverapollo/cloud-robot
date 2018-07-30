FROM python:3.6
# Set workdir and copy context in there
WORKDIR /opt/robot
COPY . .
# Install requirements
RUN pip3 install -r deployment/requirements.txt
# Set up ENV vars for the Robot script
ENV CLOUDCIX_SETTINGS_MODULE settings
ENV ROBOT_ENV dev
# Set the entry point as the robot script
ENTRYPOINT ["/bin/bash", "entrypoint.sh"]
