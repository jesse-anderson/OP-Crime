#!/bin/bash

# Navigate to the repository
cd /home/pi/Desktop/OP-Crime

# Reset any local changes
git reset --hard

# Pull the latest changes
git pull origin main

# Log the update and script execution
echo "$(date): Repository updated and scripts executed successfully." >> /home/pi/Desktop/logs/update_repo.log
