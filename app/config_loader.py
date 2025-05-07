# In app/utils/config_loader.py
import yaml
import os

config_path = os.getenv("CONFIG_PATH", "config.yaml")


def load_config(config_path="../config/config.yaml"):
    config_path = config_path
    """Loads configuration from a YAML file."""
    # Ensure config path is absolute for container environments
    if not os.path.isabs(config_path):
        config_path = os.path.abspath(config_path)

    with open(config_path, "r") as f:
        config = yaml.safe_load(f)
    return config
