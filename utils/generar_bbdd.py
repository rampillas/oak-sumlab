import sqlite3
import os

# Ruta de la base de datos
DB_PATH = "detections.db"

def init_db():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS detections (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp TEXT,
            vehicle_id TEXT,
            x_position REAL,
            y_position REAL,
            direction TEXT
        )
    """)
    conn.commit()
    conn.close()

# Inicializar la base de datos
init_db()
