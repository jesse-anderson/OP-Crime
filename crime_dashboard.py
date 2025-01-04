import streamlit as st
import pandas as pd
import folium
from streamlit_folium import st_folium
from datetime import datetime, timedelta
import numpy as np

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
    df = pd.read_csv("summary_report.zip", compression="zip", encoding="cp1252")
    return df

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

def main_app():
    """
    The main body of the application: date filters, offense filter, map, etc.
    """
    st.set_page_config(page_title="Oak Park Crime", layout="wide")

    # Links at the top for portfolio / blog
    st.markdown(
        """
        [**My Portfolio**](https://jesse-anderson.net/) | [**My Blog**](https://blog.jesse-anderson.net/)
        """,
        unsafe_allow_html=True
    )

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

    with col_map:
        st.write(f"**Displaying {len(final_df)} records on the map**.")

        # Create Folium map
        oak_park_center = [41.885, -87.78]
        crime_map = folium.Map(location=oak_park_center, zoom_start=13)

        for _, row in final_df.iterrows():
            complaint   = safe_field(row.get('Complaint #'))
            offense_val = safe_field(row.get('Offense'))
            date_val    = row.get('Date')
            date_str    = safe_field(date_val.strftime('%Y-%m-%d') if pd.notnull(date_val) else np.nan)
            time_val    = safe_field(row.get('Time'))
            location    = safe_field(row.get('Location'))
            victim      = safe_field(row.get('Victim/Address'))
            narrative   = safe_field(row.get('Narrative'))

            popup_html = f"""
            <b>Complaint #:</b> {complaint}<br/>
            <details>
              <summary>View Details</summary>
              <b>Offense:</b> {offense_val}<br/>
              <b>Date:</b> {date_str}<br/>
              <b>Time:</b> {time_val}<br/>
              <b>Location:</b> {location}<br/>
              <b>Victim:</b> {victim}<br/>
              <b>Narrative:</b> {narrative}<br/>
            </details>
            """

            folium.Marker(
                location=[row['Lat'], row['Long']],
                popup=folium.Popup(popup_html, max_width=400),
                tooltip=f"Complaint # {complaint}",
                icon=folium.Icon(color="blue", icon="info-sign")
            ).add_to(crime_map)

        st_folium(crime_map, width=1000, height=1000, use_container_width=True)

def main():
    # Check if user has agreed to disclaimer
    if "user_agreed" not in st.session_state:
        st.session_state["user_agreed"] = False

    if not st.session_state["user_agreed"]:
        show_disclaimer()
    else:
        main_app()

if __name__ == "__main__":
    main()
