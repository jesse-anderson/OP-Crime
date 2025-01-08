#!/bin/bash

# Define repository directories
OP_CRIME_DIR="/home/pi/Desktop/OP-Crime"
JESSE_REPO_DIR="/home/pi/Desktop/jesse-anderson.github.io"

# Define log directory
LOG_DIR="/home/pi/Desktop/OP-Crime/logs"

# Ensure log directory exists
mkdir -p "$LOG_DIR"

# Function to update a repository
update_repo() {
    local repo_dir="$1"
    local repo_name="$2"
    
    echo "$(date): Starting update for $repo_name." >> "$LOG_DIR/update_jesse_repo.log"
    
    cd "$repo_dir" || { echo "$(date): Failed to navigate to $repo_dir." >> "$LOG_DIR/update_jesse_repo.log"; exit 1; }
    
    # Activate virtual environment if needed
    if [ -f "$OP_CRIME_DIR/venv/bin/activate" ]; then
        source "$OP_CRIME_DIR/venv/bin/activate"
    fi
    
    # Pull the latest changes
    git pull origin main >> "$LOG_DIR/update_jesse_repo.log" 2>&1
    
    if [ $? -eq 0 ]; then
        echo "$(date): Successfully updated $repo_name." >> "$LOG_DIR/update_jesse_repo.log"
    else
        echo "$(date): Error updating $repo_name." >> "$LOG_DIR/update_jesse_repo.log"
    fi
    
    # Deactivate virtual environment
    if [ -f "$OP_CRIME_DIR/venv/bin/deactivate" ]; then
        deactivate
    fi
}

# Update OP-Crime Repository
update_repo "$OP_CRIME_DIR" "OP-Crime"

# Update jesse-anderson.github.io Repository
update_repo "$JESSE_REPO_DIR" "jesse-anderson.github.io"

echo "$(date): All repositories updated." >> "$LOG_DIR/update_jesse_repo.log"
