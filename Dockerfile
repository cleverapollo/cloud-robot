FROM python:3.6
# Read build args
ARG RENV dev
# Set workdir and copy context in there
WORKDIR /opt/robot
COPY . .
# Install requirements
RUN pip3 install -r deployment/requirements.txt
# Load the correct settings file
cp "deployment/settings/$RENV.py" ./settings.py
# Set up ENV vars for the Robot script
ENV CLOUDCIX_SETTINGS_MODULE settings
ENV ROBOT_ENV $RENV
# Set the entry point as the robot script
ENTRYPOINT ["python3", "robot.py"]
