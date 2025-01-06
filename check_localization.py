# check_localization.py

import os
import re
import json
import pandas as pd
from pathlib import Path
import logging
from collections import defaultdict
import time
from datetime import datetime
import string

from utils import load_env_vars, normalize_location, load_json_cache, save_json_cache, load_csv_data

def main():
    start_time = time.time()
    start_time_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    # Determine the directory where this script resides
    script_dir = Path(__file__).parent.resolve()

    # Path to the environment variables file relative to script directory
    env_file_path = script_dir / "env_vars.txt"

    # Load environment variables
    try:
        load_env_vars(env_file_path)
    except FileNotFoundError as e:
        print(e)
        return

    # Initialize logging
    log_file_path = script_dir / f"check_localization_logs_{datetime.now().strftime('%Y-%m-%d')}.txt"
    logging.basicConfig(
        filename=script_dir / 'check_localization.log',  # Log file in script directory
        level=logging.DEBUG,
        format='%(asctime)s - %(levelname)s - %(message)s'
    )

    # Define paths relative to script directory
    data_dir = script_dir / 'data'
    cache_dir = script_dir / 'cache'
    data_dir.mkdir(parents=True, exist_ok=True)
    cache_dir.mkdir(parents=True, exist_ok=True)

    output_csv_path = data_dir / 'summary_report.csv'
    output_zip_path = data_dir / 'summary_report.zip'
    location_cache_path = cache_dir / 'location_cache.json'
    
    # Load location cache
    location_cache = load_json_cache(location_cache_path)

    # Load CSV data
    csv_df = load_csv_data(output_csv_path, output_zip_path)
    if csv_df.empty:
        print("No data to process. Exiting.")
        logging.info("No data to process. Exiting.")
        return

    # Ensure required columns exist
    required_columns = ["Location", "Complaint #", "File Name", "Lat", "Long"]
    for col in required_columns:
        if col not in csv_df.columns:
            print(f"Error: Required column '{col}' not found in the CSV.")
            logging.error(f"Required column '{col}' not found in the CSV.")
            return

    # Extract unique location strings from the CSV
    unique_locations = csv_df["Location"].dropna().unique()
    print(f"Total unique locations in CSV: {len(unique_locations)}")
    logging.info(f"Total unique locations in CSV: {len(unique_locations)}")

    # Normalize location strings
    normalized_locations = set(normalize_location(loc) for loc in unique_locations)
    print(f"Total normalized unique locations: {len(normalized_locations)}")
    logging.info(f"Total normalized unique locations: {len(normalized_locations)}")

    # Initialize missing info
    missing_info = defaultdict(list)  # {normalized_location: [list of dicts with Complaint # and File Name]}
    updated_locations = 0  # Counter for updated cache entries

    # Iterate through the CSV to process each location
    for index, row in csv_df.iterrows():
        loc = row.get("Location", "")
        normalized_loc = normalize_location(loc)
        if not normalized_loc:
            continue  # Skip if location is empty after normalization

        lat = row.get("Lat", None)
        lng = row.get("Long", None)

        # Check if the location is already in the cache
        if normalized_loc in location_cache:
            # If cache has [null, null], try to update with CSV coordinates
            if (location_cache[normalized_loc][0] is None or location_cache[normalized_loc][1] is None) and pd.notna(lat) and pd.notna(lng):
                location_cache[normalized_loc] = [lat, lng]
                updated_locations += 1
                logging.info(f"Updated cache for '{normalized_loc}' with coordinates: ({lat}, {lng})")
        else:
            # If not in cache, add to missing_info if coordinates are missing
            if pd.isna(lat) or pd.isna(lng):
                missing_info[normalized_loc].append({
                    "Complaint #": row.get("Complaint #", "N/A"),
                    "File Name": row.get("File Name", "N/A")
                })
                location_cache[normalized_loc] = [None, None]
                logging.info(f"Added missing location to cache: '{normalized_loc}' with [null, null]")
            else:
                # Add location with existing coordinates from CSV
                location_cache[normalized_loc] = [lat, lng]
                logging.info(f"Added location to cache: '{normalized_loc}' with coordinates: ({lat}, {lng})")

    # Calculate total missing entries
    total_missing_entries = sum(len(details) for details in missing_info.values())
    print(f"Number of locations missing in cache: {len(missing_info)}")
    print(f"Total missing location entries in CSV: {total_missing_entries}")
    logging.info(f"Number of locations missing in cache: {len(missing_info)}")
    logging.info(f"Total missing location entries in CSV: {total_missing_entries}")
    print(f"Number of cache entries updated with existing coordinates: {updated_locations}")
    logging.info(f"Number of cache entries updated with existing coordinates: {updated_locations}")

    if missing_info:
        # Save the missing information to a JSON file
        missing_report_path = data_dir / 'missing_locations_report.json'
        try:
            with missing_report_path.open('w', encoding='utf-8') as report_file:
                json.dump(missing_info, report_file, indent=2)
            print(f"Missing locations report saved to '{missing_report_path}'.")
            logging.info(f"Missing locations report saved to '{missing_report_path}'.")
        except OSError as e:
            logging.error(f"Failed to save missing locations report to '{missing_report_path}': {e}")
            print(f"Error: Failed to save missing locations report to '{missing_report_path}': {e}")
        
        # Additionally, print a summary of missing locations
        print("\nSummary of Missing Locations:")
        for loc, details in missing_info.items():
            print(f"\nNormalized Location: {loc}")
            print(f"Number of Missing Entries: {len(details)}")
            for entry in details:
                print(f"  - Complaint #: {entry['Complaint #']}, File Name: {entry['File Name']}")
        
        # Log the summary
        for loc, details in missing_info.items():
            logging.info(f"\nNormalized Location: {loc}")
            logging.info(f"Number of Missing Entries: {len(details)}")
            for entry in details:
                logging.info(f"  - Complaint #: {entry['Complaint #']}, File Name: {entry['File Name']}")
    else:
        print("No missing locations found. All locations are already present in the cache.")
        logging.info("No missing locations found. All locations are already present in the cache.")

    # Save the updated location cache
    try:
        save_json_cache(location_cache_path, location_cache)
        print(f"Location cache updated and saved to '{location_cache_path}'.")
        logging.info(f"Location cache updated and saved to '{location_cache_path}'.")
    except Exception as e:
        logging.error(f"Failed to save updated location cache to '{location_cache_path}': {e}")
        print(f"Error: Failed to save updated location cache to '{location_cache_path}': {e}")

    # Prepare logging messages
    end_time = time.time()
    end_time_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    total_time_sec = end_time - start_time

    time_messages = [
        f"Start Time: {start_time_str}",
        f"End Time: {end_time_str}",
        f"Total Processing Time: {total_time_sec:.2f} seconds"
    ]

    summary_counters = [
        f"Total unique locations processed: {len(unique_locations)}",
        f"Number of normalized unique locations: {len(normalized_locations)}",
        f"Number of missing locations: {len(missing_info)}",
        f"Total missing location entries in CSV: {total_missing_entries}",
        f"Number of cache entries updated with existing coordinates: {updated_locations}"
    ]

    final_logs = []
    final_logs.extend(time_messages)
    final_logs.extend(summary_counters)

    try:
        with log_file_path.open('a', encoding="utf-8") as log_file:
            log_file.write("\n".join(final_logs) + "\n")
        logging.info(f"Logs appended to '{log_file_path}'.")
        print(f"Logs appended to '{log_file_path}'.")
    except OSError as e:
        logging.error(f"Failed to append logs to '{log_file_path}': {e}")
        print(f"Error: Failed to append logs to '{log_file_path}': {e}")

    # Print summary messages
    for message in time_messages:
        print(message)
    for counter in summary_counters:
        print(counter)

    print("Localization check completed successfully.")

if __name__ == '__main__':
    # Run the main function
    main()
