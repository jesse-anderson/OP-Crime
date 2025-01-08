#!/bin/bash

# Navigate to the repository
cd /home/pi/Desktop/OP-Crime

# Activate virtual environment
source venv/bin/activate

# Optional: Stash any local changes
git stash

# Pull the latest changes
git pull origin main

# Optional: Reapply stashed changes
git stash pop

# Deactivate virtual environment
deactivate

# Log the update
echo "$(date): Repository updated successfully." >> ~/Desktop/OP-Crime/update.log
