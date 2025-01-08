#!/bin/bash

# Navigate to the repository
cd /home/pi/Desktop/OP-Crime

# Activate virtual environment
source venv/bin/activate

# Reset any local changes
git reset --hard

# Pull the latest changes
git pull origin main

# Deactivate virtual environment
deactivate

# Log the update and script execution
echo "$(date): Repository updated and scripts executed successfully." >> ~/Desktop/OP-Crime/update.log
