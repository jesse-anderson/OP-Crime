#!/bin/bash

# Navigate to the repository directory
cd /home/pi/Desktop/OP-Crime || { echo "Failed to navigate to /home/pi/Desktop/OP-Crime"; exit 1; }

# Pull the latest changes from GitHub
git pull origin main >> /home/pi/Desktop/logs/update_repo.log 2>&1

# Activate the virtual environment
source /home/pi/Desktop/venv/bin/activate

# Run the Python scripts
python OakPark_Crime_Reporting_Web.py >> /home/pi/Desktop/logs/OakPark_Crime_Reporting_Web.log 2>&1

deactivate