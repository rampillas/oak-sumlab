import depthai as dai
import cv2
import numpy as np
import time
import sqlite3
import requests
from datetime import datetime
import vehicles_tracker
from collections import deque
import os
import base64
import traceback
import logging
import threading
import yaml
from config_loader import load_config  # Import the function

# Load Config
config = load_config()

# Configure logging for camera_service
LOG_DIR = config["logging"]["log_dir"]
DB_PATH = config["data"]["db_path"]
STATUS_FILE = config["data"]["status_file"]
BLOB_PATH = config["model"]["yolov8n_blob_path"]
CONFIDENCE_THRESHOLD = config["model"]["confidence_threshold"]
NUM_CLASSES = config["model"]["num_classes"]
COORDINATE_SIZE = config["model"]["coordinate_size"]
IOU_THRESHOLD = config["model"]["iou_threshold"]
MAX_RETRIES = config["application"]["max_retries"]
API_ALERT_URL = config["application"]["api_alert_url"]
OAK_PREVIEW_SIZE_x = config["oak_camera"]["preview_size_x"]
OAK_PREVIEW_SIZE_y = config["oak_camera"]["preview_size_y"]
OAK_FPS = config["oak_camera"]["fps"]
NUMBER_OF_DETECTION_CLASSES = config["oak_camera"]["number_of_detection_classes"]

# Ensure the log directory exists
if not os.path.exists(LOG_DIR):
    os.makedirs(LOG_DIR)
log_file = os.path.join(LOG_DIR, "camera_service.log")

# Create a specific logger for camera_service
camera_logger = logging.getLogger("camera_service")
camera_logger.setLevel(logging.INFO)

# Create a file handler for the camera_service log file
file_handler = logging.FileHandler(log_file)
file_handler.setFormatter(
    logging.Formatter("%(asctime)s - %(levelname)s - %(message)s")
)

# Add the file handler to the camera_service logger
camera_logger.addHandler(file_handler)

# Initialize VehicleTracker
vt = vehicles_tracker.VehicleTracker()

# Create a lock for logging
log_lock = threading.Lock()


def update_status(thread_name, status, lock):  # Receive the lock as a parameter
    """Updates the status in the status.yaml file."""
    with lock:  # Use the lock to ensure thread safety
        try:
            with open(STATUS_FILE, "r") as f:
                data = yaml.safe_load(f) or {}
        except FileNotFoundError:
            data = {}
        data[thread_name] = status
        with open(STATUS_FILE, "w") as f:
            yaml.dump(data, f)


# Initialize the database (if it doesn't exist)
conn = sqlite3.connect(DB_PATH)
cursor = conn.cursor()
if  os.path.exists(DB_PATH):
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS detections (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp TEXT,
            vehicle_id TEXT,
            x_position REAL,
            y_position REAL,
            direction TEXT,
            image BLOB
        )
    """
    )
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS config (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            send_image BOOLEAN,
            refresh_rate REAL
        )
    """
    )
    cursor.execute("INSERT INTO config (send_image, refresh_rate) VALUES (?,?)", (False,0.5))
    conn.commit()
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS preview_images (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            image BLOB
        )
    """
    )
    cursor.execute("INSERT INTO preview_images (image) VALUES (?)", (None,))
    conn.commit()
 
conn.close()


def save_detection(vehicle_id, x_pos, y_pos, direction, image_data=None):
    """Saves a vehicle detection to the database."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    try:
        cursor.execute(
            "INSERT INTO detections (timestamp, vehicle_id, x_position, y_position, direction, image) VALUES (?, ?, ?, ?, ?, ?)",
            (timestamp, vehicle_id, x_pos, y_pos, direction, image_data),
        )
        conn.commit()
        with log_lock:
            camera_logger.debug(f"✅ Detection saved: {vehicle_id} at ({x_pos}, {y_pos}) in direction {direction}")
    except sqlite3.Error as e:
        with log_lock:
            camera_logger.error(f"❌ Error saving detection: {e}")
    finally:
        conn.close()

