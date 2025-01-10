import streamlit as st
import pandas as pd
import folium
from streamlit_folium import st_folium
from datetime import datetime, timedelta
import numpy as np
import re
import hashlib
import requests
from folium.plugins import MarkerCluster

# Define Mailchimp API details from secrets
MAILCHIMP_API_KEY = st.secrets["mailchimp"]["api_key"]
MAILCHIMP_AUDIENCE_ID = st.secrets["mailchimp"]["audience_id"]
MAILCHIMP_DATA_CENTER = st.secrets["mailchimp"]["data_center"]

# Mailchimp API endpoint
MAILCHIMP_API_URL = f"https://{MAILCHIMP_DATA_CENTER}.api.mailchimp.com/3.0"

def safe_field(value):
    """
    Return the string version of a field or 'Not found' if it's missing/NaN/empty.
    """
    if pd.isnull(value) or value == "":
        return "Not found"
    return str(value)

@st.cache_data
def load_data():
    """
    Reads 'summary_report.zip' once, caching the DataFrame in memory.
    This prevents re-reading the file on every app rerun.
    """
    df = pd.read_csv("data/summary_report.zip", compression="zip", encoding="cp1252")
    return df

# def add_footer(crime_map):
#     """
#     Adds a footer to the provided Folium map.
#     """
#     current_year = datetime.now().year
#     footer_html = f'''
#         <div style="position: fixed; 
#                     bottom: 10px; 
#                     width: 100%; 
#                     text-align: center; 
#                     font-size: 12px; 
#                     color: #555;">
#             &copy; {current_year} Jesse Anderson
#         </div>
#     '''
#     footer_element = folium.Element(footer_html)
#     crime_map.get_root().html.add_child(footer_element)

def show_disclaimer():
    """
    Show a disclaimer 'gate' that the user must agree to in order to proceed.
    """
    st.markdown(
        """
        # Important Legal Disclaimer
        
        **By using this demonstrative research tool, you acknowledge and agree**:
        
        - This tool is for **demonstration purposes only**.
        - The data originated from publicly available Oak Park Police Department PDF files.
          View the official site here: [Oak Park Police Department](https://www.oak-park.us/village-services/police-department).
        - During parsing, **~10%** of complaints were **omitted** due to parsing issues; 
          thus the data is **incomplete**.
        - The **official** and **complete** PDF files remain with the Oak Park Police Department.
        - You **will not hold** the author **liable** for **any** decisions—formal or informal—based on this tool.
        - This tool **should not** be used in **any** official or unofficial **decision-making**.
        
        By continuing, you indicate your acceptance of these terms and disclaim all liability. 
        """
    )
    agree = st.checkbox("I have read the disclaimer and I agree to continue.")
    if agree:
        st.session_state["user_agreed"] = True
        st.rerun()
    else:
        st.stop()

def validate_email(email):
    """
    Validates the email format using regex.
    """
    email_regex = r"(^[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+$)"
    return re.match(email_regex, email) is not None

def subscribe_email(email):
    """
    Subscribes an email to the Mailchimp audience.
    """
    # Mailchimp requires the subscriber hash, which is the MD5 hash of the lowercase version of the email
    email_lower = email.lower().encode()
    subscriber_hash = hashlib.md5(email_lower).hexdigest()

    url = f"{MAILCHIMP_API_URL}/lists/{MAILCHIMP_AUDIENCE_ID}/members/{subscriber_hash}"

    data = {
        "email_address": email,
        "status": "subscribed",  # Explicitly set status to 'subscribed'
        "status_if_new": "subscribed"  # Ensure new members are subscribed
    }

    response = requests.put(
        url,
        auth=("anystring", MAILCHIMP_API_KEY),
        json=data
    )

    return response

def unsubscribe_email(email):
    """
    Unsubscribes an email from the Mailchimp audience.
    """
    # Mailchimp requires the subscriber hash, which is the MD5 hash of the lowercase version of the email
    email_lower = email.lower().encode()
    subscriber_hash = hashlib.md5(email_lower).hexdigest()

    url = f"{MAILCHIMP_API_URL}/lists/{MAILCHIMP_AUDIENCE_ID}/members/{subscriber_hash}"

    data = {
        "status": "unsubscribed"
    }

    response = requests.patch(
        url,
        auth=("anystring", MAILCHIMP_API_KEY),
        json=data
    )

    return response

