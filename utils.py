# utils.py

import os
import re
import json
import pandas as pd
from pathlib import Path
import logging
import string
import unicodedata
from dateutil import parser as date_parser
import requests
from bs4 import BeautifulSoup
from PyPDF2 import PdfReader
from nltk.corpus import stopwords
import googlemaps
from collections import defaultdict
import time 
import zipfile
import subprocess
import shutil
from datetime import datetime, timedelta
import base64

# Initialize the API call counter
api_call_count = 0  # Global counter for API calls

def load_env_vars(file_path):
    """
    Load environment variables from a file and set them in os.environ.

    Args:
        file_path (str or Path): The path to the environment variables file.

    Raises:
        FileNotFoundError: If the specified file does not exist.
    """
    env_file = Path(file_path)
    if not env_file.exists():
        raise FileNotFoundError(f"Environment file '{file_path}' not found.")
    
    with env_file.open('r') as f:
        for line in f:
            # Remove leading/trailing whitespace
            line = line.strip()
            # Skip empty lines and comments
            if not line or line.startswith('#'):
                continue
            # Split into key and value
            if '=' in line:
                key, value = line.split('=', 1)
                key = key.strip()
                value = value.strip()
                os.environ[key] = value
                print(f"Loaded environment variable: {key}")  # Optional: Remove in production
            else:
                print(f"Ignoring invalid line in env file: {line}")  # Optional: Remove in production

def normalize_location(loc_str):
    """
    Normalize the location string to ensure consistency in caching.
    
    Steps:
    - Convert to lowercase.
    - Remove leading/trailing whitespace.
    - Remove punctuation.
    - Replace multiple spaces with a single space.
    - Standardize common street suffixes.
    
    Args:
        loc_str (str or float): The original location string.

    Returns:
        str: The normalized location string.
    """
    if not isinstance(loc_str, str):
        if pd.isna(loc_str):
            loc_str = ""
        else:
            loc_str = str(loc_str)
    
    if not loc_str:
        return ""
    
    # Convert to lowercase
    loc_str = loc_str.lower()
    # Remove leading/trailing whitespace
    loc_str = loc_str.strip()
    # Remove punctuation
    loc_str = loc_str.translate(str.maketrans('', '', string.punctuation))
    # Replace multiple spaces with a single space
    loc_str = re.sub(r'\s+', ' ', loc_str)
    # Standardize suffixes
    loc_str = standardize_suffix(loc_str)
    return loc_str

def standardize_suffix(address):
    """
    Standardize common street suffixes to ensure consistency.

    Args:
        address (str): The address string.

    Returns:
        str: The address with standardized suffixes.
    """
    suffix_mapping = {
        "st": "street",
        "ave": "avenue",
        "blvd": "boulevard",
        "rd": "road",
        "ln": "lane",
        "dr": "drive",
        "ct": "court",
        "pl": "place",
        "ter": "terrace",
        "cir": "circle",
        # Add more suffixes as needed
    }
    tokens = address.split()
    if tokens:
        last_token = tokens[-1]
        if last_token in suffix_mapping:
            tokens[-1] = suffix_mapping[last_token]
    return ' '.join(tokens)

def load_json_cache(cache_path):
    """
    Load JSON cache from the specified path.

    Args:
        cache_path (Path): Path to the JSON cache file.

    Returns:
        dict: The loaded cache data.
    """
    cache_file = Path(cache_path)
    if cache_file.exists():
        try:
            with cache_file.open('r', encoding='utf-8') as f:
                return json.load(f)
        except (json.JSONDecodeError, OSError) as e:
            logging.warning(f"Failed to load cache '{cache_path}': {e}")
            return {}
    return {}

def save_json_cache(cache_path, data):
    """
    Save JSON cache to the specified path.

    Args:
        cache_path (Path): Path to save the JSON cache.
        data (dict): Data to be saved in the cache.
    """
    cache_file = Path(cache_path)
    try:
        with cache_file.open('w', encoding='utf-8') as f:
            json.dump(data, f, indent=2)
    except OSError as e:
        logging.error(f"Failed to save cache '{cache_path}': {e}")

