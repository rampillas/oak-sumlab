import streamlit as st
import pandas as pd
import sqlite3
import time
import cv2
import numpy as np
from PIL import Image
import os
import requests
from datetime import datetime, timedelta
import threading
import yaml
from config_loader import load_config

# Load Config
config = load_config()

# Database path (must match in both files)
DB_PATH = config["data"]["db_path"]
LOG_DIR = config["logging"]["log_dir"]
API_URL = config["application"]["api_last_upload_url"]
STATUS_FILE = config["data"]["status_file"]
SUM_LAB_LOGO = config["data"]["sumlab_logo"]
EU_FOOTER = config["data"]["eu_footer"]
MONITORED_LOGS = config["logging"]["monitored_logs"]
PREVIEW_REFRESH_RATE = 0.5  # Refresh rate for camera preview in seconds

# --- Helper Functions ---
def get_detection_history(show_image):
    """Retrieves detection history from the database."""
    conn = sqlite3.connect(DB_PATH)
    if show_image:
        df = pd.read_sql_query("SELECT * FROM detections ORDER BY timestamp DESC LIMIT 50", conn)
    else:
        df = pd.read_sql_query("SELECT timestamp, vehicle_id, x_position, y_position, direction FROM detections ORDER BY timestamp DESC LIMIT 50", conn)
    conn.close()
    return df

def update_config(send_image, preview_refresh_rate):
    """Updates the send_image and preview refresh rate in the database."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("UPDATE config SET send_image = ?, refresh_rate = ? WHERE id = 1", (send_image,preview_refresh_rate))
    conn.commit()
    conn.close()


    
def get_last_preview_image():
    """Retrieves the last preview image from the preview_images table."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("SELECT image FROM preview_images ORDER BY timestamp DESC LIMIT 1")
    result = cursor.fetchone()
    conn.close()
    return result[0] if result and result[0] else None



def get_last_upload_time():
    """Retrieves the last upload time from the master database."""
    try:
        response = requests.get(API_URL, timeout=5)
        response.raise_for_status()  # Raise an exception for bad status codes
        data = response.json()
        return data.get("last_upload_time", "N/A")
    except requests.exceptions.RequestException as e:
        st.error(f"Error getting last upload time: {e}")
        return "N/A"

