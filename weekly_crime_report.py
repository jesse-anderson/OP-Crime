# weekly_crime_report.py

import os
import pandas as pd
import folium
import logging
import zipfile
import time
from pathlib import Path
from datetime import datetime, timedelta
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.application import MIMEApplication
import base64
import sys

import numpy as np
import re
import hashlib
import requests

from google.auth.transport.requests import Request
from google_auth_oauthlib.flow import InstalledAppFlow
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

# Local utility to load env vars
from utils import load_env_vars,extract_year,upload_file_to_github,upload_files_to_github_batch

# Folium plugins
from folium.plugins import MarkerCluster

# Define Gmail API scope
SCOPES = ['https://www.googleapis.com/auth/gmail.send']


#############################################
# 1) HELPER FUNCTIONS
#############################################

# def load_recipients_list(csv_recipients_path):
#     """
#     Loads recipient email addresses from a CSV file with a column named 'Email'.
#     """
#     if not csv_recipients_path.exists():
#         raise FileNotFoundError(f"Recipients CSV not found at: {csv_recipients_path}")

#     df = pd.read_csv(csv_recipients_path, encoding="utf-8")
#     # Clean up duplicates or empty entries if needed
#     df['Email'] = df['Email'].astype(str).str.strip()
#     df.dropna(subset=['Email'], inplace=True)
#     df.drop_duplicates(subset=['Email'], inplace=True)

#     return df['Email'].tolist()

def get_mailchimp_subscribers():
    """
    Fetches all subscribed members from the Mailchimp audience.
    Handles pagination to retrieve all subscribers.
    """
    MAILCHIMP_API_KEY = os.getenv("MAILCHIMP_API_KEY")
    MAILCHIMP_AUDIENCE_ID = os.getenv("MAILCHIMP_AUDIENCE_ID")
    MAILCHIMP_DATA_CENTER = os.getenv("MAILCHIMP_DATA_CENTER")  # e.g., 'us1', 'us2'

    if not all([MAILCHIMP_API_KEY, MAILCHIMP_AUDIENCE_ID, MAILCHIMP_DATA_CENTER]):
        raise ValueError("Missing Mailchimp API configuration in environment variables.")

    MAILCHIMP_API_URL = f"https://{MAILCHIMP_DATA_CENTER}.api.mailchimp.com/3.0"
    endpoint = f"/lists/{MAILCHIMP_AUDIENCE_ID}/members"
    params = {
        "status": "subscribed",
        "count": 1000,  # Max allowed by Mailchimp
        "offset": 0
    }
    subscribers = []

    while True:
        response = requests.get(
            MAILCHIMP_API_URL + endpoint,
            auth=("anystring", MAILCHIMP_API_KEY),
            params=params
        )

        if response.status_code != 200:
            logging.error(f"Failed to fetch subscribers: {response.status_code} - {response.text}")
            raise Exception(f"Mailchimp API Error: {response.status_code} - {response.text}")

        data = response.json()
        members = data.get('members', [])
        subscribers.extend([member['email_address'] for member in members])

        total_items = data.get('total_items', 0)
        if len(subscribers) >= total_items:
            break
        params['offset'] += params['count']
        time.sleep(1)  # To respect API rate limits

    logging.info(f"Fetched {len(subscribers)} subscribers from Mailchimp.")
    return subscribers

def determine_date_range(df, execution_date):
    """
    Determines the date range for the report based on the execution_date (7 days).
    """
    df['Date'] = pd.to_datetime(df['Date'], errors='coerce')
    df_valid = df[df['Date'].notna()].copy()
    if df_valid.empty:
        raise ValueError("No valid dates found in the data.")

    latest_date = df_valid[df_valid['Date'].dt.date <= execution_date]['Date'].max().date()
    if pd.isna(latest_date):
        raise ValueError("No records found on or before today's date.")

    # last 7 days
    end_date = latest_date
    start_date = end_date - timedelta(days=6)

    return start_date, end_date


def filter_crime_data(df, start_date, end_date):
    """
    Filters the DataFrame to entries between start_date and end_date, inclusive.
    """
    start_dt = pd.to_datetime(start_date)
    end_dt   = pd.to_datetime(end_date) + timedelta(days=1) - timedelta(seconds=1)
    mask = (df['Date'] >= start_dt) & (df['Date'] <= end_dt)
    return df.loc[mask].copy()


