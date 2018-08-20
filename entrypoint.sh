$CHILD_PID=""
# Link the settings file to the correct place
cp "deployment/settings/$ROBOT_ENV.py" ./settings.py
install -o 1 -g 1 -m 600 "deployment/ssh-keys/$ROBOT_ENV" ~/.ssh/id_rsa
# Delete the deployment folder after copying
rm -rf deployment
# Create a method to catch SIGTERMs and pass them to the python process
handle_term() {
    kill -TERM "$CHILD_PID"
}
trap handle_term SIGTERM
# Run the robot script
python3 -u robot.py &
CHILD_PID=$!
wait "$CHILD_PID"