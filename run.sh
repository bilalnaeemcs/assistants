#!/usr/bin/expect -f

# Set timeout to -1 to wait indefinitely
set timeout -1

# Start the Python script
spawn python3 ./assistant.py

# Wait for the prompt
expect "Enter your prompt (or 'quit' to exit, 'rate' to change speech rate): "

# Send the question
send "what is AI\r"

# Continue interacting
interact
