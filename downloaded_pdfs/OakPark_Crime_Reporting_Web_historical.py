import os
import re
import requests
from bs4 import BeautifulSoup
from datetime import datetime
import pandas as pd
from PyPDF2 import PdfReader
import unicodedata
from dateutil import parser as date_parser  # Added for robust date parsing
import time
def clean_text(text):
    """
    Clean up extracted text to normalize spacing, encoding, and remove unnecessary line breaks.
    Try multiple encoding fixes if needed.
    """
    for encoding in ["utf-8", "latin1", "ascii", "cp1252"]:
        try:
            text = text.encode(encoding).decode("utf-8")
            break
        except (UnicodeEncodeError, UnicodeDecodeError):
            continue

    text = unicodedata.normalize("NFKD", text)
    text = re.sub(r"\n+", " ", text)  # Replace newlines with spaces
    text = re.sub(r"\s{2,}", " ", text)  # Replace multiple spaces with a single space
    text = text.replace(" \n", " ").replace("\n ", " ")  # Handle spaces around line breaks
    return text.strip()

def parse_date(date_str):
    """
    Parse a date string with multiple potential formats.
    Returns a standardized date string in 'YYYY-MM-DD' format, or '1900-01-01' on failure.
    """
    if not date_str:
        return "1900-01-01"
    
    date_str = date_str.strip()
    
    # Normalize separators by removing extra spaces around them
    date_str = re.sub(r'\s*[-–—]\s*', '-', date_str)
    
    # Check if it's a date range by looking for multiple date patterns
    # Use regex to find all date-like substrings
    date_pattern = r'(\d{1,2}[/-][A-Za-z]{3}[/-]\d{2,4})'
    matches = re.findall(date_pattern, date_str)
    
    if len(matches) > 1:
        # It's a date range
        parsed_dates = []
        for d in matches:
            try:
                # Use dateutil parser for flexibility
                dt = date_parser.parse(d, dayfirst=True)
                parsed_dates.append(dt)
            except (ValueError, OverflowError) as e:
                print(f"Failed to parse date part '{d}': {e}")
                continue
        if parsed_dates:
            latest_date = max(parsed_dates)
            return latest_date.strftime("%Y-%m-%d")
    else:
        # Single date
        try:
            dt = date_parser.parse(date_str, dayfirst=True)
            return dt.strftime("%Y-%m-%d")
        except (ValueError, OverflowError) as e:
            print(f"Failed to parse single date '{date_str}': {e}")
    
    return "1900-01-01"

def extract_data_from_pdf(file_path):
    reader = PdfReader(file_path)
    raw_text = " ".join([page.extract_text() for page in reader.pages if page.extract_text()])
    text = clean_text(raw_text)  # Clean the raw text

    # Refined regex patterns with lookaheads to prevent capturing trailing fields
    complaint_pattern = r"COMPLAINT NUMBER:\s*(\d{2}-\d{5})"
    offense_pattern = r"OFFENSE:\s+([A-Z\s]+)"
    date_pattern = r"DATE\(S\):\s+([A-Za-z0-9\s&\-–—]+?)(?=\s+TIME\(S\)|\s+$)"
    time_pattern = r"TIME\(S\):\s+([\d:HRS\s\-–—]+)"
    location_pattern = r"LOCATION:\s+(.+?)\s+VICTIM/ADDRESS"
    victim_pattern = r"VICTIM/ADDRESS:\s+(.+?)\s+NARRATIVE"
    narrative_pattern = r"NARRATIVE:\s+(.+?)(?=COMPLAINT NUMBER|$)"

    complaints = re.findall(complaint_pattern, text)
    offenses = re.findall(offense_pattern, text)
    dates = re.findall(date_pattern, text)
    times = re.findall(time_pattern, text)
    locations = re.findall(location_pattern, text)
    victims = re.findall(victim_pattern, text)
    narratives = re.findall(narrative_pattern, text)

    offenses = [offense.replace("DATE", "").strip() for offense in offenses]

    log_entries = []
    report = []
    # complaintCount = len(complaints)
    # print(f"Number of complaints: {complaintCount}")
    time.sleep(5)
    for i in range(len(complaints)):
        try:
            raw_date = dates[i] if i < len(dates) else "01-JAN-00"
            date_parts = raw_date.split("&")  # Assuming '&' is used to separate multiple dates
            latest_date = max([parse_date(d) for d in date_parts])
            data_date = latest_date
        except (IndexError, ValueError) as e:
            print(f"Error parsing date for complaint {complaints[i]}: {e}")
            data_date = "1900-01-01"

        entry = {
            "Date": data_date,
            "Complaint #": complaints[i] if i < len(complaints) else "N/A",
            "Offense": offenses[i] if i < len(offenses) else "N/A",
            "Time": times[i].strip() if i < len(times) else "N/A",
            "Location": locations[i].strip() if i < len(locations) else "N/A",
            "Victim/Address": victims[i].strip() if i < len(victims) else "N/A",
            "Narrative": narratives[i].strip() if i < len(narratives) else "N/A",
        }

        if entry["Narrative"] == "N/A" or entry["Date"] == "1900-01-01":
            # Attempt manual recovery using known pattern
            manual_pattern = re.compile(
                r"COMPLAINT NUMBER:\s*(?P<complaint>\d{2}-\d{5})\s+"
                r"OFFENSE:\s+(?P<offense>[A-Z\s]+)\s+"
                r"DATE\(S\):\s+(?P<date>[\dA-Za-z\s&\-–—]+)\s+"
                r"TIME\(S\):\s+(?P<time>[\d:HRS\s\-–—]+)\s+"
                r"LOCATION:\s+(?P<location>.+?)\s+"
                r"VICTIM/ADDRESS:\s+(?P<victim>.+?)\s+"
                r"NARRATIVE:\s+(?P<narrative>.+?)(?=COMPLAINT NUMBER|$)", 
                re.DOTALL
            )
            match = manual_pattern.search(text)

            if match:
                parsed_date = parse_date(match.group("date"))
                entry = {
                    "Date": parsed_date,
                    "Complaint #": match.group("complaint"),
                    "Offense": match.group("offense").strip(),
                    "Time": match.group("time").strip(),
                    "Location": match.group("location").strip(),
                    "Victim/Address": match.group("victim").strip(),
                    "Narrative": match.group("narrative").strip(),
                }
                # Optional: Log successful manual recovery
                # print(f"Manual recovery successful for '{file_path}': {entry}\n")
            else:
                print(f"Manual recovery failed for '{file_path}'\n")
                log_entry = f"Processing failure in file '{file_path}': {entry}"
                print(log_entry)
                log_entries.append(log_entry)

        report.append(entry)

    return report, log_entries