def load_csv_data(csv_path, zip_path):
    """
    Load CSV data from a regular CSV or a zipped CSV.

    Args:
        csv_path (Path): Path to the CSV file.
        zip_path (Path): Path to the ZIP file.

    Returns:
        DataFrame: Pandas DataFrame containing the CSV data.
    """
    if zip_path.exists():
        try:
            df = pd.read_csv(zip_path, compression='zip', encoding="cp1252", encoding_errors='replace')
            logging.info(f"Loaded data from zip '{zip_path}'.")
            print(f"Loaded data from zip '{zip_path}'.")
            return df
        except Exception as e:
            logging.error(f"Failed to read CSV from zip '{zip_path}': {e}")
            print(f"Error: Failed to read CSV from zip '{zip_path}': {e}")
    elif csv_path.exists():
        try:
            df = pd.read_csv(csv_path, encoding="cp1252", encoding_errors='replace')
            logging.info(f"Loaded data from CSV '{csv_path}'.")
            print(f"Loaded data from CSV '{csv_path}'.")
            return df
        except Exception as e:
            logging.error(f"Failed to read CSV '{csv_path}': {e}")
            print(f"Error: Failed to read CSV '{csv_path}': {e}")
    else:
        logging.error(f"No CSV or ZIP file found at '{csv_path}' or '{zip_path}'.")
        print(f"Error: No CSV or ZIP file found at '{csv_path}' or '{zip_path}'.")
    return pd.DataFrame()  # Return empty DataFrame on failure

def clean_text(text):
    """
    Normalize text from PDF pages.

    Args:
        text (str): Raw text extracted from a PDF.

    Returns:
        str: Cleaned and normalized text.
    """
    if not isinstance(text, str):
        logging.warning(f"Expected string for text cleaning, got {type(text)}. Converting to string.")
        text = str(text)
    text = unicodedata.normalize("NFKD", text)
    text = re.sub(r"\n+", " ", text)
    text = re.sub(r"\s{2,}", " ", text)
    return text.strip()

def parse_date(date_str):
    """
    Parse a date string -> 'YYYY-MM-DD' or '1900-01-01' if fail.

    This function attempts to handle multiple date formats, including:
      - D MMM YYYY (e.g., 1 Jan 2023)
      - MM/DD/YYYY
      - YYYY-MM-DD
      - etc.

    Steps:
      1) If the string is empty, return '1900-01-01'.
      2) Normalize common delimiters like hyphens, en-dashes, em-dashes, slashes, etc.
      3) Use a regex to find possible date substrings.
      4) Parse using dateutil.parser with dayfirst=True (adjust if needed).
      5) Return the 'latest' date if multiple are found, or '1900-01-01' if none.
    """
    if not date_str:
        return "1900-01-01"
    date_str = date_str.strip()
    # Replace multiple dashes or slashes with a single hyphen
    # Example: "12/01/2023 – 12/02/2023" -> "12-01-2023 - 12-02-2023"
    date_str = re.sub(r'\s*[-–—/]\s*', '-', date_str)

    # date_pattern = (
    #     r'(\d{1,2}[A-Za-z]{3}\d{2,4}|'      
    #     r'\d{1,2}-[A-Za-z]{3}-\d{2,4})'
    # )

    # # Extended date patterns to capture more variations
    date_pattern = (
        r'(\d{1,2}[A-Za-z]{3}-\d{2,4})|'     # e.g. "1Jan-2023" or "12Dec-21"
        r'(\d{1,2}-[A-Za-z]{3}-\d{2,4})|'    # e.g. "1-Jan-2023"
        r'(\d{1,2}\s[A-Za-z]{3,9}\s\d{2,4})|' # e.g. "1 Jan 2023"
        r'([A-Za-z]{3,9}\s\d{1,2},\s?\d{4})|' # e.g. "January 1, 2023"
        r'(\d{4}-\d{2}-\d{2})|'              # e.g. "2023-01-01"
        r'(\d{1,2}/\d{1,2}/\d{4})|'          # e.g. "12/31/2023"
        r'(\d{1,2}\s[A-Za-z]{4,9}\s\d{4})'   # e.g. "1 January 2023"
    )
    matches = re.findall(date_pattern, date_str, flags=re.IGNORECASE)

    # The regex above returns a tuple for each match, so flatten them
    # Each match might be something like ('12/31/2023', '', '', '', '', '', '')
    # We'll filter out empty strings below

    flattened = []
    for match_tuple in matches:
        for m in match_tuple:
            if m.strip():
                flattened.append(m.strip())

    # If no matches, just attempt a direct parse in case there's a weird format
    if not flattened:
        try:
            dt = date_parser.parse(date_str, dayfirst=True, fuzzy=True)
            return dt.strftime("%Y-%m-%d")
        except:
            return "1900-01-01"

    # If there's at least one match, parse them all
    parsed_dates = []
    for d in flattened:
        try:
            dt = date_parser.parse(d, dayfirst=True, fuzzy=True)
            parsed_dates.append(dt)
        except:
            continue

    # If any valid dates were parsed, return the latest
    if parsed_dates:
        return max(parsed_dates).strftime("%Y-%m-%d")

    # If we got here, everything failed
    return "1900-01-01"