def load_all_crimes(zip_file_path):
    """
    Reads summary_report.zip containing your full crime data (summary_report.csv).
    """
    if not zip_file_path.exists():
        raise FileNotFoundError(f"Could not find zip file '{zip_file_path}'")

    with zipfile.ZipFile(zip_file_path, 'r') as z:
        with z.open('summary_report.csv') as csvfile:
            df = pd.read_csv(csvfile, encoding='cp1252', on_bad_lines='skip')

    df['Date'] = pd.to_datetime(df['Date'], errors='coerce')
    df = df[df['Date'].notna()]
    df.sort_values(by='Date', ascending=False, inplace=True)
    return df


def safe_field(value):
    """
    Return the string version of a field or 'Not found' if it's missing/NaN/empty.
    """
    if pd.isnull(value) or value == "":
        return "Not found"
    return str(value)



def create_folium_map_filtered_data(
    df,
    lat_col='Lat',
    lng_col='Long',
    offense_col='Offense',
    date_col='Date',
    output_html_path='weekly_map.html'
):
    """
    Creates a Folium map plotting each record in df with disclaimers overlay (JS + HTML) 
    and saves it to 'output_html_path'.
    """
    oak_park_center = [41.885, -87.78]
    crime_map = folium.Map(location=oak_park_center, zoom_start=13)

    marker_cluster = MarkerCluster().add_to(crime_map)
    # Define the static part of the base URL
    base_url_static = 'https://www.oak-park.us/sites/default/files/police/summaries/'

    for _, row in df.iterrows():
        lat = row[lat_col]
        lng = row[lng_col]
        offense = row.get(offense_col, "Unknown")
        complaint = safe_field(row.get('Complaint #'))
        offense_val = safe_field(offense)
        date_str = safe_field(row['Date'].strftime('%Y-%m-%d') if pd.notnull(row['Date']) else np.nan)
        time_val = safe_field(row.get('Time'))
        location = safe_field(row.get('Location'))
        victim = safe_field(row.get('Victim/Address'))
        narrative = safe_field(row.get('Narrative'))
        filename = safe_field(row.get('File Name'))

        popup_html = f"""
            <b>Complaint #:</b> {complaint}<br/>
            <b>Offense:</b> {offense_val}<br/>
            <b>Date:</b> {date_str}<br/>
            <details>
              <summary><b>View Details</b></summary>
              <b>Time:</b> {time_val}<br/>
              <b>Location:</b> {location}<br/>
              <b>Victim:</b> {victim}<br/>
              <b>Narrative:</b> {narrative}<br/>
              <b>URL:</b> <a href="{filename}" target="_blank">PDF Link</a>
            </details>
        """

        folium.Marker(
            location=[lat, lng],
            popup=folium.Popup(popup_html, max_width=300),
            icon=folium.Icon(color='red', icon='info-sign')
        ).add_to(marker_cluster)

    # Basic map title
    title_html = '''
    <h3 align="center" style="font-size:20px"><b>Oak Park Crime Map</b></h3>
    <br>
    <h3 align="center" style="font-size:10px">
    <a href="https://jesse-anderson.net/">My Portfolio</a> |
    <a href="https://blog.jesse-anderson.net/">My Blog</a> |
    <a href="https://blog.jesse-anderson.net/">Documentation</a> |
    <a href="mailto:jesse@jesse-anderson.net">Contact</a> |
    <a href="https://forms.gle/GnyaVwo1Vzm8nBH6A">
        Add me to Weekly Updates
    </a>
    </h3>
'''
    crime_map.get_root().html.add_child(folium.Element(title_html))

    # 1) Overlays disclaimers in a "splash screen" with JavaScript:
    disclaimers_overlay = """
    <style>
    /* Full-page overlay styling */
    #disclaimerOverlay {
      position: fixed;
      z-index: 9999; /* On top of everything */
      left: 0;
      top: 0;
      width: 100%;
      height: 100%;
      background-color: rgba(255, 255, 255, 0.95);
      color: #333;
      display: block; /* Visible by default */
      overflow: auto;
      text-align: center;
      padding-top: 100px;
      font-family: Arial, sans-serif;
    }
    #disclaimerContent {
      background: #f9f9f9;
      border: 1px solid #ccc;
      display: inline-block;
      padding: 20px;
      max-width: 800px;
      text-align: left;
    }
    #acceptButton {
      margin-top: 20px;
      padding: 10px 20px;
      font-size: 16px;
      cursor: pointer;
    }
    </style>

    <div id="disclaimerOverlay">
      <div id="disclaimerContent">
        <h2>Important Legal Disclaimer</h2>
        <p><strong>By using this demonstrative research tool, you acknowledge and agree:</strong></p>
        <ul>
            <li>This tool is for <strong>demonstration purposes only</strong>.</li>
            <li>The data originated from publicly available Oak Park Police Department PDF files.
                View the official site here: 
                <a href="https://www.oak-park.us/village-services/police-department"
                   target="_blank">Oak Park Police Department</a>.</li>
            <li>During parsing, <strong>~10%</strong> of complaints were <strong>omitted</strong> 
                due to parsing issues; thus the data is <strong>incomplete</strong>.</li>
            <li>The <strong>official</strong> and <strong>complete</strong> PDF files remain 
                with the Oak Park Police Department.</li>
            <li>You <strong>will not hold</strong> the author <strong>liable</strong> for <strong>any</strong> 
                decisions—formal or informal—based on this tool.</li>
            <li>This tool <strong>should not</strong> be used in <strong>any</strong> official or unofficial 
                <strong>decision-making</strong>.</li>
        </ul>
        <p><strong>By continuing, you indicate your acceptance of these terms 
           and disclaim all liability.</strong></p>
        <hr/>
        <button id="acceptButton" onclick="hideOverlay()">I Accept</button>
      </div>
    </div>

    <script>
    function hideOverlay() {
      var overlay = document.getElementById('disclaimerOverlay');
      overlay.style.display = 'none'; 
    }
    </script>
    """

    disclaimers_element = folium.Element(disclaimers_overlay)
    crime_map.get_root().html.add_child(disclaimers_element)

    # 2) Save final HTML
    crime_map.save(str(output_html_path))

