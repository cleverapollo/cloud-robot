# Link the settings file to the correct place
cp "deployment/settings/$ROBOT_ENV.py" ./settings.py
# Run the robot script
python3 robot.py