def clean_narrative_basic(narrative):
    """
    Lightly clean the original narrative:
      - Lowercase
      - Reduce multiple spaces
    (No punctuation removal or stopword removal.)

    Args:
        narrative (str): The original narrative text.

    Returns:
        str: Lightly cleaned narrative.
    """
    lowercased = narrative.lower()
    light_clean = re.sub(r"\s+", " ", lowercased).strip()
    return light_clean

def process_narrative_nlp(narrative):
    """
    Full NLP cleaning of the narrative:
      - Remove punctuation
      - Lowercase
      - Remove English stopwords

    Args:
        narrative (str): The original narrative text.

    Returns:
        str: Fully processed narrative.
    """
    narrative_no_punct = narrative.translate(str.maketrans('', '', string.punctuation))
    narrative_lower = narrative_no_punct.lower()
    tokens = narrative_lower.split()
    stop_words = set(stopwords.words('english'))
    tokens_clean = [t for t in tokens if t not in stop_words]
    processed = " ".join(tokens_clean)
    return processed

def fetch_pdf_links(base_url):
    """
    Fetch PDF links from Oak Park site.

    Args:
        base_url (str): The base URL to fetch PDFs from.

    Returns:
        list: List of PDF URLs.
    """
    try:
        response = requests.get(base_url)
        response.raise_for_status()
    except requests.RequestException as e:
        logging.error(f"Failed to fetch PDF links from '{base_url}': {e}")
        return []

    soup = BeautifulSoup(response.content, 'html.parser')
    pdf_links = []
    for link in soup.find_all('a', href=True):
        href = link['href']
        if href.lower().endswith('.pdf'):
            if href.startswith('http'):
                pdf_links.append(href)
            else:
                pdf_links.append('https://www.oak-park.us' + href)
    return pdf_links

def download_pdf(url, download_dir, redownload=False):
    """
    Download a PDF if not already downloaded (unless redownload=True).

    Args:
        url (str): The URL of the PDF to download.
        download_dir (str or Path): The directory to save the downloaded PDF.
        redownload (bool): If True, download even if the file exists.

    Returns:
        str or None: Path to the downloaded PDF or None if failed.
    """
    download_path = Path(download_dir)
    download_path.mkdir(parents=True, exist_ok=True)
    local_filename = download_path / Path(url).name

    if not redownload and local_filename.exists():
        return str(local_filename)

    try:
        resp = requests.get(url)
        resp.raise_for_status()
        with local_filename.open('wb') as f:
            f.write(resp.content)
        logging.info(f"Downloaded: {local_filename}")
        print(f"Downloaded: {local_filename}")
        return str(local_filename)
    except requests.RequestException as e:
        logging.error(f"Failed to download '{url}': {e}")
        print(f"Failed to download '{url}': {e}")
        return None