def create_folium_map_cumulative(
    df,
    lat_col='Lat',
    lng_col='Long',
    offense_col='Offense',
    date_col='Date',
    output_html_path='cumulative_map.html'
):
    """
    Creates a Folium map plotting all records in df up to a certain date with disclaimers overlay (JS + HTML) 
    and saves it to 'output_html_path'.
    """
    oak_park_center = [41.885, -87.78]
    crime_map = folium.Map(location=oak_park_center, zoom_start=11)  # Zoomed out for cumulative view

    marker_cluster = MarkerCluster().add_to(crime_map)
    # Define the static part of the base URL
    base_url_static = 'https://www.oak-park.us/sites/default/files/police/summaries/'

    for _, row in df.iterrows():
        lat = row[lat_col]
        lng = row[lng_col]
        offense = row.get(offense_col, "Unknown")
        complaint = safe_field(row.get('Complaint #'))
        offense_val = safe_field(offense)
        date_str = safe_field(row['Date'].strftime('%Y-%m-%d') if pd.notnull(row['Date']) else np.nan)
        time_val = safe_field(row.get('Time'))
        location = safe_field(row.get('Location'))
        victim = safe_field(row.get('Victim/Address'))
        narrative = safe_field(row.get('Narrative'))
        filename = safe_field(row.get('File Name'))

        popup_html = f"""
            <b>Complaint #:</b> {complaint}<br/>
            <b>Offense:</b> {offense_val}<br/>
            <b>Date:</b> {date_str}<br/>
            <details>
              <summary><b>View Details</b></summary>
              <b>Time:</b> {time_val}<br/>
              <b>Location:</b> {location}<br/>
              <b>Victim:</b> {victim}<br/>
              <b>Narrative:</b> {narrative}<br/>
              <b>URL:</b> <a href="{filename}" target="_blank">PDF Link</a>
            </details>
        """

        folium.Marker(
            location=[lat, lng],
            popup=folium.Popup(popup_html, max_width=300),
            icon=folium.Icon(color='blue', icon='info-sign')  # Different color for distinction
        ).add_to(marker_cluster)

    # Basic map title
    title_html = '''
    <h3 align="center" style="font-size:20px"><b>Oak Park Cumulative Crime Map</b></h3>
    <br>
    <h3 align="center" style="font-size:10px">
    <a href="https://jesse-anderson.net/">My Portfolio</a> |
    <a href="https://blog.jesse-anderson.net/">My Blog</a> |
    <a href="https://blog.jesse-anderson.net/">Documentation</a> |
    <a href="mailto:jesse@jesse-anderson.net">Contact</a> |
    <a href="https://forms.gle/GnyaVwo1Vzm8nBH6A">
        Add me to Weekly Updates
    </a>
    </h3>
'''
    crime_map.get_root().html.add_child(folium.Element(title_html))

    # Overlays disclaimers in a "splash screen" with JavaScript (reuse existing disclaimer)
    disclaimers_overlay = """
    <style>
    /* Full-page overlay styling */
    #disclaimerOverlay {
      position: fixed;
      z-index: 9999; /* On top of everything */
      left: 0;
      top: 0;
      width: 100%;
      height: 100%;
      background-color: rgba(255, 255, 255, 0.95);
      color: #333;
      display: block; /* Visible by default */
      overflow: auto;
      text-align: center;
      padding-top: 100px;
      font-family: Arial, sans-serif;
    }
    #disclaimerContent {
      background: #f9f9f9;
      border: 1px solid #ccc;
      display: inline-block;
      padding: 20px;
      max-width: 800px;
      text-align: left;
    }
    #acceptButton {
      margin-top: 20px;
      padding: 10px 20px;
      font-size: 16px;
      cursor: pointer;
    }
    </style>

    <div id="disclaimerOverlay">
      <div id="disclaimerContent">
        <h2>Important Legal Disclaimer</h2>
        <p><strong>By using this demonstrative research tool, you acknowledge and agree:</strong></p>
        <ul>
            <li>This tool is for <strong>demonstration purposes only</strong>.</li>
            <li>The data originated from publicly available Oak Park Police Department PDF files.
                View the official site here: 
                <a href="https://www.oak-park.us/village-services/police-department"
                   target="_blank">Oak Park Police Department</a>.</li>
            <li>During parsing, <strong>~10%</strong> of complaints were <strong>omitted</strong> 
                due to parsing issues; thus the data is <strong>incomplete</strong>.</li>
            <li>The <strong>official</strong> and <strong>complete</strong> PDF files remain 
                with the Oak Park Police Department.</li>
            <li>You <strong>will not hold</strong> the author <strong>liable</strong> for <strong>any</strong> 
                decisions—formal or informal—based on this tool.</li>
            <li>This tool <strong>should not</strong> be used in <strong>any</strong> official or unofficial 
                <strong>decision-making</strong>.</li>
        </ul>
        <p><strong>By continuing, you indicate your acceptance of these terms 
           and disclaim all liability.</strong></p>
        <hr/>
        <button id="acceptButton" onclick="hideOverlay()">I Accept</button>
      </div>
    </div>

    <script>
    function hideOverlay() {
      var overlay = document.getElementById('disclaimerOverlay');
      overlay.style.display = 'none'; 
    }
    </script>
    """

    disclaimers_element = folium.Element(disclaimers_overlay)
    crime_map.get_root().html.add_child(disclaimers_element)

    # Save final HTML
    crime_map.save(str(output_html_path))


