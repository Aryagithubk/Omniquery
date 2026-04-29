import os
import yaml
from typing import Dict, Any

class PromptLoader:
    """Loads prompt templates from YAML configuration files."""
    
    def __init__(self, base_path: str = None):
        if base_path is None:
            # Assuming src/config/prompt_loader.py, the prompts dir is in src/config/prompts
            current_dir = os.path.dirname(os.path.abspath(__file__))
            self.base_path = os.path.join(current_dir, "prompts")
        else:
            self.base_path = base_path

        # Create directory if it doesn't exist
        os.makedirs(self.base_path, exist_ok=True)

    def load_prompt(self, agent_name: str) -> Dict[str, Any]:
        """Loads prompt configurations for a specific agent by name."""
        file_path = os.path.join(self.base_path, f"{agent_name}.yaml")
        if not os.path.exists(file_path):
            raise FileNotFoundError(f"Prompt configuration file for {agent_name} not found at {file_path}")
            
        with open(file_path, "r", encoding="utf-8") as f:
            try:
                return yaml.safe_load(f) or {}
            except Exception as e:
                raise ValueError(f"Failed to parse YAML file {file_path}: {e}")
