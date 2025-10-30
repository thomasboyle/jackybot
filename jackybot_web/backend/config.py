import os
from dotenv import load_dotenv
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent.parent
ENV_FILE = BASE_DIR / '.env'

if ENV_FILE.exists():
    load_dotenv(ENV_FILE)
else:
    load_dotenv()

class Config:
    SECRET_KEY = os.environ.get('FLASK_SECRET_KEY', 'dev-secret-key-change-in-production')
    DISCORD_CLIENT_ID = os.environ.get('DISCORD_CLIENT_ID')
    DISCORD_CLIENT_SECRET = os.environ.get('DISCORD_CLIENT_SECRET')
    DISCORD_REDIRECT_URI = os.environ.get('DISCORD_REDIRECT_URI', 'http://localhost:5000/auth/callback')
    DISCORD_API_BASE = 'https://discord.com/api/v10'
    WEBSOCKET_PORT = int(os.environ.get('WEBSOCKET_PORT', 5000))
    WEB_INTERFACE_URL = os.environ.get('WEB_INTERFACE_URL', 'http://localhost:5173')
    CORS_ORIGINS = os.environ.get('CORS_ORIGINS', 'http://localhost:5173').split(',')
    
    SESSION_COOKIE_SECURE = os.environ.get('SESSION_COOKIE_SECURE', 'False').lower() == 'true'
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = os.environ.get('SESSION_COOKIE_SAMESITE', 'Lax')
    PERMANENT_SESSION_LIFETIME = 86400
    
    COG_SETTINGS_PATH_ENV = os.environ.get('COG_SETTINGS_PATH')
    if COG_SETTINGS_PATH_ENV:
        COG_SETTINGS_PATH = COG_SETTINGS_PATH_ENV if os.path.isabs(COG_SETTINGS_PATH_ENV) else str(BASE_DIR / COG_SETTINGS_PATH_ENV)
    else:
        COG_SETTINGS_PATH = str(BASE_DIR / 'data' / 'cog_settings.json')
    
    COG_METADATA_PATH_ENV = os.environ.get('COG_METADATA_PATH')
    if COG_METADATA_PATH_ENV:
        COG_METADATA_PATH = COG_METADATA_PATH_ENV if os.path.isabs(COG_METADATA_PATH_ENV) else str(BASE_DIR / COG_METADATA_PATH_ENV)
    else:
        COG_METADATA_PATH = str(BASE_DIR / 'cogs' / 'cog_metadata.json')

