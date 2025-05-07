import os
import shutil
import logging

# Configure logging for this script
LOG_DIR = "../logs"
if not os.path.exists(LOG_DIR):
    os.makedirs(LOG_DIR)
log_file = os.path.join(LOG_DIR, "clean_logs.log")

logging.basicConfig(filename=log_file, level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

def clean_logs(log_dir="logs"):
    """Cleans all log files within the specified log directory.

    Args:
        log_dir (str): The path to the directory containing the log files.
    """
    try:
        if not os.path.exists(log_dir):
            logging.warning(f"⚠️ Log directory '{log_dir}' does not exist.")
            return

        for filename in os.listdir(log_dir):
            if filename.endswith(".log"):
                filepath = os.path.join(log_dir, filename)
                try:
                    with open(filepath, "w") as f:
                        f.truncate(0)
                    logging.info(f"🗑️ Log file '{filename}' cleaned successfully.")
                except Exception as e:
                    logging.error(f"❌ Error cleaning log file '{filename}': {e}")
    except Exception as e:
        logging.error(f"❌ An error occurred while cleaning logs: {e}")

if __name__ == "__main__":
    clean_logs()
