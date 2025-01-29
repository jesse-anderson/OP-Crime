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
import googlemaps
import zipfile

from utils import (
    load_env_vars,
    normalize_location,
    load_json_cache,
    save_json_cache,
    fetch_pdf_links,
    download_pdf,
    extract_data_from_pdf,
    clean_narrative_basic,
    process_narrative_nlp,
    parse_date,
    clean_text,
    get_lat_long,
    get_api_call_count,
    extract_year,
    git_commit_and_force_push, 
    synchronize_repository,
    upload_files
)

# Ensure you've downloaded stopwords once:
# nltk.download('stopwords')


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
    github_repo_path = Path(os.getenv("GITHUB_REPO_OP_CRIME"))
    synchronize_repository(github_repo_path)
    googlemaps_api_key = os.getenv("GOOGLEMAPS_API_KEY")
    # print(googlemaps_api_key)
    if not googlemaps_api_key:
        raise ValueError("Google Maps API key not found in environment variables.")

    # Initialize Google Maps client
    try:
        gmaps_client = googlemaps.Client(key=googlemaps_api_key)
    except Exception as e:
        logging.critical(f"Failed to initialize Google Maps client: {e}")
        print(f"Failed to initialize Google Maps client: {e}")
        return

    # Define paths relative to script directory
    base_url = 'https://www.oak-park.us/Public-Safety/Police-Department/Reports-Maps/Activity-Reports'
    download_dir = script_dir / 'downloaded_pdfs'
    data_dir = script_dir / 'data'
    cache_dir = script_dir / 'cache'
    data_dir.mkdir(parents=True, exist_ok=True)
    cache_dir.mkdir(parents=True, exist_ok=True)

    output_csv_path = data_dir / 'summary_report.csv'
    output_zip_path = data_dir / 'summary_report.zip'
    cache_path = cache_dir / 'pdf_cache.json'
    location_cache_path = cache_dir / 'location_cache.json'
    reprocess = True
    redownload = True
    reprocess_locs = False    # Flag for reprocessing locations

    # Create download directory if it doesn't exist
    download_dir.mkdir(parents=True, exist_ok=True)

    # Load caches
    pdf_cache = load_json_cache(cache_path)
    location_cache = load_json_cache(location_cache_path)

    # Initialize complaint number tracker
    complaint_number_tracker = defaultdict(int)  # Tracks occurrence of each complaint number

    # Initialize existing complaint numbers
    existing_complaint_numbers = set()
    # Prioritize zip file
    if output_zip_path.exists():
        try:
            existing_df = pd.read_csv(output_zip_path, compression='zip', encoding="cp1252", encoding_errors='replace')
            existing_complaint_numbers = set(existing_df["Complaint #"].dropna())
            logging.info(f"Loaded existing data from '{output_zip_path}'.")
            print(f"Loaded existing data from '{output_zip_path}'.")
        except Exception as e:
            logging.warning(f"Could not read CSV from zip '{output_zip_path}': {e}")
            print(f"Warning: Could not read CSV from zip '{output_zip_path}': {e}")
    elif output_csv_path.exists():
        try:
            existing_df = pd.read_csv(output_csv_path, encoding="cp1252", encoding_errors='replace')
            existing_complaint_numbers = set(existing_df["Complaint #"].dropna())
            logging.info(f"Loaded existing data from '{output_csv_path}'.")
            print(f"Loaded existing data from '{output_csv_path}'.")
        except Exception as e:
            logging.warning(f"Could not read existing CSV '{output_csv_path}': {e}")
            print(f"Warning: Could not read existing CSV '{output_csv_path}': {e}")
    else:
        logging.info("No existing data found. Starting fresh.")
        print("No existing data found. Starting fresh.")

    # Fetch PDF links
    pdf_links = fetch_pdf_links(base_url)
    logging.info(f"Found {len(pdf_links)} PDF links to process.")
    print(f"Found {len(pdf_links)} PDF links to process.")

    all_report_data = []
    all_log_entries = []

    complaints_processed = 0
    invalid_dates_count = 0
    complaints_with_errors = 0
    duplicate_complaints_count = 0  # Initialize duplicate complaints count

    for pdf_link in pdf_links:
        pdf_url = pdf_link
        pdf_path = download_pdf(pdf_url, download_dir, redownload=redownload)
        # print(pdf_url)
        if not pdf_path:
            continue  # Skip if download failed

        filename = Path(pdf_path).name
        try:
            pdf_size = Path(pdf_path).stat().st_size
            pdf_mtime = Path(pdf_path).stat().st_mtime
        except OSError as e:
            logging.error(f"Failed to get stats for '{pdf_path}': {e}")
            print(f"Failed to get stats for '{pdf_path}': {e}")
            continue

        cache_info = pdf_cache.get(filename, {})
        if cache_info:
            cached_size = cache_info.get("file_size", -1)
            cached_mtime = cache_info.get("last_modified", -1)
            pdf_all_err_free = cache_info.get("all_error_free", False)
            complaint_list = cache_info.get("complaints", [])

            if (
                pdf_size == cached_size
                and pdf_mtime == cached_mtime
                and pdf_all_err_free
                and all(c in existing_complaint_numbers for c in complaint_list)
            ):
                logging.info(f"Skipping '{filename}' (cache says all error-free + all in CSV + unchanged).")
                print(f"Skipping '{filename}' (cache says all error-free + all in CSV + unchanged).")
                continue
            else:
                logging.info(f"Reprocessing '{filename}' because changed or missing from CSV...")
                print(f"Reprocessing '{filename}' because changed or missing from CSV...")
        else:
            logging.info(f"No cache entry for '{filename}'; processing...")
            print(f"No cache entry for '{filename}'; processing...")

        # **Pass existing_complaint_numbers to prevent double processing**
        report_data, log_entries = extract_data_from_pdf(
            pdf_path,
            gmaps_client,
            location_cache,
            reprocess_locs,
            existing_complaint_numbers,  # Pass existing complaint numbers
            pdf_url
        )

        if not report_data:
            logging.warning(f"No new data extracted from '{filename}'.")
            continue

        all_error_free = True
        complaint_nums = []
        for row in report_data:
            complaints_processed += 1
            if row["Date"] == "1900-01-01":
                invalid_dates_count += 1
            if row["Error Free"] == 0:
                complaints_with_errors += 1
                all_error_free = False
            
            complaint_num = row["Complaint #"]
            complaint_number_tracker[complaint_num] += 1  # Increment count

            complaint_nums.append(complaint_num)

        pdf_cache[filename] = {
            "complaints": complaint_nums,
            "all_error_free": all_error_free,
            "file_size": pdf_size,
            "last_modified": pdf_mtime
        }

        all_report_data.extend(report_data)
        all_log_entries.extend(log_entries)

    # Save caches
    save_json_cache(cache_path, pdf_cache)
    save_json_cache(location_cache_path, location_cache)

    if all_report_data:
        try:
            if output_zip_path.exists():
                existing_df = pd.read_csv(output_zip_path, compression='zip', encoding="cp1252", encoding_errors='replace')
                new_df = pd.DataFrame(all_report_data)

                combined_df = pd.concat([existing_df, new_df], ignore_index=True)
                combined_df.drop_duplicates(subset=["Complaint #", "File Name"], keep="first", inplace=True)
                combined_df.sort_values(by="Date", ascending=False, inplace=True)

                # Calculate duplicates BEFORE writing to zip
                complaint_counts = combined_df['Complaint #'].value_counts()
                duplicate_complaints = complaint_counts[complaint_counts > 1]
                num_unique_duplicate_complaints = duplicate_complaints.count()
                duplicate_complaints_count += num_unique_duplicate_complaints  # Update the count

                # Optional: Log the duplicated complaint numbers
                if not duplicate_complaints.empty:
                    duplicate_list = duplicate_complaints.index.tolist()
                    logging.info(f"Duplicated Complaint Numbers: {duplicate_list}")
                    print(f"Duplicated Complaint Numbers: {duplicate_list}")

                # Write to a temporary CSV before zipping
                temp_csv = data_dir / 'summary_report.csv'
                combined_df.to_csv(
                    temp_csv,
                    index=False,
                    encoding="cp1252",
                    errors="replace"
                )

                # Zip the CSV
                with zipfile.ZipFile(output_zip_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
                    zipf.write(temp_csv, arcname='summary_report.csv')

                # Remove the temporary CSV
                # temp_csv.unlink()

                logging.info(f"Appended new data to '{output_zip_path}'.")
                print(f"Appended new data to '{output_zip_path}'.")
            else:
                new_df = pd.DataFrame(all_report_data)
                new_df.drop_duplicates(subset=["Complaint #", "File Name"], keep="first", inplace=True)
                new_df.sort_values(by="Date", ascending=False, inplace=True)

                # Calculate duplicates BEFORE writing to zip
                complaint_counts = new_df['Complaint #'].value_counts()
                duplicate_complaints = complaint_counts[complaint_counts > 1]
                num_unique_duplicate_complaints = duplicate_complaints.count()
                duplicate_complaints_count += num_unique_duplicate_complaints  # Update the count

                # Optional: Log the duplicated complaint numbers
                if not duplicate_complaints.empty:
                    duplicate_list = duplicate_complaints.index.tolist()
                    logging.info(f"Duplicated Complaint Numbers: {duplicate_list}")
                    print(f"Duplicated Complaint Numbers: {duplicate_list}")

                # Write to a temporary CSV before zipping
                temp_csv = data_dir / 'summary_report.csv'
                new_df.to_csv(
                    temp_csv,
                    index=False,
                    encoding="cp1252",
                    errors="replace"
                )

                # Zip the CSV
                with zipfile.ZipFile(output_zip_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
                    zipf.write(temp_csv, arcname='summary_report.csv')

                # Remove the temporary CSV
                # temp_csv.unlink()

                logging.info(f"Created new zip archive '{output_zip_path}'.")
                print(f"Created new '{output_zip_path}'.")
        except Exception as e:
            logging.error(f"Error writing to zip '{output_zip_path}': {e}")
            print(f"Error writing to zip '{output_zip_path}': {e}")

    # Prepare logging messages
    end_time = time.time()
    end_time_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    total_time_sec = end_time - start_time

    # Calculate duplicate counts
    # Unique complaint numbers with more than one occurrence
    num_unique_duplicate_complaints = sum(1 for count in complaint_number_tracker.values() if count > 1)

    time_messages = [
        f"Start Time: {start_time_str}",
        f"End Time: {end_time_str}",
        f"Total Processing Time: {total_time_sec:.2f} seconds"
    ]
    summary_counters = [
        f"Total complaints processed: {complaints_processed}",
        f"Number of incorrectly parsed dates (1900-01-01): {invalid_dates_count}",
        f"Number of complaints with errors (Error Free = 0): {complaints_with_errors}",
        f"Number of duplicate complaint numbers: {num_unique_duplicate_complaints}",  # NEW
        f"Total Geocoding API calls made: {get_api_call_count()}"  # NEW: API call count
    ]

    final_logs = []
    final_logs.extend(all_log_entries)
    final_logs.extend(time_messages)
    final_logs.extend(summary_counters)

    log_file_path = script_dir / f"logs_{datetime.now().strftime('%Y-%m-%d')}.txt"
    try:
        with log_file_path.open('w', encoding="utf-8") as log_file:
            log_file.write("\n".join(final_logs))
        logging.info(f"Logs written to '{log_file_path}'.")
        print(f"Logs written to '{log_file_path}'.")
    except OSError as e:
        logging.error(f"Failed to write logs to '{log_file_path}': {e}")
        print(f"Failed to write logs to '{log_file_path}': {e}")

    # Compute the "error rate"
    # Here, we'll define error_rate as fraction of complaints that had "Error Free = 0"
    # Example: 5% = 0.05,  or you could do 5.00 for 5%.
    error_rate = 0.0
    if complaints_processed > 0:
        error_rate = complaints_with_errors / complaints_processed *100

    # Overwrite error_rate into a text file
    error_rate_file = script_dir / "error_rate.txt"
    try:
        with error_rate_file.open('w', encoding="utf-8") as f:
            # Format: "error_rate = 5%"
            # If you prefer a percentage, multiply by 100 and add '%'
            f.write(f"error_rate = {error_rate:.4f} %\n")
        logging.info(f"Error rate written to '{error_rate_file}'.")
        print(f"Error rate written to '{error_rate_file}'.")
    except OSError as e:
        logging.error(f"Failed to write error rate to '{error_rate_file}': {e}")
        print(f"Failed to write error rate to '{error_rate_file}': {e}")

    for message in time_messages:
        print(message)
    for counter in summary_counters:
        print(counter)

    print("Finished processing.")

    # Now we synchronize, upload files, and force-push changes:
    commit_message = f"Automated update on {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"

    # Upload desired files (e.g., logs and error_rate file) to a target subfolder
    files_to_upload = [log_file_path, error_rate_file]
    target_subfolder = "crime_map_outputs"  # Adjust as needed
    upload_files(github_repo_path, files_to_upload, target_subfolder)

    #  Stage and force-push everything
    git_commit_and_force_push(github_repo_path, commit_message)

    print("daily crime map update process completed with forced Git push.")
    logging.info("daily crime map update process completed with forced Git push.")
if __name__ == '__main__':
    # Configure logging
    script_dir = Path(__file__).parent.resolve()  # Ensure log file is in script directory
    logging.basicConfig(
        filename=script_dir / f'processing_{datetime.now().strftime("%Y_%m_%d_%H_%M_%S")}.log',  # Updated to store log in script directory
        level=logging.DEBUG,
        format='%(asctime)s - %(levelname)s - %(message)s'
    )
    
    # Ensure stopwords are downloaded: nltk.download('stopwords')
    main()