def get_vehicle_count_last_hour():
    """Gets the number of vehicles detected in the last hour."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    one_hour_ago = datetime.now() - timedelta(hours=1)
    cursor.execute("SELECT COUNT(DISTINCT vehicle_id) FROM detections WHERE timestamp >= ?",
                   (one_hour_ago.strftime("%Y-%m-%d %H:%M:%S"),))
    count = cursor.fetchone()[0]
    conn.close()
    return count

def read_log_file(log_file_name):
    """Reads a log file and returns its content (last 100 lines, reversed)."""
    log_file_path = os.path.join(LOG_DIR, log_file_name)
    if os.path.exists(log_file_path):
        try:
            with open(log_file_path, "r") as f:
                lines = f.readlines()
                last_lines = lines[-100:]  # Get last 100 lines
                last_lines.reverse()  # Reverse the order
                return "".join(last_lines)  # Return as a single string
        except UnicodeDecodeError:
            return "Can not decode this file"
    else:
        return f"Log file not found: {log_file_name}"

def get_thread_status(thread_name):
    """Checks if a thread is running based on the status file."""
    try:
        with open(STATUS_FILE, "r") as f:
            status = yaml.safe_load(f)
            return status.get(thread_name, 0) == 1  # Returns True if status is 1, False otherwise
    except FileNotFoundError:
        return False  # If status file is not found, assume thread is not running

def refresh_logs():
    """Function to refresh logs."""
    st.session_state.log_refresh_time = time.time()
    st.session_state.last_log_content = {}
    for log_file, _ in st.session_state.log_files.items():
        st.session_state.last_log_content[log_file] = read_log_file(log_file)

def get_db_size():
    """Gets the size of the local database in MB."""
    try:
        size_bytes = os.path.getsize(DB_PATH)
        size_mb = size_bytes / (1024 * 1024)
        return f"{size_mb:.2f} MB"
    except FileNotFoundError:
        return "N/A"


# --- Main App ---
st.set_page_config(layout="wide")  # Use the whole window

# --- Initialize Session State ---
if "log_files" not in st.session_state:
    st.session_state.log_files = {
        # Use the MONITORED_LOGS to show the logs we want
    }
    for log in MONITORED_LOGS:
        st.session_state.log_files[log] = log

if 'show_image' not in st.session_state:
    st.session_state.show_image = False

if "last_log_content" not in st.session_state:
    st.session_state.last_log_content = {}
    for log_file, _ in st.session_state.log_files.items():
        st.session_state.last_log_content[log_file] = read_log_file(log_file)
        
if "page" not in st.session_state:
    st.session_state.page = "Monitoring"

if "table_refresh" not in st.session_state:
    st.session_state.table_refresh = False

if "log_refresh_time" not in st.session_state:
    st.session_state.log_refresh_time = time.time()
    
if "preview_refresh_time" not in st.session_state:
    st.session_state.preview_refresh_time = time.time()
    
if "show_preview" not in st.session_state:
    st.session_state.show_preview = False

if "preview_refresh_rate" not in st.session_state:
    st.session_state.preview_refresh_rate = 0.5 # Default value

# --- Sidebar ---
st.sidebar.image(SUM_LAB_LOGO)
st.sidebar.divider()

st.sidebar.title("CIRCUIT")
st.sidebar.subheader("CIRCUlar & resilient transport InfrasTructures")

st.sidebar.divider()
st.sidebar.markdown('###')
st.sidebar.text("Menu")
# Navigation
if st.sidebar.button("🏠 Main View"):
    st.session_state.page = "Main View"

if st.sidebar.button("📊 Monitoring"):
    st.session_state.page = "Monitoring"

st.sidebar.divider()
st.sidebar.markdown('###')

st.sidebar.markdown(
    """
    <p style="text-align: left; color: grey;">
        Developed by: Sum+Lab.
        <br>
        University of Cantabria (UNICAN).
    </p>
    """,
    unsafe_allow_html=True,
)
st.sidebar.image(EU_FOOTER)

# --- Main View ---
if st.session_state.page == "Main View":
    # Initialize Streamlit
    st.title("🚗 CIRCUIT: Car Detection System")
    st.subheader("CIRCUlar & resilient transport InfrasTructures (CIRCUIT)")
    col1, col2 = st.columns([1, 1])  # Adjust column ratio as needed (1:2)

    with col1:
        b1 = st.button("🔄 Activate/Deactivate Table refresh")
        if b1:
            st.session_state.table_refresh = not st.session_state.table_refresh

        # Display table description
        st.markdown(
            """
            #### Detection History
            This table shows the latest vehicle detections. 
            It includes the timestamp, vehicle ID, position, and direction of each detection.
            """
        )
        # Placeholder for the table
        tabla_placeholder = st.empty()

    with col2:
        st.markdown(f"##### Preview refresh rate (actual: {st.session_state.preview_refresh_rate:.2f} s)")
        preview_refresh_rate_slider = st.slider("Preview refresh rate (s)", 0.1, 5.0, st.session_state.preview_refresh_rate, 0.1)
        if preview_refresh_rate_slider != st.session_state.preview_refresh_rate:
            st.session_state.preview_refresh_rate = preview_refresh_rate_slider
            update_config(st.session_state.show_image, st.session_state.preview_refresh_rate)
            
        b2 = st.button("📸 Activate/Deactivate Camera Preview")
        if b2:
            st.session_state.show_image = not st.session_state.show_image
            update_config(st.session_state.show_image, st.session_state.preview_refresh_rate)
            

        # Placeholder for the image
        frame_placeholder = st.empty()

    # Main loop (only for data retrieval and display)
    while True:
        if st.session_state.table_refresh:
            df = get_detection_history(st.session_state.table_refresh)
            # Remove the 'image' column if it exists
            if 'image' in df.columns:
                df = df.drop(columns=['image'])

            tabla_placeholder.dataframe(df)
        if st.session_state.show_image:
            image_data = get_last_preview_image()
            if image_data:
                nparr = np.frombuffer(image_data, np.uint8)
                frame = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
                frame_placeholder.image(frame, channels="BGR", use_container_width=True)
        
        elif not st.session_state.show_image:
            frame_placeholder.empty()
        time.sleep(st.session_state.preview_refresh_rate)  # Adjust refresh rate as needed (e.g., every 0.5 seconds)

# --- Monitoring Page ---
elif st.session_state.page == "Monitoring":
    st.title("📊 System Monitoring")

    # --- Layout ---
    col_left, col_right = st.columns([1, 2])  # Left column is 1/3, Right column is 2/3

    # --- Left Column ---
    with col_left:
        st.subheader("System Status")

        # Process Status
        st.markdown("#### Processes")
        if get_thread_status("camera_service"):
            st.markdown(f"<span style='color:green'>🟢 camera_service: Running</span>", unsafe_allow_html=True)
        else:
            st.markdown(f"<span style='color:red'>🔴 camera_service: Stopped</span>", unsafe_allow_html=True)

        if get_thread_status("send_hourly_data"):
            st.markdown(f"<span style='color:green'>🟢 send_hourly_data: Running</span>", unsafe_allow_html=True)
        else:
            st.markdown(f"<span style='color:red'>🔴 send_hourly_data: Stopped</span>", unsafe_allow_html=True)
        
        if get_thread_status("delete_old_images"):
            st.markdown(f"<span style='color:green'>🟢 delete_old_images: Running</span>", unsafe_allow_html=True)
        else:
            st.markdown(f"<span style='color:red'>🔴 delete_old_images: Stopped</span>", unsafe_allow_html=True)
        if get_thread_status("fastapi_server"):
            st.markdown(f"<span style='color:green'>🟢 fastapi_server: Running</span>", unsafe_allow_html=True)
        else:
            st.markdown(f"<span style='color:red'>🔴 fastapi_server: Stopped</span>", unsafe_allow_html=True)        
        
        st.markdown("---")
        
        # Real-time Data
        st.markdown("#### Real-time Data")
        last_upload_time = get_last_upload_time()
        st.markdown(f"Last Upload Time: {last_upload_time}")

        vehicle_count = get_vehicle_count_last_hour()
        st.markdown(f"Vehicles in Last Hour: {vehicle_count}")
        
        db_size = get_db_size()  # Call the function to get the database size
        st.markdown(f"Local DB Size: {db_size}")  # Display the database size

    # --- Right Column ---
    with col_right:
        st.subheader("Log Files")

        # Update log content if needed
        for log_file, log_label in st.session_state.log_files.items():
            current_content = read_log_file(log_file)
            if current_content != st.session_state.last_log_content[log_file]:
                st.session_state.last_log_content[log_file] = current_content

        # Display the text area with log content
        for log_file, log_label in st.session_state.log_files.items():
            st.markdown(f"**{log_label}**")
            st.text_area(f"Log Content ({log_file})", value=st.session_state.last_log_content[log_file], height=200,
                         key=f"log_{log_file}", disabled=True)

    time.sleep(5)  # refresh time
    st.rerun()