def extract_data_from_pdf(file_path, gmaps_client, location_cache, reprocess_locs, existing_complaint_numbers):
    """
    Extract data from PDF, returning (report, log_entries).
    Only processes complaints not already in existing_complaint_numbers.

    Args:
        file_path (str or Path): Path to the PDF file.
        gmaps_client (googlemaps.Client): Initialized Google Maps client.
        location_cache (dict): Cache of normalized locations to (lat, lng).
        reprocess_locs (bool): Flag to force reprocessing of locations.
        existing_complaint_numbers (set): Set of complaint numbers already processed.

    Returns:
        tuple: (list of report entries, list of log entries)
    """
    try:
        reader = PdfReader(file_path)
        raw_text = " ".join([page.extract_text() or "" for page in reader.pages])
    except Exception as e:
        logging.error(f"Failed to read PDF '{file_path}': {e}")
        return [], [f"Failed to read PDF '{file_path}': {e}"]
    text = clean_text(raw_text)
    base_url_static = 'https://www.oak-park.us/sites/default/files/police/summaries/'
    # Log a preview of the cleaned text
    logging.debug(f"Cleaned Text Preview (first 500 chars): {text[:500]}...")
    
    complaint_pattern = r"COMPLAINT NUMBER:\s*(\d{2}-\d{5})"
    offense_pattern   = r"OFFENSE:\s+([A-Z\s]+)"
    date_pattern      = r"DATE\(S\)\s*:?\s+([A-Za-z0-9\s&\-–—/]+?)(?=\s+TIME\(S\)|\s+$)"
    time_pattern      = r"TIME\(S\):\s+([\d:HRS\s\-–—]+)"
    location_pattern  = r"LOCATION:\s+(.+?)(?=\s+(?:VICTIM/ADDRESS|NARRATIVE|NARRITIVE|NARRTIVE))"
    victim_pattern    = r"VICTIM/ADDRESS:\s+(.+?)(?=\s+NARRATIVE|NARRITIVE|NARRTIVE)"
    narrative_pattern = r"NARR(?:ATIVE|ITIVE|TIVE)\s*:\s+(.+?)(?=COMPLAINT NUMBER|$)"

    complaints = re.findall(complaint_pattern, text)
    offenses   = re.findall(offense_pattern, text)
    dates      = re.findall(date_pattern, text)
    times      = re.findall(time_pattern, text)
    locations  = re.findall(location_pattern, text)
    victims    = re.findall(victim_pattern, text)
    narratives = re.findall(narrative_pattern, text)
    
    # Clean offenses
    offenses = [o.replace("DATE", "").strip() for o in offenses]
    
    report = []
    log_entries = []
    time.sleep(0.2)  # Respectful pause for API calls
    
    num_entries = len(complaints)
    logging.debug(f"Number of complaints found: {num_entries}")
    
    for i in range(num_entries):
        try:
            # Safe indexing
            comp_num = complaints[i] if i < len(complaints) else "N/A"
            
            # Skip already processed complaints
            if comp_num in existing_complaint_numbers:
                logging.info(f"Skipping already processed Complaint # {comp_num}")
                continue

            # Extract other fields
            offense  = offenses[i].strip() if i < len(offenses) else "N/A"
            time_str = times[i].strip() if i < len(times) else "N/A"
            loc_str  = locations[i].strip() if i < len(locations) else "N/A"
            victim   = victims[i].strip() if i < len(victims) else "N/A"
            narr_raw = narratives[i].strip() if i < len(narratives) else "N/A"

            # Log extracted fields
            logging.debug(f"Processing Complaint #{comp_num}:")
            logging.debug(f"  Offense: {offense}")
            logging.debug(f"  Time: {time_str}")
            logging.debug(f"  Location: {loc_str}")
            logging.debug(f"  Victim/Address: {victim}")
            logging.debug(f"  Narrative: {narr_raw}")

            # Normalize location
            normalized_loc_str = normalize_location(loc_str)

            # Clean narrative
            narrative_cleaned = clean_narrative_basic(narr_raw) if narr_raw != "N/A" else "N/A"

            # NLP processing
            if narr_raw != "N/A":
                nlp_text = process_narrative_nlp(narr_raw)
                nlp_flag = 1
            else:
                nlp_text = "N/A"
                nlp_flag = 0

            # Geocode location
            if normalized_loc_str in location_cache and not reprocess_locs:
                lat, lng = location_cache[normalized_loc_str]
                loc_flag = 1 if (lat is not None and lng is not None) else 0
                logging.debug(f"Using cached coordinates for '{normalized_loc_str}': ({lat}, {lng})")
            else:
                lat, lng = get_lat_long(loc_str, gmaps_client)
                loc_flag = 1 if (lat is not None and lng is not None) else 0
                location_cache[normalized_loc_str] = (lat, lng)
                if lat is not None and lng is not None:
                    logging.debug(f"Geocoded '{loc_str}' to ({lat}, {lng})")
                else:
                    logging.debug(f"Failed to geocode '{loc_str}'")

            # Parse date
            try:
                raw_date = dates[i] if i < len(dates) else "1900-01-01"
                # If you have multiple dates separated by '&', split them
                date_strs = raw_date.split("&")
                parsed_dates = [parse_date(d) for d in date_strs]
                # print(parsed_dates)
                parsed_date = max(parsed_dates) if parsed_dates else "1900-01-01"
            except:
                parsed_date = "1900-01-01"
                logging.debug(f"Parsed Date: {parsed_date}")

            filename=os.path.basename(file_path)
            # Extract the year from the filename
            year = extract_year(filename)
            if year:
                base_url = f"{base_url_static}{year}/"
                link = f"{base_url}{filename}"
                filename = link #crappy workaround, but whatever.
            else:
                # Handle cases where the year isn't found or is out of range
                link = "#"
                logging.warning(f"Year not found or out of range in filename: {filename}. Defaulting to filename...")
                filename = os.path.basename(file_path)

            # Create entry
            entry = {
                "Date": parsed_date,
                "Complaint #": comp_num,
                "Offense": offense,
                "Time": time_str,
                "Location": loc_str,
                "Victim/Address": victim,
                "Narrative": narrative_cleaned,  # lightly cleaned
                "NLP_Text": nlp_text,            # fully processed
                "File Name": filename,
                "Lat": lat,
                "Long": lng,
                "Loc": loc_flag,
                "nlp": nlp_flag
            }

            # Define critical fields for error checking
            critical_fields = ["Date", "Complaint #", "Offense"]

            # Check for errors
            error_reasons = []
            for field in critical_fields:
                if entry[field] in ["N/A", "1900-01-01", None]:
                    error_reasons.append(f"Missing or invalid {field}")

            if not error_reasons:
                entry["Error Free"] = 1
            else:
                entry["Error Free"] = 0
                entry["Error Reasons"] = "; ".join(error_reasons)
                
                # Log detailed error reasons
                block_pattern = (
                    rf"COMPLAINT NUMBER:\s*{re.escape(comp_num)}"
                    r".*?(?=COMPLAINT NUMBER:\s*\d{{2}}-\d{{5}}|$)"
                )
                block_match = re.search(block_pattern, text, flags=re.DOTALL | re.IGNORECASE)
                if block_match:
                    block_text = block_match.group(0).strip()
                    debug_log = f"\n[DEBUG] Error block for Complaint # {comp_num}:\n{block_text}\n"
                    logging.debug(debug_log)
                    log_entries.append(debug_log)
                else:
                    debug_log = f"[DEBUG] Could not locate block text for complaint {comp_num}"
                    logging.debug(debug_log)
                    log_entries.append(debug_log)

            report.append(entry)

        except Exception as e:
            error_message = f"Error processing complaint #{i+1} in '{file_path}': {e}"
            logging.error(error_message)
            log_entries.append(error_message)

    return report, log_entries