def get_gmail_service():
    """
    Authenticates the user and returns the Gmail API service.
    """
    creds = None
    token_path = Path('token.json')

    if token_path.exists():
        creds = Credentials.from_authorized_user_file(str(token_path), SCOPES)

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            try:
                creds.refresh(Request())
                logging.info("Credentials refreshed successfully.")
            except Exception as e:
                logging.error(f"Error refreshing credentials: {e}")
                print(f"[ERROR] Could not refresh credentials: {e}")
                return None
        else:
            try:
                flow = InstalledAppFlow.from_client_secrets_file(
                    'credentials.json', SCOPES
                )
                creds = flow.run_local_server(port=0)
                logging.info("Authentication flow completed successfully.")
            except Exception as e:
                logging.error(f"Error during OAuth flow: {e}")
                print(f"[ERROR] Could not complete OAuth flow: {e}")
                return None

        try:
            with open(token_path, 'w') as token:
                token.write(creds.to_json())
                logging.info("Credentials saved to token.json.")
        except Exception as e:
            logging.error(f"Failed to save credentials: {e}")
            print(f"[ERROR] Could not save credentials: {e}")

    try:
        service = build('gmail', 'v1', credentials=creds)
        logging.info("Gmail service created successfully.")
        return service
    except HttpError as error:
        logging.error(f"An error occurred while building Gmail service: {error}")
        print(f"[ERROR] An error occurred while building Gmail service: {error}")
        return None