def add_top_links():
    """
    Adds horizontal navigation links: Portfolio, Blog, and Email Updates.
    """
    # Create three equal columns for the links
    col1, col2, col3,col4,col5,col6 = st.columns(6)
    with col1:
        st.markdown('[**Portfolio**](https://jesse-anderson.net/)',
        unsafe_allow_html=True)
    with col2:
        st.markdown('[**Blog**](https://blog.jesse-anderson.net/)',
        unsafe_allow_html=True)
    with col3:
        st.markdown('[**Documentation**](https://blog.jesse-anderson.net/)',
        unsafe_allow_html=True)
    with col4:
        st.markdown('[**Contact**](mailto:jesse@jesse-anderson.net?subject=Inquiry%20from%20Oak%20Park%20Crime%20Map%20App&body=Hello%20Jesse,%0A%0A)',
        unsafe_allow_html=True)
    with col5:
        # Email Updates link pointing to the email updates section
        #Google forms is better. .-.
        st.markdown('[**📧 Email Updates**](https://forms.gle/GnyaVwo1Vzm8nBH6A)')
    with col6:
        # Cumulative static map with all crimes
        st.markdown('[**Comp. Map**](https://jesse-anderson.net/OP-Crime-Maps/crime_map_cumulative.html)')

# def add_email_subscription():
#     """
#     Displays subscription and unsubscription forms at the bottom of the page.
#     The forms are within a collapsed expander that the user can expand manually.
#     """
#     # Add an anchor to scroll to
#     st.markdown('<a id="email-updates"></a>', unsafe_allow_html=True)
    
#     # **3. Implement Email Updates within a Collapsed Expander**
#     with st.expander("📧 Email Updates", expanded=False):
#         st.markdown("### Subscribe to Email Updates")
#         with st.form("email_subscription_form"):
#             subscribe_email_input = st.text_input("Enter your email address to subscribe:")
#             subscribe_submit = st.form_submit_button("Subscribe")

#             if subscribe_submit:
#                 if validate_email(subscribe_email_input):
#                     response = subscribe_email(subscribe_email_input)
#                     if response.status_code == 200:
#                         # Check if the email was already subscribed
#                         response_data = response.json()
#                         status = response_data.get("status")
#                         if status == "subscribed":
#                             # Check if the 'previous_status' was 'unsubscribed' to provide accurate feedback
#                             previous_status = response_data.get("status_if_new")
#                             if previous_status == "subscribed":
#                                 st.success("Subscription successful! You've been resubscribed to the email list.")
#                             else:
#                                 st.success("Subscription successful! You've been added to the email list.")
#                         else:
#                             st.info("You are already subscribed.")
#                     else:
#                         # Handle errors
#                         error_message = response.json().get('detail', 'An error occurred.')
#                         st.error(f"Subscription failed: {error_message}")
#                 else:
#                     st.error("Please enter a valid email address.")

#         st.markdown("---")  # Separator

#         st.markdown("### Unsubscribe from Email Updates")
#         with st.form("email_unsubscription_form"):
#             unsubscribe_email_input = st.text_input("Enter your email address to unsubscribe:")
#             unsubscribe_submit = st.form_submit_button("Unsubscribe")

#             if unsubscribe_submit:
#                 if validate_email(unsubscribe_email_input):
#                     response = unsubscribe_email(unsubscribe_email_input)
#                     if response.status_code == 200:
#                         response_data = response.json()
#                         status = response_data.get("status")
#                         if status == "unsubscribed":
#                             st.success("You have been unsubscribed successfully.")
#                         else:
#                             st.info("Your email was not found in our list.")
#                     else:
#                         # Handle errors
#                         error_message = response.json().get('detail', 'An error occurred.')
#                         st.error(f"Unsubscription failed: {error_message}")
#                 else:
#                     st.error("Please enter a valid email address.")

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