def write_data_to_csv(report, output_file):
    if not report:
        print("No data to write to CSV.")
        return

    df = pd.DataFrame(report)

    def normalize_text(text):
        return unicodedata.normalize("NFKD", str(text)).encode("ascii", "ignore").decode("ascii")
    
    df = df.applymap(normalize_text)

    df.sort_values(by="Date", ascending=False, inplace=True)

    df.to_csv(output_file, index=False, encoding="cp1252")
    print(f"Data written to {output_file} with Windows-1252 encoding for Excel compatibility.")

def fetch_pdf_links(base_url):
    response = requests.get(base_url)
    response.raise_for_status()
    soup = BeautifulSoup(response.content, 'html.parser')
    pdf_links = []
    for link in soup.find_all('a', href=True):
        href = link['href']
        if href.lower().endswith('.pdf'):
            pdf_links.append(href)
    return pdf_links

def download_pdf(url, download_dir, redownload=False):
    local_filename = os.path.join(download_dir, os.path.basename(url))
    if not redownload and os.path.exists(local_filename):
        # print(f"Already downloaded: {local_filename}")
        return local_filename
    else:
        response = requests.get(url)
        response.raise_for_status()
        with open(local_filename, 'wb') as f:
            f.write(response.content)
        print(f"Downloaded: {local_filename}")
    return local_filename

def main():
    base_url = 'https://www.oak-park.us/village-services/police-department/police-activity-summary-reports'
    download_dir = r'C:\Users\Jesse\Downloads\downloaded_pdfs'
    output_csv_path = r'C:\Users\Jesse\Downloads\summary_report.csv'

    reprocess = True
    redownload = False

    os.makedirs(download_dir, exist_ok=True)

    pdf_links = fetch_pdf_links(base_url)
    all_report_data = []
    all_log_entries = []

    for pdf_link in pdf_links:
        pdf_url = pdf_link if pdf_link.startswith('http') else f'https://www.oak-park.us{pdf_link}'
        pdf_path = download_pdf(pdf_url, download_dir, redownload=redownload)
        if reprocess:
            report_data, log_entries = extract_data_from_pdf(pdf_path)
            all_report_data.extend(report_data)
            all_log_entries.extend(log_entries)

    write_data_to_csv(all_report_data, output_csv_path)

    log_file_path = f"logs_{datetime.now().strftime('%Y-%m-%d')}.txt"
    with open(log_file_path, 'w', encoding="utf-8") as log_file:
        log_file.write("\n".join(all_log_entries))
    print(f"Logs written to {log_file_path}")

if __name__ == '__main__':
    main()
