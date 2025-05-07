import sqlite3
from datetime import datetime, timedelta
import random
import logging
import os

# Configure logging
LOG_DIR = "logs"
if not os.path.exists(LOG_DIR):
    os.makedirs(LOG_DIR)
log_file = os.path.join(LOG_DIR, "insert_sample_data.log")

logging.basicConfig(filename=log_file, level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

def insert_sample_data(db_path="detections.db", num_records=100):
    """
    Inserts sample vehicle detection data into the SQLite database.

    Args:
        db_path (str): The path to the SQLite database file.
        num_records (int): The number of sample records to insert.
    """
    conn = None
    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()

        # Ensure the table exists
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS detections (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT,
                vehicle_id TEXT,
                x_position REAL,
                y_position REAL,
                direction TEXT,
                image BLOB
            )
        """)

        for i in range(num_records):
            # Generate random data
            timestamp = (datetime.now() - timedelta(minutes=random.randint(60, 65))).strftime("%Y-%m-%d %H:%M:%S")  # Up to 24 hours ago
            logging.info(timestamp)
            vehicle_id = f"vehicle-{random.randint(1, 1000)}"
            x_position = random.uniform(0, 640)  # Assuming a 640x480 frame
            y_position = random.uniform(0, 480)
            directions = ["ascending", "descending", "static", "unknown"]
            direction = random.choice(directions)
            image_data = None #no image

            # Insert the data
            cursor.execute(
                "INSERT INTO detections (timestamp, vehicle_id, x_position, y_position, direction, image) VALUES (?, ?, ?, ?, ?, ?)",
                (timestamp, vehicle_id, x_position, y_position, direction, image_data),
            )

        conn.commit()
        logging.info(f"✅ Inserted {num_records} sample records into {db_path}")

    except sqlite3.Error as e:
        logging.error(f"❌ An error occurred: {e}")
    finally:
        if conn:
            conn.close()

if __name__ == "__main__":
    insert_sample_data()
