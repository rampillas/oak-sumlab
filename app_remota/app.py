import streamlit as st
import requests
import time
import cv2
import numpy as np
from datetime import datetime, timedelta
import yaml
from config_loader import load_config
from streamlit_autorefresh import st_autorefresh

# Load Config
config = load_config()

API_URL = config["api"]["host"]
#STATUS_FILE = config["data"]["status_file"]
MONITORED_LOGS = config["logging"]["monitored_logs"]
SUM_LAB_LOGO = config["data"]["sumlab_logo"]
EU_FOOTER = config["data"]["eu_footer"]
PREVIEW_REFRESH_RATE = 0.5  # Refresh rate for camera preview in seconds

# --- Helper Functions ---

def get_detection_history(show_image):
    """Retrieves detection history from the API."""
    try:
        params = {"show_image": str(show_image).lower()}
        response = requests.get(f"http://localhost:8000/detections", params=params, timeout=5)
        response.raise_for_status()
        data = response.json()
        return data.get("detections", [])
    except requests.exceptions.RequestException as e:
        st.error(f"Error retrieving detection history: {e}")
        return []

def update_config(send_image, preview_refresh_rate):
    """Updates the send_image and preview refresh rate via API."""
    print(f"Updating config: send_image={send_image}, preview_refresh_rate={preview_refresh_rate}")
    try:
        payload = {
            "send_image": bool(send_image),
            "refresh_rate": float(preview_refresh_rate)
        }
        response = requests.post(f"{API_URL}:8000/config", json=payload, timeout=5)
        response.raise_for_status()
        return True
    except requests.exceptions.RequestException as e:
        st.error(f"Error updating config: {e}")
        return False

def get_last_preview_image():
    """Retrieves the last preview image from the API."""
    try:
        response = requests.get(f"{API_URL}:8000/preview_image", timeout=5)
        response.raise_for_status()
        data = response.json()
        image_data = data.get("image_data")
        return image_data
    except requests.exceptions.RequestException as e:
        st.error(f"Error retrieving last preview image: {e}")
        return None

def get_last_upload_time():
    """Retrieves the last upload time from the API."""
    try:
        response = requests.get(f"http://localhost:8000/last-upload-time", timeout=5)
        response.raise_for_status()
        data = response.json()
        return data.get("last_upload_time", "N/A")
    except requests.exceptions.RequestException as e:
        st.error(f"Error getting last upload time: {e}")
        return "N/A"

def get_vehicle_count_last_hour():
    """Gets the number of vehicles detected in the last hour from the API."""
    try:
        response = requests.get(f"http://localhost:8000/vehicle_count_last_hour", timeout=5)
        response.raise_for_status()
        data = response.json()
        return data.get("count", 0)
    except requests.exceptions.RequestException as e:
        st.error(f"Error getting vehicle count: {e}")
        return 0

def read_log_file(log_file_name):
    """Reads a log file content from the API."""
    try:
        params = {"table": log_file_name}
        response = requests.get(f"{API_URL}:8000/logs", params=params, timeout=5)
        response.raise_for_status()
        data = response.text
        return data
    except requests.exceptions.RequestException as e:
        return f"Error reading log file {log_file_name}: {e}"

def get_thread_status(thread_name):
    """Checks if a thread is running based on the API status endpoint."""
    try:
        response = requests.get(f"{API_URL}:8000/status", timeout=5)
        response.raise_for_status()
        status = response.json()
        return status.get(thread_name, 0) == 1
    except requests.exceptions.RequestException:
        return False

def refresh_logs():
    """Function to refresh logs."""
    st.session_state.log_refresh_time = time.time()
    st.session_state.last_log_content = {}
    for log_file, _ in st.session_state.log_files.items():
        st.session_state.last_log_content[log_file] = read_log_file(log_file)

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

if "log_refresh_interval" not in st.session_state:
    st.session_state.log_refresh_interval = 10  # Default value for log & data refresh rate

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

st.sidebar.text("Control de procesos")
#print("Control de procesos")
#if st.sidebar.button("🔁 Reiniciar proceso1"):
#    cerrar_screen(SESSION_NAME)
#    lanzar_screen(SESSION_NAME, COMANDO_RELANZAR)
#    st.sidebar.success(f"Sesión '{SESSION_NAME}' reiniciada con éxito.")

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
    

        # Log & Data refresh rate slider added here
        log_refresh_interval_slider = st.slider("Log & Data refresh rate (s)", 1, 60, st.session_state.log_refresh_interval, 1)
        if log_refresh_interval_slider != st.session_state.log_refresh_interval:
            st.session_state.log_refresh_interval = log_refresh_interval_slider

        
        st.markdown(f"Local DB Size: N/A")  # Removed DB size retrieval, replaced with N/A

    # --- Right Column ---
    with col_right:
        st.subheader("Log Files")

        # Update log content if needed
        for log_file, log_label in st.session_state.log_files.items():
            current_content = read_log_file(log_file)
            if current_content != st.session_state.last_log_content.get(log_file, ""):
                st.session_state.last_log_content[log_file] = current_content

        # Display the text area with log content
        for log_file, log_label in st.session_state.log_files.items():
            st.markdown(f"**{log_label}**")
            st.text_area(f"Log Content ({log_file})", value=st.session_state.last_log_content[log_file], height=200,
                         key=f"log_{log_file}", disabled=True)

    time.sleep(st.session_state.log_refresh_interval)  # refresh time
    st.rerun()
