import threading
import yaml
import os
import time
import traceback
from camera_service import main as run_camera_service
from guardar_horario import send_hourly_data, delete_old_images
from fastapi_server import run_server
from datetime import datetime
from config_loader import load_config  # Import the function
import psycopg2


# Load Config
config = load_config()

PG_HOST = config["pg_db"]["host"]
PG_NAME= config["pg_db"]["name"]
PG_USERNAME = config["pg_db"]["user"]
PG_PASSWORD = config["pg_db"]["password"]


def log_to_db(level, message):
    try:
        conn = psycopg2.connect(host=PG_HOST, database=PG_NAME, user=PG_USERNAME, password=PG_PASSWORD)
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO guardar_horario_logs (timestamp, level, message) VALUES (NOW(), %s, %s)",
            (level, message)
        )
        conn.commit()
    except Exception as e:
        print(f"Error logging to database: {e}")
    finally:
        if 'conn' in locals():
            conn.close()

# Create the yaml lock here
yaml_lock = threading.Lock()


def update_status(thread_name, status, lock):
    """Updates the status in the status.yaml file."""
    with lock:  # Acquire the lock before accessing the YAML file
        try:
            with open(config["data"]["status_file"], "r") as f:
                data = yaml.safe_load(f) or {}
        except FileNotFoundError:
            data = {}
        data[thread_name] = status
        with open(config["data"]["status_file"], "w") as f:
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
        with open(config["data"]["status_file"], "w") as f:
            yaml.dump(initial_status, f)
            log_to_db("INFO", f"🔄 Status file created in {config['data']['status_file']}")


def camera_service_wrapper(lock):
    """Wrapper for camera_service.main with error handling."""
    try:
        update_status("camera_service", 1, lock)
        log_to_db("INFO", "🔄 Starting camera_service...")
        run_camera_service(lock)
    except Exception as e:
        log_to_db("ERROR", f"❌❌❌ An error in camera_service occurred: {e}")
        traceback.print_exc()
        update_status("camera_service", 0, lock)


def send_hourly_data_wrapper(lock):
    """Wrapper for send_hourly_data with error handling."""
    try:
        update_status("send_hourly_data", 1, lock)
        log_to_db("INFO", "🔄 Starting send_hourly_data...")
        send_hourly_data(lock)
    except Exception as e:
        log_to_db("ERROR", f"❌❌❌ An error in send_hourly_data occurred: {e}")
        traceback.print_exc()
        update_status("send_hourly_data", 0, lock)


def delete_old_images_wrapper(lock):
    """Wrapper for delete_old_images with error handling."""
    try:
        update_status("delete_old_images", 1, lock)
        log_to_db("INFO", "🔄 Starting delete_old_images...")
        delete_old_images(lock)
    except Exception as e:
        log_to_db("ERROR", f"❌❌❌ An error in delete_old_images occurred: {e}")
        traceback.print_exc()
        update_status("delete_old_images", 0, lock)


def run_server_wrapper(lock):
    """Wrapper for run_server with error handling."""
    try:
        update_status("fastapi_server", 1, lock)
        log_to_db("INFO", "🔄 Starting fastapi_server...")
        run_server(lock)
    except Exception as e:
        log_to_db("ERROR", f"❌❌❌ An error in fastapi occurred: {e}")
        traceback.print_exc()
        update_status("fastapi_server", 0, lock)


def main():
    """Main function to start and manage the threads."""
    # Create the status file if it doesn't exist
    if not os.path.exists(config["data"]["status_file"]):
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

    log_to_db("INFO", f"🔄 Starting threads at {datetime.now()}")
    fastapi_thread.start()
    camera_thread.start()
    send_data_thread.start()
    delete_images_thread.start()

    while True:
        time.sleep(1)  # Keep the main thread alive


if __name__ == "__main__":
    main()