def save_image(image_data=None):
    """Saves an image to the database."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
   
    try: 
        cursor.execute("DELETE FROM preview_images")   
        cursor.execute(
            f"INSERT into preview_images (image) VALUES (?)", (image_data,)
        )
        
        conn.commit()
       
    except sqlite3.Error as e:  
        with log_lock:
            camera_logger.error(f"❌ Error saving image: {e}")
    finally:
        conn.close()
    

def send_alert(vehicle_id, x_pos, y_pos, alert_type="Sentido contrario"):
    """
    Sends an alert with vehicle information to a specified API endpoint.
    Args:
        vehicle_id (str): The ID of the vehicle.
        x_pos (float): The x-coordinate position of the vehicle.
        y_pos (float): The y-coordinate position of the vehicle.
        alert_type (str): the type of the alert
    Returns:
        None
    Raises:
        requests.exceptions.RequestException: If there is an issue with the HTTP request.
    The function sends a POST request to the API endpoint with the vehicle information
    and a timestamp. If the request is successful, it prints a success message. If the
    request fails, it prints a failure message and indicates that the alert will be
    retried in the next detection.
    """
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    data = {
        "timestamp": timestamp,
        "vehicle_id": vehicle_id,
        "x_position": x_pos,
        "y_position": y_pos,
        "alert": alert_type,
    }

    try:
        response = requests.post(API_ALERT_URL, json=data, timeout=5)
        if response.status_code == 200:
            with log_lock:
                camera_logger.info("✅ Alerta enviada correctamente")
        else:
            with log_lock:
                camera_logger.warning(
                    f"⚠️ Fallo en el envío de alerta, status: {response.status_code}"
                )
    except requests.exceptions.RequestException:
        with log_lock:
            camera_logger.error(
                "❌ No se pudo enviar la alerta, se reintentará en la siguiente detección."
            )


def get_config():
    """Gets the configuration (send_image status) from the database."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    try:
        cursor.execute("SELECT send_image FROM config WHERE id = 1")
        result = cursor.fetchone()
        return result[0] if result else False
    except sqlite3.Error as e:
        with log_lock:
            camera_logger.error(f"❌ Error getting config: {e}")
        return False  # Default to False in case of error
    finally:
        conn.close()

