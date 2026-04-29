import yaml
import os
import sys

# Add project root to path if needed (though usually handled by caller)
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

from src.utils.logger import setup_logger

logger = setup_logger(__name__)

def load_config(config_path: str = "config.yaml") -> dict:
    """Load configuration from a YAML file."""
    # Robust path finding
    possible_paths = [
        config_path,
        os.path.join(os.getcwd(), config_path),
        os.path.join(os.getcwd(), "company-rag", config_path),
        os.path.join(os.path.dirname(__file__), "..", "..", config_path)
    ]
    
    found_path = None
    for path in possible_paths:
        if os.path.exists(path):
            found_path = path
            break
            
    if not found_path:
        logger.error(f"Config file not found. Checked: {possible_paths}")
        raise FileNotFoundError(f"Config file not found.")

    with open(found_path, "r", encoding="utf-8") as f:
        try:
            config = yaml.safe_load(f)
            logger.info(f"Configuration loaded from {found_path}")
            return config
        except yaml.YAMLError as e:
            logger.error(f"Error parsing config file: {e}")
            raise
