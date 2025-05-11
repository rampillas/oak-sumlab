import threading
import sqlite3
import requests
import time
from datetime import datetime, timedelta
import logging
import os
import traceback
import yaml  # Import the yaml library
from config_loader import load_config #Import the function

# Load Config
config = load_config()
# Configuration using config.yaml
LOG_DIR = config["logging"]["log_dir"]
DB_PATH = config["data"]["db_path"]
API_ALERT_URL = config["application"]["api_alert_url"]
API_BATCH_URL = config["application"]["api_batch_url"]
DELETE_IMAGES_INTERVAL = config["threads"]["tasks"]["delete_old_images"]["delete_images_interval"]
SAVE_DATA_INTERVAL = config["threads"]["tasks"]["send_hourly_data"]["save_data_interval"]
KEEP_CONTRARY_IMAGES = config["application"]["keep_contrary_images"]
STATUS_FILE = config["data"]["status_file"]
API_LAST_UPLOAD_URL = config["application"]["api_last_upload_url"] #new

log_file = os.path.join(LOG_DIR, "guardar_horario.log")

# Create a specific logger for guardar_horario
guardar_horario_logger = logging.getLogger("guardar_horario")
guardar_horario_logger.setLevel(logging.INFO)

# Create a file handler for the guardar_horario log file
file_handler = logging.FileHandler(log_file)
file_handler.setFormatter(logging.Formatter('%(asctime)s - %(levelname)s - %(message)s'))

# Add the file handler to the guardar_horario logger
guardar_horario_logger.addHandler(file_handler)

# Create a lock for logging
log_lock = threading.Lock()



def send_alert(vehicle_id, x_pos, y_pos, alert_type="Sentido contrario"):
    """Sends an alert to the API endpoint."""
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    data = {"timestamp": timestamp, "vehicle_id": vehicle_id, "x_position": x_pos, "y_position": y_pos, "alert": alert_type}
    
    try:
        response = requests.post(API_ALERT_URL, json=data, timeout=5)
        if response.status_code == 200:
            with log_lock:
                guardar_horario_logger.info(f"🔔 Alert sent successfully: {data}")
        else:
            with log_lock:
                guardar_horario_logger.warning(f"⚠️ Alert failed to send (status {response.status_code}): {data}")
    except requests.exceptions.RequestException:
        with log_lock:
            guardar_horario_logger.error(f"❌ Alert could not be sent due to network error: {data}")

def update_status(thread_name, status, lock):  # Receive the lock as a parameter
    """Updates the status in the status.yaml file."""
    with lock:  # Acquire the lock before accessing the YAML file
        try:
            with open(STATUS_FILE, "r") as f:
                data = yaml.safe_load(f) or {}
        except FileNotFoundError:
            data = {}
        data[thread_name] = status
        with open(STATUS_FILE, "w") as f:
            yaml.dump(data, f)

def get_last_upload_time():
    """Gets the last upload time from the master database."""
    try:
        with log_lock:
            guardar_horario_logger.info("🔄 Getting last upload time...")
        response = requests.get(API_LAST_UPLOAD_URL, timeout=5) #changed
        if response.status_code == 200:
            last_upload_time_str = response.json().get("last_upload_time")
            if last_upload_time_str:
                try:
                    return datetime.strptime(last_upload_time_str, "%Y-%m-%d %H:%M:%S")
                except ValueError:
                    return datetime.strptime(last_upload_time_str, "%Y-%m-%d %H:%M:%S.%f")
            else:
                with log_lock:
                    guardar_horario_logger.warning("⚠️ No last upload time found.")
                return None
        else:
            with log_lock:
                guardar_horario_logger.warning(f"⚠️ Error getting last upload time, response: {response.status_code}")
            return None
    except requests.exceptions.RequestException:
        with log_lock:
            guardar_horario_logger.error("❌ Could not get the last upload time due to a network error.")
        return None