def get_refresh_rate():
    """Gets the refresh rate (in seconds) from the database."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    try:    
        cursor.execute("SELECT refresh_rate FROM config WHERE id = 1")
        result = cursor.fetchone()
        return result[0] if result else 0.5
    except sqlite3.Error as e:
        with log_lock:
            camera_logger.error(f"❌ Error getting refresh rate: {e}")
        return 0.5  # Default to 0.5 in case of error
    finally:
        conn.close()    

def initialize_camera():
    """
    Initializes the OAK-1 camera and returns the pipeline.
    """
    try:
        
        pipeline = dai.Pipeline()
        cam_rgb = pipeline.create(dai.node.ColorCamera)
        cam_rgb.setPreviewSize(OAK_PREVIEW_SIZE_x, OAK_PREVIEW_SIZE_y)
        cam_rgb.setInterleaved(False)
        cam_rgb.setFps(OAK_FPS)

        nn = pipeline.create(dai.node.YoloDetectionNetwork)
        nn.setBlobPath(BLOB_PATH)
        nn.setConfidenceThreshold(CONFIDENCE_THRESHOLD)
        nn.setNumClasses(NUM_CLASSES)
        nn.setCoordinateSize(COORDINATE_SIZE)
        nn.setAnchors([])
        nn.setAnchorMasks({})
        nn.setIouThreshold(IOU_THRESHOLD)

        tracker = pipeline.create(dai.node.ObjectTracker)
        tracker.setDetectionLabelsToTrack(NUMBER_OF_DETECTION_CLASSES)
        tracker.setTrackerType(dai.TrackerType.ZERO_TERM_COLOR_HISTOGRAM)
        tracker.setTrackerIdAssignmentPolicy(
            dai.TrackerIdAssignmentPolicy.UNIQUE_ID
        )

        nn.passthrough.link(tracker.inputTrackerFrame)
        nn.passthrough.link(tracker.inputDetectionFrame)
        nn.out.link(tracker.inputDetections)

        cam_rgb.preview.link(nn.input)

        xout_nn = pipeline.create(dai.node.XLinkOut)
        xout_nn.setStreamName("detections")
        tracker.out.link(xout_nn.input)

        xout_rgb = pipeline.create(dai.node.XLinkOut)
        xout_rgb.setStreamName("video")
        cam_rgb.preview.link(xout_rgb.input)

        with log_lock:
            camera_logger.info("✅ Camera initialized successfully.")
        return pipeline
    except Exception as e:
        with log_lock:
            camera_logger.error(f"❌ Error initializing camera: {e}")
        return None


def run_camera(pipeline):
    """
    Runs the camera detection process.
    """
    with dai.Device(pipeline) as device:
        device.setIrFloodLightIntensity(0.5)
        q_nn = device.getOutputQueue(name="detections", maxSize=4, blocking=False)
        q_video = device.getOutputQueue(name="video", maxSize=4, blocking=False)

        while True:
            frame_count=0
            try:
                in_nn = q_nn.get()
                tracklets = in_nn.tracklets
                mov = vt.calculate_tracklet_movement(tracklets)

                send_image = get_config()

                if send_image:
                    in_video = q_video.get()
                    frame = in_video.getCvFrame()
                    refresh_rate = get_refresh_rate()


                for detection in tracklets:
                    if detection.label in (0, 2, 5, 7):
                        roi = detection.roi.denormalize(
                            OAK_PREVIEW_SIZE, OAK_PREVIEW_SIZE
                        )  # the size of the image
                        x1 = int(roi.topLeft().x)
                        y1 = int(roi.topLeft().y)
                        x2 = int(roi.bottomRight().x)
                        y2 = int(roi.bottomRight().y)
                        label = detection.label
                        x_center = (x1 + x2) // 2
                        y_center = (y1 + y2) // 2
                        vehicle_id = detection.id if hasattr(detection, "id") else None

                        if vehicle_id is not None:
                            direction_history = mov.get(
                                vehicle_id, None
                            )  # Get the history or a new deque if not found

                            last_position = "unknown"
                            if isinstance(direction_history, deque):
                                direction_history_list = list(direction_history)

                                if len(direction_history) > 0:
                                    last_position = direction_history_list[-1]

                                    ascending_count = direction_history_list.count(
                                        "ascending"
                                    )

                                    if ascending_count >= 5:
                                        if send_image:
                                            cv2.putText(
                                                frame,
                                                "-> -> ->",
                                                (x1, y1 - 20),
                                                cv2.FONT_HERSHEY_SIMPLEX,
                                                0.6,
                                                (0, 255, 0),
                                                2,
                                            )
                                        send_alert(vehicle_id, x_center, y1)
                                    elif (
                                        direction_history_list[-1] == "ascending"
                                    ):  # Check only the last direction
                                        if send_image:
                                            cv2.putText(
                                                frame,
                                                "->",
                                                (x1, y1 - 20),
                                                cv2.FONT_HERSHEY_SIMPLEX,
                                                0.6,
                                                (0, 255, 0),
                                                2,
                                            )
                                    elif direction_history_list[-1] == "descending":
                                        if send_image:
                                            cv2.putText(
                                                frame,
                                                "<-",
                                                (x1, y1 - 20),
                                                cv2.FONT_HERSHEY_SIMPLEX,
                                                0.6,
                                                (0, 255, 0),
                                                2,
                                            )
                            if send_image:
                                cv2.rectangle(
                                    frame, (x1, y1), (x2, y2), (0, 255, 0), 2
                                )
                                cv2.putText(
                                    frame,
                                    f" {detection.label} id: {vehicle_id}  conf= {detection.srcImgDetection.confidence:0.2f}",
                                    (x1, y1 - 10),
                                    cv2.FONT_HERSHEY_SIMPLEX,
                                    0.5,
                                    (0, 255, 0),
                                    2,
                                )
                            image_data = None
                            if send_image:
                                if frame_count % int(OAK_FPS * refresh_rate) == 0:
                                    image_data = cv2.imencode(".jpg", frame)[1].tobytes()
                                    save_image(image_data)
                                    frame_count=0
                                else:
                                    frame_count+=1

                            save_detection(
                                vehicle_id, x_center, y_center, last_position, image_data
                            )
                    else:
                        if send_image:
                            if frame_count % int(OAK_FPS * refresh_rate) == 0:
                                image_data = cv2.imencode(".jpg", frame)[1].tobytes()
                                save_image(image_data)
                                frame_count=0
                            else:
                                frame_count+=1
                if not tracklets:
                    if send_image:
                        if frame_count % int(OAK_FPS * refresh_rate) == 0:
                            image_data = cv2.imencode(".jpg", frame)[1].tobytes()
                            save_image(image_data)
                            frame_count=0
                        else:
                            frame_count+=1

                time.sleep(0.03)
            except Exception as e:
                with log_lock:
                    camera_logger.error(f"❌ Error in camera operation: {e}")
                traceback.print_exc()


def main(lock=None):  # Receive the lock as a parameter
    """
    Main function to handle camera operation with error recovery.
    """
    update_status("camera_service", 1, lock)  # Pass the lock to update_status
    max_retries = MAX_RETRIES
    retries = 0
    pipeline = None  # Initialize pipeline to None

    while retries < max_retries:
        try:
            if pipeline is None:
                pipeline = (
                    initialize_camera()
                )  # Initialize the camera only if it's not initialized
            if pipeline is not None:
                run_camera(pipeline)
            else:
                with log_lock:
                    camera_logger.error(
                        "❌ Pipeline is none, the camera will not run."
                    )
                break  # if pipeline is none, exit
        except Exception as e:
            with log_lock:
                camera_logger.error(f"❌ Error in camera operation: {e}")
            traceback.print_exc()
            retries += 1
            with log_lock:
                camera_logger.info(f"🔄 Retrying... (attempt {retries}/{max_retries})")
            pipeline = None  # set pipeline to none to force reinitialization
            time.sleep(5)  # Wait for 5 seconds before retrying

    # If it reaches here, it means max retries have been reached
    update_status("camera_service", 0, lock)  # Pass the lock to update_status
    with log_lock:
        camera_logger.error(
            f"❌❌❌ Max retries reached ({max_retries}). Sending emergency alert."
        )
    send_alert(
        vehicle_id="SYSTEM",
        x_pos=0,
        y_pos=0,
        alert_type=f"CAMERA FAILED after {max_retries} retries.",
    )


if __name__ == "__main__":
    lock= threading.Lock()  # Create a lock for the main function
    main()