def send_email_with_disclaimer_and_links(
    service,
    sender_email,
    to_emails,
    subject,
    body_text,
    attachments
):
    """
    Sends an email with disclaimers and links using the Gmail API.
    """
    try:
        message = MIMEMultipart()
        message['to'] = "Undisclosed Recipients <jesse@jesse-anderson.net>"
        message['subject'] = subject
        message['from'] = sender_email

        # disclaimer = """
        # <p><strong>Important Legal Disclaimer</strong></p>
        # <p><strong>By using this demonstrative research tool, you acknowledge and agree:</strong></p>
        # <ul>
        #     <li>This tool is for <strong>demonstration purposes only</strong>.</li>
        #     <li>The data originated from publicly available Oak Park Police Department PDF files.
        #         <a href="https://www.oak-park.us/village-services/police-department">Official site</a>.</li>
        #     <li>During parsing, <strong>~10%</strong> of complaints were <strong>omitted</strong>.</li>
        #     <li>The <strong>official</strong> and <strong>complete</strong> PDF files remain with the Oak Park Police Department.</li>
        #     <li>You <strong>will not hold</strong> the author <strong>liable</strong> for any decisions
        #         based on this tool.</li>
        #     <li>This tool <strong>should not</strong> be used in any official or unofficial <strong>decision-making</strong>.</li>
        # </ul>
        # <p><strong>By continuing, you disclaim all liability.</strong></p>
        # <hr>
        # """

        links = """
        <p>
            <a href="https://jesse-anderson.net/">My Portfolio</a> | 
            <a href="https://blog.jesse-anderson.net/">My Blog</a>
        </p>
        <hr>
        """

        # html = f"""
        # <html>
        #   <body>
        #     {links}
        #     {disclaimer}
        #     <p>Hello,</p>
        #     <p>Attached is the crime report covering the period from {body_text['start_date']} to {body_text['end_date']}, including:</p>
        #     <ul>
        #         <li>A CSV of all crimes that occurred in this period.</li>
        #     </ul>
        #     <p>For an interactive view of the crime locations, visit:</p>
        #     <p><a href="https://jesse-anderson.net/OP-Crime-Maps/{body_text['map_filename']}">
        #         Crime Map</a></p>
        #     <p>Best,<br>Crime Report Bot</p>
        #   </body>
        # </html>
        # """

        # Define the plain text content
        plain_text = f"""
        Important Legal Disclaimer
        
        By using this demonstrative research tool, you acknowledge and agree:

        - This tool is for demonstration purposes only.
        - The data originated from publicly available Oak Park Police Department PDF files.
          View the official site here: https://www.oak-park.us/village-services/police-department.
        - During parsing, ~10% of total complaints since 2018 were omitted due to parsing issues; 
          thus the data is incomplete.
        - The official and complete PDF files remain with the Oak Park Police Department.
        - You will not hold the author liable for any decisions—formal or informal—based on this tool.
        - This tool should not be used in any official or unofficial decision-making.

        By continuing, you indicate your acceptance of these terms and disclaim all liability.

        ------------

        Hello,
        The crime report from {body_text['start_date']} to {body_text['end_date']} is attached as a .csv file.

        Interactive map:
        {body_text['weekly_map_url']}

        Cumulative map:
        {body_text['cumulative_map_url']}
        
        Last week's data:
        {body_text['csv_url']}
        """

        part1 = MIMEText(plain_text, 'plain')
        # part2 = MIMEText(html, 'html')
        message.attach(part1)
        # message.attach(part2)

        bcc_emails = ", ".join(to_emails)
        message['bcc'] = bcc_emails

        # Attach the CSV
        for file_path in attachments:
            file_path = Path(file_path)
            if not file_path.exists():
                logging.warning(f"Attachment '{file_path}' not found, skipping.")
                continue
            with open(file_path, 'rb') as f:
                mime_application = MIMEApplication(f.read(), Name=file_path.name)
            mime_application['Content-Disposition'] = f'attachment; filename="{file_path.name}"'
            message.attach(mime_application)

        raw_message = base64.urlsafe_b64encode(message.as_bytes()).decode()
        body = {'raw': raw_message}

        sent_message = service.users().messages().send(userId="me", body=body).execute()
        logging.info(f"Email sent successfully. Message ID: {sent_message['id']}")
        print("Crime report email sent successfully.")
    except Exception as e:
        logging.error(f"Failed to send email: {e}")
        print(f"[ERROR] Failed to send email: {e}")