def get_lat_long(location_string, gmaps_client):
    """
    Attempt to geocode location string in Oak Park, IL, 60302.
    Returns (lat, long) or (None, None).

    Also increments the global api_call_count when an API call is made.

    Args:
        location_string (str): The location string to geocode.
        gmaps_client (googlemaps.Client): Initialized Google Maps client.

    Returns:
        tuple: (latitude, longitude) or (None, None) if geocoding fails.
    """
    global api_call_count  # Declare as global to modify the counter
    
    # Enhance address precision
    location_string = location_string.lower().replace("block of", "").strip()
    # Example: "1100 block of south grove" -> "1100 south grove st"
    # Add "st", "ave", etc., if known. Otherwise, Google might infer.
    
    full_address = f"{location_string.title()} Street, Oak Park, IL, 60302"  # Title case for consistency
    logging.debug(f"Attempting to geocode address: '{full_address}'")
    try:
        geocode_result = gmaps_client.geocode(full_address)
        if geocode_result:
            lat = geocode_result[0]['geometry']['location']['lat']
            lng = geocode_result[0]['geometry']['location']['lng']
            api_call_count += 1  # Increment API call counter
            logging.info(f"Geocoded '{full_address}' to ({lat}, {lng})")
            return (lat, lng)
        else:
            logging.warning(f"No geocode results for '{full_address}'")
    except googlemaps.exceptions.ApiError as api_err:
        logging.error(f"API Error for '{full_address}': {api_err}")
    except googlemaps.exceptions.TransportError as transport_err:
        logging.error(f"Transport Error for '{full_address}': {transport_err}")
    except googlemaps.exceptions.Timeout as timeout_err:
        logging.error(f"Timeout Error for '{full_address}': {timeout_err}")
    except Exception as e:
        logging.error(f"Unexpected error for '{full_address}': {e}")
    return (None, None)