def main_app():
    """
    The main body of the application: date filters, offense filter, map, etc.
    """

    # # Links at the top for portfolio / blog
    # st.markdown(
    #     """
    #     [**My Portfolio**](https://jesse-anderson.net/) | [**My Blog**](https://blog.jesse-anderson.net/)
    #     """,
    #     unsafe_allow_html=True
    # )

    st.title("Oak Park Crime Map")

    # 1) Load data from the ZIP (cached)
    df = load_data()

    # Convert 'Date' to datetime, remove rows with date=1900 or missing lat/long
    df['Date'] = pd.to_datetime(df['Date'], errors='coerce')
    df = df[(df['Date'].notna()) & (df['Date'] != pd.Timestamp("1900-01-01"))]
    df = df.dropna(subset=['Lat', 'Long'])

    # Determine data's min/max date
    min_date_in_data = df['Date'].min().date()
    max_date_in_data = df['Date'].max().date()

    # We'll still allow up to 3 months, but default to just the last 1 month for faster display
    today = datetime.now().date()
    
    # Default = last 1 month
    # e.g. 31 days; you can do 30 if you prefer
    default_start = max(min_date_in_data, today - timedelta(days=31))
    default_end   = min(today, max_date_in_data)

    # Create columns with ratio [1, 2]: left filter (narrow), right map (wider)
    col_filter, col_map = st.columns([1, 2], gap="small")

    with col_filter:
        st.subheader("Date Range (up to 3 months)")

        # Start & End date pickers
        start_date = st.date_input(
            "Start Date",
            value=default_start,
            min_value=min_date_in_data,
            max_value=max_date_in_data
        )
        end_date = st.date_input(
            "End Date",
            value=default_end,
            min_value=min_date_in_data,
            max_value=max_date_in_data
        )

        # Validate date logic
        if end_date < start_date:
            st.warning("End date cannot be before start date. Please adjust.")
            st.stop()

        date_diff = (end_date - start_date).days
        # Still enforce up to 3 months (~92 days)
        if date_diff > 92:
            st.warning("Time range cannot exceed ~3 months (92 days). Please shorten.")
            st.stop()

        # Filter by date
        start_dt = pd.to_datetime(start_date)
        end_dt   = pd.to_datetime(end_date) + pd.Timedelta(days=1)  # inclusive
        date_mask = (df['Date'] >= start_dt) & (df['Date'] < end_dt)
        partial_df = df[date_mask]

        if partial_df.empty:
            st.info("No records found for the selected date range.")
            st.stop()

        # Dynamically gather offenses from partial_df
        unique_offenses = sorted(partial_df['Offense'].dropna().unique())

        st.subheader("Offense Filter")
        with st.expander("Select Offenses (scrollable)", expanded=False):
            if not unique_offenses:
                st.write("No offenses found for this date range.")
                selected_offenses = []
            else:
                # By default, no offenses => show all
                selected_offenses = st.multiselect(
                    "Offense(s)",
                    options=unique_offenses,
                    default=[],  # empty => show all
                    help="Scroll to find more offenses. If empty => show all."
                )

    # If user picks no offense => show all
    if selected_offenses:
        final_df = partial_df[partial_df['Offense'].isin(selected_offenses)]
    else:
        final_df = partial_df

    if final_df.empty:
        st.info("No records found for the selected offense(s).")
        st.stop()

    # Truncate to 2,000
    total_recs = len(final_df)
    if total_recs > 2000:
        st.info(f"There are {total_recs} matching records. Showing only the first 2,000.")
        final_df = final_df.iloc[:2000]
    
    base_url_static = 'https://www.oak-park.us/sites/default/files/police/summaries/'

    with col_map:
        st.write(f"**Displaying {len(final_df)} records on the map**.")

        # Create Folium map
        oak_park_center = [41.885, -87.78]
        crime_map = folium.Map(location=oak_park_center, zoom_start=13)
        marker_cluster = MarkerCluster(
            control=True,
            showCoverageOnHover=True,
            zoomToBoundsOnClick=True,
        ).add_to(crime_map)

        for _, row in final_df.iterrows():
            complaint   = safe_field(row.get('Complaint #'))
            offense_val = safe_field(row.get('Offense'))
            date_val    = row.get('Date')
            date_str    = safe_field(date_val.strftime('%Y-%m-%d') if pd.notnull(date_val) else np.nan)
            time_val    = safe_field(row.get('Time'))
            location    = safe_field(row.get('Location'))
            victim      = safe_field(row.get('Victim/Address'))
            narrative   = safe_field(row.get('Narrative'))
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
                location=[row['Lat'], row['Long']],
                popup=folium.Popup(popup_html, max_width=300),
                tooltip=f"Complaint # {complaint}",
                icon=folium.Icon(color="red", icon="info-sign")
            ).add_to(marker_cluster)

        footer_html = f"""
    <style>
        .footer {{
            position: fixed;
            left: 0;
            bottom: 0;
            width: 100%;
            background-color: #f1f1f1;
            color: #555;
            text-align: center;
            padding: 0px 0;
            font-size: 10px;
            box-shadow: 0 -2px 5px rgba(0,0,0,0.1);
        }}
        .footer a {{
            color: #555;
            text-decoration: none;
            margin: 0 10px;
        }}
        .footer a:hover {{
            text-decoration: underline;
        }}
    </style>
    <div class="footer">
        Copyright &copy; {datetime.now().year} Jesse Anderson. All rights reserved.
    </div>
"""

        st_folium(crime_map, use_container_width=True)
        # **Insert the Footer Below the Map**
        st.markdown(footer_html, unsafe_allow_html=True)

def main():
    # Set the page layout to wide
    st.set_page_config(page_title="Oak Park Crime", layout="wide")
    # Check if user has agreed to disclaimer
    if "user_agreed" not in st.session_state:
        st.session_state["user_agreed"] = False

    if not st.session_state["user_agreed"]:
        show_disclaimer()
    else:
        

        # Add horizontal navigation links at the top
        add_top_links()

        # Proceed with the main application
        main_app()

        # # Add Email Updates section at the bottom
        # add_email_subscription()
if __name__ == "__main__":
    main()
