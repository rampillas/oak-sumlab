import threading
import yaml
import os
import time
import traceback
from camera_service import main as run_camera_service
from guardar_horario import send_hourly_data, delete_old_images
from fastapi_server import run_server
import logging
from datetime import datetime
from config_loader import load_config  # Import the function

# Load Config
config = load_config()

# Configure logging for start_threads.py
LOG_DIR = config["logging"]["log_dir"]
STATUS_FILE = config["data"]["status_file"]

# Ensure the log directory exists
if not os.path.exists(LOG_DIR):
    os.makedirs(LOG_DIR)
log_file = os.path.join(LOG_DIR, "start_threads.log")

# Create a specific logger for start_threads
start_threads_logger = logging.getLogger("start_threads")
start_threads_logger.setLevel(logging.INFO)

# Create a file handler for the start_threads log file
file_handler = logging.FileHandler(log_file)
file_handler.setFormatter(logging.Formatter('%(asctime)s - %(levelname)s - %(message)s'))

# Add the file handler to the start_threads logger
start_threads_logger.addHandler(file_handler)

# Create the yaml lock here
yaml_lock = threading.Lock()


def update_status(thread_name, status, lock):
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


def create_status_file(lock):
    """Creates the status file with initial status."""
    initial_status = {
        "camera_service": 0,
        "send_hourly_data": 0,
        "delete_old_images": 0,
        "fastapi_server": 0
    }
    with lock:
        with open(STATUS_FILE, "w") as f:
            yaml.dump(initial_status, f)
            start_threads_logger.info(f"🔄 Status file created in {STATUS_FILE}")


def camera_service_wrapper(lock):
    """Wrapper for camera_service.main with error handling."""
    try:
        update_status("camera_service", 1, lock)
        start_threads_logger.info("🔄 Starting camera_service...")
        run_camera_service(lock)
    except Exception as e:
        start_threads_logger.error(f"❌❌❌ An error in camera_service occurred: {e}")
        traceback.print_exc()
        update_status("camera_service", 0, lock)


def send_hourly_data_wrapper(lock):
    """Wrapper for send_hourly_data with error handling."""
    try:
        update_status("send_hourly_data", 1, lock)
        start_threads_logger.info("🔄 Starting send_hourly_data...")
        send_hourly_data(lock)
    except Exception as e:
        start_threads_logger.error(f"❌❌❌ An error in send_hourly_data occurred: {e}")
        traceback.print_exc()
        update_status("send_hourly_data", 0, lock)


def delete_old_images_wrapper(lock):
    """Wrapper for delete_old_images with error handling."""
    try:
        update_status("delete_old_images", 1, lock)
        start_threads_logger.info("🔄 Starting delete_old_images...")
        delete_old_images(lock)
    except Exception as e:
        start_threads_logger.error(f"❌❌❌ An error in delete_old_images occurred: {e}")
        traceback.print_exc()
        update_status("delete_old_images", 0, lock)


def run_server_wrapper(lock):
    """Wrapper for run_server with error handling."""
    try:
        update_status("fastapi_server", 1, lock)
        start_threads_logger.info("🔄 Starting fastapi_server...")
        run_server(lock)
    except Exception as e:
        start_threads_logger.error(f"❌❌❌ An error in fastapi occurred: {e}")
        traceback.print_exc()
        update_status("fastapi_server", 0, lock)


def main():
    """Main function to start and manage the threads."""
    # Create the status file if it doesn't exist
    if not os.path.exists(STATUS_FILE):
        create_status_file(yaml_lock)
    
    #ensure all the threads are in status 0
    update_status("camera_service", 0, yaml_lock)
    update_status("send_hourly_data", 0, yaml_lock)
    update_status("delete_old_images", 0, yaml_lock)
    update_status("fastapi_server", 0, yaml_lock)

    # Start the threads, passing the lock
    camera_thread = threading.Thread(target=camera_service_wrapper, args=(yaml_lock,), daemon=True)
    send_data_thread = threading.Thread(target=send_hourly_data_wrapper, args=(yaml_lock,), daemon=True)
    delete_images_thread = threading.Thread(target=delete_old_images_wrapper, args=(yaml_lock,), daemon=True)
    fastapi_thread = threading.Thread(target=run_server_wrapper, args=(yaml_lock,), daemon=True)

    start_threads_logger.info(f"🔄 Starting threads at {datetime.now()}")
    fastapi_thread.start()
    camera_thread.start()
    send_data_thread.start()
    delete_images_thread.start()

    while True:
        time.sleep(1)  # Keep the main thread alive


if __name__ == "__main__":
    main()
