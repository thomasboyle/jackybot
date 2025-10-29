import json
import os
from typing import Dict, List, Optional
from threading import Lock

class CogManager:
    def __init__(self, settings_path: str, metadata_path: str):
        self.settings_path = settings_path
        self.metadata_path = metadata_path
        self.lock = Lock()
        self._ensure_files_exist()
    
    def _ensure_files_exist(self):
        if not os.path.exists(self.settings_path):
            os.makedirs(os.path.dirname(self.settings_path), exist_ok=True)
            with open(self.settings_path, 'w') as f:
                json.dump({}, f)
        
        if not os.path.exists(self.metadata_path):
            os.makedirs(os.path.dirname(self.metadata_path), exist_ok=True)
            with open(self.metadata_path, 'w') as f:
                json.dump([], f)
    
    def load_settings(self) -> Dict:
        with self.lock:
            try:
                with open(self.settings_path, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except Exception as e:
                print(f"Error loading settings: {e}")
                return {}
    
    def save_settings(self, settings: Dict):
        with self.lock:
            try:
                with open(self.settings_path, 'w', encoding='utf-8') as f:
                    json.dump(settings, f, indent=2)
            except Exception as e:
                print(f"Error saving settings: {e}")
    
    def get_server_settings(self, server_id: str) -> Dict:
        settings = self.load_settings()
        return settings.get(server_id, {})
    
    def update_server_settings(self, server_id: str, cog_name: str, enabled: bool):
        settings = self.load_settings()
        
        if server_id not in settings:
            settings[server_id] = {}
        
        if cog_name not in settings[server_id]:
            settings[server_id][cog_name] = {}
        
        settings[server_id][cog_name]['enabled'] = enabled
        self.save_settings(settings)
        
        return settings[server_id]
    
    def load_metadata(self) -> List[Dict]:
        with self.lock:
            try:
                with open(self.metadata_path, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except Exception as e:
                print(f"Error loading metadata: {e}")
                return []
    
    def get_all_cogs(self) -> List[Dict]:
        return self.load_metadata()
    
    def initialize_server_settings(self, server_id: str) -> Dict:
        settings = self.load_settings()
        
        if server_id not in settings:
            settings[server_id] = {}
            metadata = self.load_metadata()
            
            for cog in metadata:
                settings[server_id][cog['name']] = {'enabled': True}
            
            self.save_settings(settings)
        
        return settings[server_id]

