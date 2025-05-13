from fastapi import FastAPI, HTTPException, Query
from pydantic import BaseModel
from datetime import datetime, timedelta
from typing import List, Optional
import psycopg2
import os
import uvicorn
import logging
import threading
import sqlite3
import yaml
import base64
from config_loader import load_config



# Load Config
config = load_config()

app = FastAPI()

# Database configuration for the master database (PostgreSQL)
STATUS_FILE = config["data"]["status_file"]
MASTER_DB_HOST = config["master_db"]["host"]
MASTER_DB_NAME = config["master_db"]["name"]
MASTER_DB_USER = config["master_db"]["user"]
MASTER_DB_PASSWORD = config["master_db"]["password"]
DB_PATH = config["data"]["db_path"]

PG_HOST = config["pg_db"]["host"]
PG_NAME= config["pg_db"]["name"]
PG_USERNAME = config["pg_db"]["user"]
PG_PASSWORD = config["pg_db"]["password"]


def log_to_db(level, message):
    try:
        conn = psycopg2.connect(host=PG_HOST, database=PG_NAME, user=PG_USERNAME, password=PG_PASSWORD)
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO fastapi_service_logs (timestamp, level, message) VALUES (NOW(), %s, %s)",
            (level, message)
        )
        conn.commit()
    except Exception as e:
        print(f"Error logging to database: {e}")
    finally:
        if 'conn' in locals():
            conn.close()

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
            log_to_db("INFO", '✅ Database created correctly')
    except Exception as e:
        with log_lock:
            log_to_db("ERROR", f"❌ Error creating database: {e}")
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
            log_to_db("INFO", f"✅ Data batch received and stored: {len(data)} items")

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
            log_to_db("INFO", f"🔔 Alert received: {data}")
        return {"message": "Alert received successfully", "alert": data.alert}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error receiving alert: {e}")
    finally:
        if conn:
            conn.close()


@app.get("/detections")
def get_detections(show_image: Optional[bool] = Query(False, description="Include image in the response")):
    """
    Returns the last 50 detections in JSON format.
    If show_image is True, includes the image from preview_images table.
    """
    conn_sqlite = None
    try:
        with conn_lock:
            conn_sqlite = sqlite3.connect(DB_PATH)
            cursor_sqlite = conn_sqlite.cursor()
            cursor_sqlite.execute("SELECT id, timestamp, vehicle_id, x_position, y_position, direction FROM detections ORDER BY id DESC LIMIT 50")
            rows = cursor_sqlite.fetchall()
            conn_sqlite.close()
        detections = []
        for row in rows:
            detection = {
                "id": row[0],
                "timestamp": row[1],
                "vehicle_id": row[2],
                "x_position": row[3],
                "y_position": row[4],
                "direction": row[5]
            }
            detections.append(detection)
            
        return {"detections": detections}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error fetching detections: {e}")
    finally:
        pass


@app.get("/preview_image")
def get_preview_image():
    """Returns the last image encoded in base64 with key 'image_data'."""
    with conn_lock:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute("SELECT image FROM preview_images LIMIT 1")
        result = cursor.fetchone()
        conn.close()
    if result and result[0]:
        image_bytes = result[0]
        if isinstance(image_bytes, memoryview):
            image_bytes = image_bytes.tobytes()
        image_base64 = base64.b64encode(image_bytes).decode('utf-8')
        return {"image_data": image_base64}
    else:
        raise HTTPException(status_code=404, detail="No preview image found")


@app.get("/vehicle_count_last_hour")
def vehicle_count_last_hour():
    """Returns the count of unique vehicles detected in the last hour."""
    conn = None
    try:
        one_hour_ago = datetime.now() - timedelta(hours=1)
        conn = psycopg2.connect(
            host=MASTER_DB_HOST,
            database=MASTER_DB_NAME,
            user=MASTER_DB_USER,
            password=MASTER_DB_PASSWORD,
        )
        cursor = conn.cursor()
        cursor.execute(
            "SELECT COUNT(DISTINCT vehicle_id) FROM master_detections WHERE timestamp >= %s",
            (one_hour_ago.isoformat(),)
        )
        result = cursor.fetchone()
        count = result[0] if result and result[0] is not None else 0
        return {"count": count}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error fetching vehicle count: {e}")
    finally:
        if conn:
            conn.close()



# Nueva implementación: consulta la tabla fastapi_service_logs en PostgreSQL local
@app.get("/logs")
def get_logs(table: str = Query(..., description="Name of the log table to fetch")):
    """
    Returns the 30 most recent logs from the fastapi_service_logs table in the local PostgreSQL database.
    Each log is represented as a dictionary with keys: timestamp, level, message.
    """
    
    conn = None
    allowed_tables = {
        "fastapi_service_logs",
        "camera_service_logs",
        "guardar_horario_logs",
        "start_threads_logs"
    }
    if table+'_logs' not in allowed_tables:
        raise HTTPException(status_code=400, detail=f"Table '{table}' is not allowed. Allowed tables: {', '.join(allowed_tables)}")

    try:
        conn = psycopg2.connect(
            host=PG_HOST,
            database=PG_NAME,
            user=PG_USERNAME,
            password=PG_PASSWORD,
        )
        cursor = conn.cursor()
        cursor.execute(
            f"SELECT timestamp, level, message FROM {table}_logs ORDER BY timestamp DESC LIMIT 30"
        )
        rows = cursor.fetchall()
        logs = []
        for row in rows:
            log_entry = {
                "timestamp": str(row[0]),
                "level": row[1],
                "message": row[2],
            }
            logs.append(log_entry)
        return logs
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error fetching logs: {e}")
    finally:
        if conn:
            conn.close()


@app.get("/status")
def get_status():
    """Returns the current content of the status.yaml file as JSON."""
    try:
        with open(STATUS_FILE, "r") as f:
            data = yaml.safe_load(f) or {}
        return data
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="Status file not found")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error reading status file: {e}")


class ConfigUpdate(BaseModel):
    send_image: bool
    refresh_rate: float

@app.post("/config")
def update_config(config_data: ConfigUpdate):
    """Updates the config table in SQLite with send_image and refresh_rate."""
    print(config_data)
    with conn_lock:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        try:
            cursor.execute(""" drop table if exists config""")
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS config (
                    id INTEGER PRIMARY KEY,
                    send_image BOOLEAN,
                    refresh_rate REAL
                )
            """)
            cursor.execute("SELECT id FROM config WHERE id=1")
            if cursor.fetchone():
                cursor.execute("UPDATE config SET send_image=?, refresh_rate=? WHERE id=1",
                               (config_data.send_image, config_data.refresh_rate))
            else:
                cursor.execute("INSERT INTO config (id, send_image, refresh_rate) VALUES (1, ?, ?)",
                               (config_data.send_image, config_data.refresh_rate))
            conn.commit()
            return {"message": "Config updated successfully"}
        except Exception as e:
            conn.rollback()
            with log_lock:
                log_to_db("ERROR", f"❌ Error updating config: {e}")
            raise HTTPException(status_code=500, detail=f"Error updating config: {e}")
        finally:
            conn.close()


def run_server(lock):
    """Runs the FastAPI server."""
    update_status("fastapi_server", 1, lock)
    uvicorn.run(app, host="0.0.0.0", port=config["servers"]["fastapi"]["port"])