def get_api_call_count():
    """
    Retrieve the current API call count.
    
    Returns:
        int: Number of API calls made.
    """
    return api_call_count

def extract_year(filename, start_year=2017, end_year=2030):
    """
    Extracts a four-digit year from the filename.
    Returns the year as a string if found and within the range.
    Returns None otherwise.
    """
    match = re.search(r'(20[1][7-9]|20[2][0-9]|2030)', filename)
    if match:
        return match.group(0)
    return None

def get_file_sha(repo_owner, repo_name, file_path, github_pat):
    """
    Checks if a file exists in the repository and returns its SHA if it does.

    Args:
        repo_owner (str): GitHub username or organization.
        repo_name (str): Repository name.
        file_path (str): Path to the file within the repository.
        github_pat (str): Personal Access Token for authentication.

    Returns:
        str or None: SHA of the file if it exists, else None.
    """
    api_url = f"https://api.github.com/repos/{repo_owner}/{repo_name}/contents/{file_path}"
    headers = {"Authorization": f"token {github_pat}"}
    
    response = requests.get(api_url, headers=headers)
    
    if response.status_code == 200:
        file_info = response.json()
        return file_info.get('sha')
    elif response.status_code == 404:
        return None
    else:
        logging.error(f"Failed to check file existence: {response.status_code} - {response.text}")
        print(f"[ERROR] Failed to check file existence: {response.status_code} - {response.text}")
        return None

def upload_file_to_github(file_path, github_repo_path, target_subfolder):
    """
    Uploads a specified file to a target subfolder within the GitHub repository
    using the GitHub API and Personal Access Token (PAT).

    Args:
        file_path (Path): Path to the file to upload.
        github_repo_path (Path): Path to the local GitHub repository (not used in API method).
        target_subfolder (str): Subfolder within the repository where the file will be placed.
    """
    try:
        GITHUB_PAT = os.getenv("GITHUB_PAT")
        if not GITHUB_PAT:
            raise ValueError("GITHUB_PAT not found in environment variables.")

        repo_owner = "jesse-anderson"  # Replace with your GitHub username or organization
        repo_name = "jesse-anderson.github.io"  # Replace with your repository name

        # Define target path within the repository
        target_path = f"{target_subfolder}/{file_path.name}"

        # Check if the file already exists to determine if it's an update or create operation
        existing_sha = get_file_sha(repo_owner, repo_name, target_path, GITHUB_PAT)

        with open(file_path, 'rb') as f:
            content = f.read()

        encoded_content = base64.b64encode(content).decode('utf-8')

        commit_message = f"Add {'update' if existing_sha else 'new'} file {file_path.name} on {datetime.now().strftime('%Y-%m-%d')}"

        data = {
            "message": commit_message,
            "content": encoded_content,
            "branch": "main"
        }

        if existing_sha:
            data["sha"] = existing_sha  # Include sha if updating an existing file

        api_url = f"https://api.github.com/repos/{repo_owner}/{repo_name}/contents/{target_path}"
        headers = {"Authorization": f"token {GITHUB_PAT}"}

        response = requests.put(api_url, json=data, headers=headers)

        if response.status_code in [200, 201]:
            action = "updated" if existing_sha else "created"
            logging.info(f"Successfully {action} {file_path.name} to GitHub.")
            print(f"Successfully {action} {file_path.name} to GitHub.")
        else:
            logging.error(f"Failed to upload {file_path.name} to GitHub. Status Code: {response.status_code}")
            print(f"Failed to upload {file_path.name} to GitHub. Status Code: {response.status_code}")
            print(response.json())

    except Exception as e:
        logging.error(f"Failed to upload {file_path.name} to GitHub: {e}")
        print(f"[ERROR] Could not upload {file_path.name} to GitHub: {e}")