#############################################
# 2) MAIN WORKFLOW / REPORT GENERATION
#############################################

def main_report_generation():
    """
    Executes the full pipeline:
    1. Load environment variables
    2. Load & filter data for the last 7 days
    3. Create & save Folium map with disclaimers overlay
    4. Upload HTML to GitHub
    5. Send email with CSV attached
    """
    start_time = time.time()
    script_dir = Path(__file__).parent.resolve()

    env_file_path = script_dir / "env_vars.txt"
    try:
        load_env_vars(env_file_path)
    except FileNotFoundError as e:
        print(f"[ERROR] {e}")
        return

    sender_email = os.getenv("SENDER_EMAIL")
    if not sender_email:
        raise ValueError("Missing SENDER_EMAIL in env_vars.txt")

    logging.basicConfig(
        filename=script_dir / 'full_crime_report.log',
        level=logging.DEBUG,
        format='%(asctime)s - %(levelname)s - %(message)s'
    )

    data_dir = script_dir / 'data'
    map_dir = script_dir / 'generated_maps'
    # recipients_csv = script_dir / 'recipients.csv'
    csv_dir = script_dir / 'generated_csvs'  # New directory for CSVs
    map_dir.mkdir(parents=True, exist_ok=True)
    csv_dir.mkdir(parents=True, exist_ok=True)

    zip_file_path = data_dir / 'summary_report.zip'

    execution_date = datetime.now().date()
    date_str = execution_date.strftime('%Y-%m-%d')

    # CSV & HTML output
    filtered_subset_filename = f'filtered_subset_{date_str}.csv'
    filtered_subset_path = csv_dir / filtered_subset_filename
    weekly_map_output_filename = f'crime_map_weekly_{date_str}.html'
    weekly_map_output_path = map_dir / weekly_map_output_filename
    cumulative_map_output_filename = f'crime_map_cumulative_{date_str}.html'
    cumulative_map_output_path = map_dir / cumulative_map_output_filename

    # Local GitHub Pages folder
    github_repo_path = os.getenv("GITHUB_REPO")
    github_repo_path = Path(github_repo_path)

    # (C) Load data
    try:
        df_full = load_all_crimes(zip_file_path)
    except Exception as e:
        logging.error(f"Failed to load all crimes: {e}")
        print(f"[ERROR] Could not load all crimes: {e}")
        return

    if df_full.empty:
        logging.info("No crime data—no map or CSV generated.")
        print("No crime data—no map or CSV generated.")
        return

    # (D) Filter last 7 days
    try:
        start_date, end_date = determine_date_range(df_full, execution_date)
        df_filtered = filter_crime_data(df_full, start_date, end_date)
    except Exception as e:
        logging.error(f"Error determining date range: {e}")
        print(f"[ERROR] Could not determine date range: {e}")
        return

    if df_filtered.empty:
        logging.info("No crimes found—no map or CSV generated.")
        print("No crimes found in the determined date range—no map or CSV generated.")
        return

    # (E) Write filtered CSV
    try:
        df_filtered.to_csv(filtered_subset_path, index=False, encoding="cp1252")
        logging.info(f"Filtered data written to {filtered_subset_path}")
    except Exception as e:
        logging.error(f"Failed to write filtered data to CSV: {e}")
        print(f"[ERROR] Could not write filtered data to CSV: {e}")
        return

    # (F) Create Folium map with disclaimers overlay
    try:
        create_folium_map_filtered_data(
            df=df_filtered,
            lat_col='Lat',
            lng_col='Long',
            offense_col='Offense',
            date_col='Date',
            output_html_path=weekly_map_output_path
        )
        logging.info(f"Folium map created at {weekly_map_output_path}")
    except Exception as e:
        logging.error(f"Error creating Folium map: {e}")
        print(f"[ERROR] Could not create Folium map: {e}")
        return

    try:
        create_folium_map_cumulative(
            df=df_full,  # Use the full dataset for cumulative map
            lat_col='Lat',
            lng_col='Long',
            offense_col='Offense',
            date_col='Date',
            output_html_path=cumulative_map_output_path
        )
        logging.info(f"Cumulative Folium map created at {cumulative_map_output_path}")
    except Exception as e:
        logging.error(f"Error creating cumulative Folium map: {e}")
        print(f"[ERROR] Could not create cumulative Folium map: {e}")
        return
    
    test = False
    if not test:
        # (G) Upload Map and csv
        try:
            # Upload Maps
            files_to_upload_maps = [weekly_map_output_path, cumulative_map_output_path]
            upload_files_to_github_batch(
                file_paths=files_to_upload_maps,
                github_repo_path=github_repo_path,
                target_subfolder='OP-Crime-Maps'
            )
            time.sleep(5) #paranoia
            # Upload CSV
            files_to_upload_csv = filtered_subset_path
            upload_file_to_github(
                file_path=files_to_upload_csv,
                github_repo_path=github_repo_path,
                target_subfolder='OP-Crime-Data'
            )
        except Exception as e:
            logging.error(f"Failed to upload files to GitHub: {e}")
            print(f"[ERROR] Could not upload files to GitHub: {e}")
            return
        # (I) Generate GitHub URLs for the uploaded files
        # Assuming GitHub Pages are served from the root of the repository
        github_base_url = "https://jesse-anderson.github.io"

        weekly_map_url = f"{github_base_url}/OP-Crime-Maps/{weekly_map_output_filename}"
        cumulative_map_url = f"{github_base_url}/OP-Crime-Maps/{cumulative_map_output_filename}"
        csv_url = f"{github_base_url}/OP-Crime-Data/{filtered_subset_filename}"

        # (J) Gmail API & Email
        try:
            service = get_gmail_service()
            if not service:
                raise Exception("Failed to create Gmail service.")
        except Exception as e:
            logging.error(f"Authentication failed: {e}")
            print(f"[ERROR] Authentication failed: {e}")
            return
        time.sleep(60) #time to build github pages....
        # (K) Load Recipients
        try:
            # to_list = load_recipients_list(recipients_csv)
            # to_list = get_mailchimp_subscribers()
            to_list = ["jander98@illinois.edu"]
        except FileNotFoundError as e:
            logging.error(f"Error loading recipients: {e}")
            print(f"[ERROR] {e}")
            return

        if not to_list:
            logging.warning("No recipients found—cannot send email.")
            print("No recipients found in recipients.csv—cannot send email.")
            return

        subject = f"Crime Report from {start_date.strftime('%Y-%m-%d')} to {end_date.strftime('%Y-%m-%d')}"
        body_text = {
            'start_date': start_date.strftime('%Y-%m-%d'),
            'end_date': end_date.strftime('%Y-%m-%d'),
            'weekly_map_url': weekly_map_url,
            'cumulative_map_url': cumulative_map_url,
            'csv_url': csv_url
        }
        attachments = []

        try:
            send_email_with_disclaimer_and_links(
                service=service,
                sender_email=sender_email,
                to_emails=to_list,
                subject=subject,
                body_text=body_text,
                attachments=attachments
            )
        except Exception as e:
            logging.error(f"Failed to send email: {e}")
            print(f"[ERROR] Could not send email: {e}")

    end_time = time.time()
    elapsed_sec = end_time - start_time
    logging.info(f"Finished full_crime_report in {elapsed_sec:.2f} seconds.")
    print(f"Finished full_crime_report in {elapsed_sec:.2f} seconds.")


#############################################
# 3) MAIN ENTRY POINT
#############################################

def main():
    """
    Simply runs the report generation from the command line; no Streamlit involved.
    """
    main_report_generation()


if __name__ == "__main__":
    main()
