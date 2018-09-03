CHILD_PID=""
# Create a method to catch SIGTERMs and pass them to the python process
handle_term() {
    kill -TERM "$CHILD_PID"
}
trap handle_term SIGTERM
# Run the robot script
python3 -u robot.py &
CHILD_PID=$!
wait "$CHILD_PID"