def upload_files_to_github_batch(file_paths, github_repo_path, target_subfolder):
    """
    Uploads multiple files to a target subfolder within the GitHub repository
    using the GitHub API and Personal Access Token (PAT).
    """
    try:
        logging.info(f"Starting batch upload for files: {[str(fp) for fp in file_paths]}")
        print(f"Starting batch upload for files: {[str(fp) for fp in file_paths]}")

        # Define target directory and ensure it exists
        target_dir = Path(target_subfolder)
        for file_path in file_paths:
            upload_file_to_github(file_path, github_repo_path, target_subfolder)

    except Exception as e:
        logging.error(f"Failed to upload files to GitHub: {e}")
        print(f"[ERROR] Could not upload files to GitHub: {e}")


def git_commit_and_push(repo_path, commit_message):
    """
    Stages all changes, commits with the provided message, and pushes to the remote repository
    using a Personal Access Token (PAT) for authentication. Handles non-fast-forward errors
    by pulling remote changes and retrying the push.
    
    Args:
        repo_path (Path): Path to the local Git repository.
        commit_message (str): Commit message.
    """
    try:
        # Load PAT from environment variable
        github_pat = os.getenv("GITHUB_PAT")
        if not github_pat:
            logging.error("GITHUB_PAT not found in environment variables.")
            print("Error: GITHUB_PAT not found in environment variables.")
            return

        # Verify that repo_path exists and is a directory
        if not repo_path.exists() or not repo_path.is_dir():
            logging.error(f"Repository path '{repo_path}' does not exist or is not a directory.")
            print(f"Error: Repository path '{repo_path}' does not exist or is not a directory.")
            return

        # Get the original remote URL
        original_remote = subprocess.run(
            ['git', '-C', str(repo_path), 'remote', 'get-url', 'origin'],
            capture_output=True, text=True, check=True
        )
        original_remote_url = original_remote.stdout.strip()
        logging.debug(f"Original remote URL: {original_remote_url}")
        print("Original remote URL retrieved.")

        # Modify the remote URL to include the PAT
        if original_remote_url.startswith("https://"):
            # Insert PAT into the remote URL
            # Handle potential 'https://username@...' formats
            remote_with_pat = re.sub(r'^https://', f'https://{github_pat}@', original_remote_url)
        else:
            logging.error("Remote URL is not HTTPS. Cannot embed PAT.")
            print("Error: Remote URL is not HTTPS. Cannot embed PAT.")
            return

        # Set the remote URL with PAT
        subprocess.run(
            ['git', '-C', str(repo_path), 'remote', 'set-url', 'origin', remote_with_pat],
            capture_output=True, text=True, check=True
        )
        logging.debug("Remote URL updated with PAT.")
        print("Remote URL updated with PAT.")

        # Check git status before staging
        pre_add_status = subprocess.run(
            ['git', '-C', str(repo_path), 'status'],
            capture_output=True, text=True
        )
        logging.debug(f"Git status before adding:\n{pre_add_status.stdout}")
        print(f"Git status before adding:\n{pre_add_status.stdout}")

        # Stage all changes
        # Using 'git add -A' to ensure all changes (including deletions) are staged
        subprocess.run(
            ['git', '-C', str(repo_path), 'add', '-A'],
            capture_output=True, text=True, check=True
        )
        logging.info("Staged all changes.")
        print("Staged all changes.")

        # Check git status after staging
        post_add_status = subprocess.run(
            ['git', '-C', str(repo_path), 'status'],
            capture_output=True, text=True
        )
        logging.debug(f"Git status after adding:\n{post_add_status.stdout}")
        print(f"Git status after adding:\n{post_add_status.stdout}")

        # Check if there are any changes to commit
        status_result = subprocess.run(
            ['git', '-C', str(repo_path), 'status', '--porcelain'],
            capture_output=True, text=True, check=True
        )
        if not status_result.stdout.strip():
            logging.info("No changes to commit.")
            print("No changes to commit.")
            # Restore the original remote URL before exiting
            subprocess.run(
                ['git', '-C', str(repo_path), 'remote', 'set-url', 'origin', original_remote_url],
                capture_output=True, text=True, check=True
            )
            logging.debug("Restored original remote URL.")
            print("Restored original remote URL.")
            return

        # Commit changes
        commit_result = subprocess.run(
            ['git', '-C', str(repo_path), 'commit', '-m', commit_message],
            capture_output=True, text=True
        )
        if commit_result.returncode == 0:
            logging.info(f"Committed changes with message: '{commit_message}'.")
            print(f"Committed changes with message: '{commit_message}'.")
        else:
            logging.error(f"Commit failed: {commit_result.stderr}")
            print(f"Error: Commit failed: {commit_result.stderr}")
            # Restore the original remote URL before exiting
            subprocess.run(
                ['git', '-C', str(repo_path), 'remote', 'set-url', 'origin', original_remote_url],
                capture_output=True, text=True, check=True
            )
            logging.debug("Restored original remote URL.")
            print("Restored original remote URL.")
            return

        # Confirm commit
        last_commit = subprocess.run(
            ['git', '-C', str(repo_path), 'log', '-1', '--pretty=%B'],
            capture_output=True, text=True, check=True
        )
        logging.debug(f"Last commit message: {last_commit.stdout.strip()}")
        print(f"Last commit message: {last_commit.stdout.strip()}")

        # Attempt to push changes
        push_result = subprocess.run(
            ['git', '-C', str(repo_path), 'push', 'origin', 'main'],  # Change 'main' if your branch is different
            capture_output=True, text=True
        )

        if push_result.returncode == 0:
            logging.info("Pushed changes to remote repository.")
            print("Pushed changes to remote repository.")
        else:
            # Check if the error is a non-fast-forward error
            if "non-fast-forward" in push_result.stderr:
                logging.warning("Push failed due to non-fast-forward. Attempting to pull and retry push.")
                print("Push failed due to non-fast-forward. Attempting to pull and retry push.")

                # Pull remote changes with rebase to avoid unnecessary merge commits
                pull_result = subprocess.run(
                    ['git', '-C', str(repo_path), 'pull', 'origin', 'main', '--rebase'],  # Change 'main' if needed
                    capture_output=True, text=True
                )

                if pull_result.returncode == 0:
                    logging.info("Pulled remote changes successfully.")
                    print("Pulled remote changes successfully.")

                    # Retry pushing changes
                    retry_push = subprocess.run(
                        ['git', '-C', str(repo_path), 'push', 'origin', 'main'],  # Change 'main' if needed
                        capture_output=True, text=True
                    )

                    if retry_push.returncode == 0:
                        logging.info("Pushed changes to remote repository after pulling.")
                        print("Pushed changes to remote repository after pulling.")
                    else:
                        logging.error(f"Retry push failed: {retry_push.stderr}")
                        print(f"Error: Retry push failed: {retry_push.stderr}")
                else:
                    logging.error(f"Pull failed: {pull_result.stderr}")
                    print(f"Error: Pull failed: {pull_result.stderr}")

                    # Optional: Force push (use with caution)
                    user_input = input("Do you want to force push and overwrite remote changes? (y/N): ").strip().lower()
                    if user_input == 'y':
                        force_push = subprocess.run(
                            ['git', '-C', str(repo_path), 'push', 'origin', 'main', '--force'],
                            capture_output=True, text=True
                        )
                        if force_push.returncode == 0:
                            logging.info("Force pushed changes to remote repository.")
                            print("Force pushed changes to remote repository.")
                        else:
                            logging.error(f"Force push failed: {force_push.stderr}")
                            print(f"Error: Force push failed: {force_push.stderr}")
                    else:
                        logging.warning("Force push aborted by user.")
                        print("Force push aborted by user.")
            else:
                # Other push errors
                logging.error(f"Push failed: {push_result.stderr}")
                print(f"Error: Push failed: {push_result.stderr}")

        # Restore the original remote URL to avoid exposing the PAT
        subprocess.run(
            ['git', '-C', str(repo_path), 'remote', 'set-url', 'origin', original_remote_url],
            capture_output=True, text=True, check=True
        )
        logging.debug("Restored original remote URL.")
        print("Restored original remote URL.")
    except Exception as e:
        print(f"Error: {e}")