def send_hourly_data(lock): # Receive the lock as a parameter
    """Sends hourly data to the master database and deletes the sent data."""
    while True:
        try:
            update_status("send_hourly_data", 1, lock) # Pass the lock
            last_upload_time = get_last_upload_time()
            with log_lock:
                guardar_horario_logger.info(f"🔄 Checking for new data... Last upload time: {last_upload_time}")

            now = datetime.now()
            current_hour_start = now.replace(minute=now.minute-int(SAVE_DATA_INTERVAL/60), second=0, microsecond=0)#(minute=0, second=0, microsecond=0)
            previous_hour_start = current_hour_start - timedelta(hours=SAVE_DATA_INTERVAL / 3600)

            if last_upload_time is not None and previous_hour_start > last_upload_time:
                with log_lock:
                    guardar_horario_logger.info(f"⏳ Uploading data from {last_upload_time} to {current_hour_start}")

                conn = sqlite3.connect(DB_PATH)
                cursor = conn.cursor()
                cursor.execute(
                    "SELECT * FROM detections WHERE timestamp >= ? AND timestamp < ?",
                    (last_upload_time.strftime("%Y-%m-%d %H:%M:%S"), current_hour_start.strftime("%Y-%m-%d %H:%M:%S")),
                )
                data = cursor.fetchall()
                conn.close()
                with log_lock:
                    guardar_horario_logger.info(f"🔄 Found {len(data)} new detections to upload")

                if data:
                    json_data = [
                        {
                            "id": row[0],
                            "timestamp": row[1],
                            "vehicle_id": row[2],
                            "x_position": row[3],
                            "y_position": row[4],
                            "direction": row[5]
                        }
                        for row in data
                    ]

                    while True:
                        try:
                            response = requests.post(API_BATCH_URL, json=json_data, timeout=5)
                            if response.status_code == 200:
                                with log_lock:
                                    guardar_horario_logger.info(
                                        f"✅ Data from {last_upload_time} to {current_hour_start} uploaded and deleting"
                                    )

                                conn = sqlite3.connect(DB_PATH)
                                cursor = conn.cursor()
                                cursor.execute(
                                    "DELETE FROM detections WHERE timestamp < ?",
                                    (current_hour_start.strftime("%Y-%m-%d %H:%M:%S"),),
                                )
                                conn.commit()
                                conn.close()
                                break
                            else:
                                with log_lock:
                                    guardar_horario_logger.warning(f"⚠️ API error ({response.status_code}). Retrying in 5 min...")
                                time.sleep(300)
                        except requests.exceptions.RequestException:
                            with log_lock:
                                guardar_horario_logger.error("❌ No connection to API. Retrying in 5 min...")
                            time.sleep(300)
            else:
                with log_lock:
                    guardar_horario_logger.info(f"😴 No new data to upload. Waiting...")

            time.sleep(SAVE_DATA_INTERVAL)  # Wait for the configured interval

        except Exception as e:
            update_status("send_hourly_data", 0, lock) # Pass the lock
            with log_lock:
                guardar_horario_logger.error(f"❌ An unexpected error occurred: {e}")
                traceback.print_exc()
            send_alert(vehicle_id="SYSTEM", x_pos=0, y_pos=0, alert_type=f"send_hourly_data FAILED.")
            time.sleep(60)  # Wait a minute before retrying

def delete_old_images(lock): # Receive the lock as a parameter
    """Deletes images from the database older than DELETE_IMAGES_INTERVAL seconds."""
    try:
        while True:
            update_status("delete_old_images", 1, lock) # Pass the lock
            now = datetime.now()
            with log_lock:
                guardar_horario_logger.info(f"⏳ Cleaning up old images..., current time: {now}")
            conn = sqlite3.connect(DB_PATH)
            cursor = conn.cursor()

            try:
                threshold_time = datetime.now() - timedelta(seconds=DELETE_IMAGES_INTERVAL)
                threshold_time_str = threshold_time.strftime("%Y-%m-%d %H:%M:%S")
                with log_lock:
                    guardar_horario_logger.info(f"🔄 Deleting images older than {threshold_time_str}...")

                if KEEP_CONTRARY_IMAGES:
                    with log_lock:
                        guardar_horario_logger.info("✅ Keep contrary images are enabled")
                    number_of_rows = cursor.execute(
                        "SELECT COUNT(*) FROM detections WHERE image IS NOT NULL and direction != 'ascending' AND timestamp < ?",
                        (threshold_time_str,)).fetchone()[0]
                    with log_lock:
                        guardar_horario_logger.info(f"🔄 Deleting {number_of_rows} contrary images if exists")
                    cursor.execute("UPDATE detections SET image = NULL WHERE direction != 'ascending' AND timestamp < ?",
                                   (threshold_time_str,))
                else:
                    with log_lock:
                        guardar_horario_logger.info("✅ Keep contrary images are disabled")
                    number_of_rows = cursor.execute(
                        "SELECT COUNT(*) FROM detections WHERE image IS NOT NULL and timestamp < ?",
                        (threshold_time_str,)).fetchone()[0]
                    with log_lock:
                        guardar_horario_logger.info(f"🔄 Deleting {number_of_rows} images")
                    cursor.execute("UPDATE detections SET image = NULL WHERE  timestamp < ?", (threshold_time_str,))
                conn.commit()
                with log_lock:
                    guardar_horario_logger.info("✅ Old images deleted successfully")

            except Exception as e:
                with log_lock:
                    guardar_horario_logger.error(f"❌ Error deleting images: {e}")
            finally:
                conn.close()

            time.sleep(DELETE_IMAGES_INTERVAL)
    except Exception as e:
        update_status("delete_old_images", 0, lock) # Pass the lock
        with log_lock:
            guardar_horario_logger.error(f"❌❌❌ An fatal error in delete_old_images occurred: {e}")
            traceback.print_exc()
        send_alert(vehicle_id="SYSTEM", x_pos=0, y_pos=0, alert_type=f"delete_old_images FAILED.")
