from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from datetime import datetime, timedelta
from typing import List
import psycopg2
import os
import uvicorn
import logging
import threading
import sqlite3
import yaml
from config_loader import load_config

# Load Config
config = load_config()

app = FastAPI()

# Database configuration for the master database (PostgreSQL)
STATUS_FILE = config["data"]["status_file"]
LOG_DIR = config["logging"]["log_dir"]
MASTER_DB_HOST = config["master_db"]["host"]
MASTER_DB_NAME = config["master_db"]["name"]
MASTER_DB_USER = config["master_db"]["user"]
MASTER_DB_PASSWORD = config["master_db"]["password"]
DB_PATH = config["data"]["db_path"]

# Ensure the log directory exists
if not os.path.exists(LOG_DIR):
    os.makedirs(LOG_DIR)
log_file = os.path.join(LOG_DIR, "fastapi_server.log")

# Create a specific logger for fastapi_server
fastapi_logger = logging.getLogger("fastapi_server")
fastapi_logger.setLevel(logging.INFO)

# Create a file handler for the fastapi_server log file
file_handler = logging.FileHandler(log_file)
file_handler.setFormatter(logging.Formatter('%(asctime)s - %(levelname)s - %(message)s'))

# Add the file handler to the fastapi_server logger
fastapi_logger.addHandler(file_handler)

# Create a lock for logging
log_lock = threading.Lock()
conn_lock = threading.Lock()
# SQLite database path



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


# Create the master database table if it doesn't exist
def create_master_db():
    """
    Creates the master database with the necessary tables if they do not already exist.

    This function connects to the PostgreSQL database using the provided connection parameters.
    It creates two tables:
    - master_detections: Stores detection data with fields for id, timestamp, vehicle_id, x_position, y_position, and direction.
    - last_upload: Stores the last upload time with fields for id and last_upload_time.

    If the last_upload table is empty, it initializes the last_upload_time with the current time minus one day.

    Prints a success message if the database is created correctly, otherwise prints an error message.

    Raises:
        Exception: If there is an error creating the database.
    """
    conn = None
    try:
        conn = psycopg2.connect(
            host=MASTER_DB_HOST,
            database=MASTER_DB_NAME,
            user=MASTER_DB_USER,
            password=MASTER_DB_PASSWORD,
        )
        cursor = conn.cursor()
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS master_detections (
                id SERIAL PRIMARY KEY,
                timestamp TEXT,
                vehicle_id TEXT,
                x_position REAL,
                y_position REAL,
                direction TEXT
            )
        """)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS last_upload (
                id SERIAL PRIMARY KEY,
                last_upload_time TEXT
            )
        """)
        # Initialize last_upload_time if it doesn't exist
        cursor.execute("SELECT * FROM last_upload")
        if not cursor.fetchone():
            cursor.execute("INSERT INTO last_upload (last_upload_time) VALUES (%s)", [str(datetime.now() - timedelta(days=1))])
        conn.commit()
        with log_lock:
            fastapi_logger.info('✅ Database created correctly')
    except Exception as e:
        with log_lock:
            fastapi_logger.error(f"❌ Error creating database: {e}")
    finally:
        if conn:
            conn.close()


# Run the db creation
#create_master_db()

# Pydantic model for the incoming data
class DetectionData(BaseModel):
    id: int
    timestamp: str
    vehicle_id: str
    x_position: float
    y_position: float
    direction: str

@app.get("/ultima imagen")
def get_last_image():   
    """Returns the last image from the master database."""
    with conn_lock:
        conn= sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute("SELECT image FROM preview_images LIMIT 1")
        result = cursor.fetchone()
        conn.close()
    return result[0] if result and result[0] else None

# Endpoint to get the last upload time
@app.get("/last-upload-time")
def get_last_upload_time():
    """Returns the last upload time from the master database."""
    conn = None
    try:
        conn = psycopg2.connect(
            host=MASTER_DB_HOST,
            database=MASTER_DB_NAME,
            user=MASTER_DB_USER,
            password=MASTER_DB_PASSWORD,
        )
        cursor = conn.cursor()
        cursor.execute("SELECT MAX(last_upload_time) FROM last_upload")
        result = cursor.fetchone()

        if result and result[0]:
            return {"last_upload_time": result[0]}
        else:
            raise HTTPException(status_code=404, detail="Last upload time not found")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error getting last upload time: {e}")
    finally:
        if conn:
            conn.close()


# Endpoint to receive data batches
@app.post("/subir-detecciones")
def receive_data_batch(data: List[DetectionData]):
    """
    Receives a batch of detection data and stores it in the master database.
    Args:
        data (List[DetectionData]): A list of detection data items to be stored.
    Returns:
        dict: A message indicating the success of the operation.
    Raises:
        HTTPException: If there is an error storing the data in the database.
    """
    conn = None
    try:
        conn = psycopg2.connect(
            host=MASTER_DB_HOST,
            database=MASTER_DB_NAME,
            user=MASTER_DB_USER,
            password=MASTER_DB_PASSWORD,
        )
        cursor = conn.cursor()

        # Get the latest timestamp from the data
        latest_timestamp = max(item.timestamp for item in data)

        for item in data:
            cursor.execute(
                "INSERT INTO master_detections (timestamp, vehicle_id, x_position, y_position, direction) VALUES (%s, %s, %s, %s, %s)",
                (item.timestamp, item.vehicle_id, item.x_position, item.y_position, item.direction),
            )
        conn.commit()
        with log_lock:
            fastapi_logger.info(f"✅ Data batch received and stored: {len(data)} items")

        # Update the last upload time with the latest timestamp from the data
        cursor.execute("INSERT INTO last_upload (last_upload_time) VALUES (%s)", (latest_timestamp,))
        conn.commit()

        return {"message": "Data batch received and stored successfully"}

    except Exception as e:
        if conn:
            conn.rollback()
        raise HTTPException(status_code=500, detail=f"Error storing data: {e}")
    finally:
        if conn:
            conn.close()


# Endpoint to receive alerts
class AlertData(BaseModel):
    timestamp: str
    vehicle_id: str
    x_position: float
    y_position: float
    alert: str


@app.post("/alerta")
def receive_alert(data: AlertData):
    """Receives an alert."""
    conn = None
    try:
        with log_lock:
            fastapi_logger.info(f"🔔 Alert received: {data}")
        return {"message": "Alert received successfully", "alert": data.alert}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error receiving alert: {e}")
    finally:
        if conn:
            conn.close()


def run_server(lock):
    """Runs the FastAPI server."""
    update_status("fastapi_server", 1, lock)
    uvicorn.run(app, host="0.0.0.0", port=config["servers"]["fastapi"]["port"])
