from flask import Flask, jsonify, request, session, redirect
from flask_cors import CORS
from flask_socketio import SocketIO, emit
import requests
from urllib.parse import urlencode
import secrets
import os
import logging
from config import Config
from cog_manager import CogManager

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = Flask(__name__)
app.config.from_object(Config)
CORS(app, origins=Config.CORS_ORIGINS, supports_credentials=True)

socketio = SocketIO(app, cors_allowed_origins=Config.CORS_ORIGINS, async_mode='threading')

cog_manager = CogManager(Config.COG_SETTINGS_PATH, Config.COG_METADATA_PATH)

DISCORD_OAUTH2_URL = 'https://discord.com/api/oauth2/authorize'
DISCORD_TOKEN_URL = 'https://discord.com/api/oauth2/token'

@app.route('/')
def index():
    return jsonify({
        'status': 'online',
        'service': 'JackyBot Web Interface'
    })

@app.route('/auth/login')
def login():
    state = secrets.token_urlsafe(16)
    session['oauth_state'] = state
    session.permanent = True
    
    params = {
        'client_id': Config.DISCORD_CLIENT_ID,
        'redirect_uri': Config.DISCORD_REDIRECT_URI,
        'response_type': 'code',
        'scope': 'identify guilds',
        'state': state
    }
    
    auth_url = f"{DISCORD_OAUTH2_URL}?{urlencode(params)}"
    logger.info(f"OAuth login initiated, state saved: {state[:8]}...")
    return jsonify({'url': auth_url})

@app.route('/auth/callback')
def callback():
    code = request.args.get('code')
    state = request.args.get('state')
    error = request.args.get('error')
    
    if error:
        logger.error(f"OAuth error from Discord: {error}")
        return jsonify({'error': f'OAuth error: {error}'}), 400
    
    if not code:
        logger.warning("OAuth callback missing code parameter")
        return jsonify({'error': 'Missing authorization code'}), 400
    
    saved_state = session.get('oauth_state')
    if not saved_state:
        logger.warning("OAuth callback missing session state - session may have expired or cookies not working")
        return jsonify({'error': 'Session expired. Please try logging in again.'}), 400
    
    if state != saved_state:
        logger.warning(f"OAuth state mismatch: received {state[:8] if state else None}..., expected {saved_state[:8]}...")
        return jsonify({'error': 'Invalid OAuth state. Possible CSRF attack or session expired.'}), 400
    
    data = {
        'client_id': Config.DISCORD_CLIENT_ID,
        'client_secret': Config.DISCORD_CLIENT_SECRET,
        'grant_type': 'authorization_code',
        'code': code,
        'redirect_uri': Config.DISCORD_REDIRECT_URI
    }
    
    headers = {'Content-Type': 'application/x-www-form-urlencoded'}
    
    try:
        response = requests.post(DISCORD_TOKEN_URL, data=data, headers=headers)
        response.raise_for_status()
        credentials = response.json()
        
        session['access_token'] = credentials['access_token']
        session['refresh_token'] = credentials.get('refresh_token')
        session.permanent = True
        session.pop('oauth_state', None)
        
        logger.info("OAuth callback successful, redirecting to dashboard")
        return redirect(f'{Config.WEB_INTERFACE_URL}/dashboard')
    except requests.exceptions.HTTPError as e:
        logger.error(f"Discord API error: {e.response.status_code} - {e.response.text}")
        return jsonify({'error': f'Discord API error: {e.response.status_code}'}), 500
    except Exception as e:
        logger.error(f"OAuth callback error: {str(e)}")
        return jsonify({'error': str(e)}), 500

@app.route('/auth/user')
def get_user():
    access_token = session.get('access_token')
    
    if not access_token:
        return jsonify({'error': 'Not authenticated'}), 401
    
    headers = {'Authorization': f'Bearer {access_token}'}
    
    try:
        response = requests.get(f'{Config.DISCORD_API_BASE}/users/@me', headers=headers)
        response.raise_for_status()
        return jsonify(response.json())
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/auth/logout', methods=['POST'])
def logout():
    session.clear()
    return jsonify({'success': True})

@app.route('/api/servers')
def get_servers():
    access_token = session.get('access_token')
    
    if not access_token:
        return jsonify({'error': 'Not authenticated'}), 401
    
    headers = {'Authorization': f'Bearer {access_token}'}
    
    try:
        response = requests.get(f'{Config.DISCORD_API_BASE}/users/@me/guilds', headers=headers)
        response.raise_for_status()
        guilds = response.json()
        
        admin_guilds = [g for g in guilds if (int(g['permissions']) & 0x8) == 0x8]
        
        return jsonify(admin_guilds)
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/cogs')
def get_cogs():
    if not session.get('access_token'):
        return jsonify({'error': 'Not authenticated'}), 401
    
    cogs = cog_manager.get_all_cogs()
    return jsonify(cogs)

@app.route('/api/servers/<server_id>/settings')
def get_server_settings(server_id):
    if not session.get('access_token'):
        return jsonify({'error': 'Not authenticated'}), 401
    
    settings = cog_manager.get_server_settings(server_id)
    
    if not settings:
        settings = cog_manager.initialize_server_settings(server_id)
    
    return jsonify(settings)

@app.route('/api/servers/<server_id>/settings', methods=['POST'])
def update_server_settings(server_id):
    if not session.get('access_token'):
        return jsonify({'error': 'Not authenticated'}), 401
    
    data = request.json
    cog_name = data.get('cog_name')
    enabled = data.get('enabled')
    
    if not cog_name or enabled is None:
        return jsonify({'error': 'Missing cog_name or enabled'}), 400
    
    updated_settings = cog_manager.update_server_settings(server_id, cog_name, enabled)
    
    socketio.emit('cog_update', {
        'server_id': server_id,
        'cog_name': cog_name,
        'enabled': enabled
    }, broadcast=True)
    
    return jsonify(updated_settings)

@socketio.on('connect')
def handle_connect():
    print('Client connected')

@socketio.on('disconnect')
def handle_disconnect():
    print('Client disconnected')

if __name__ == '__main__':
    debug_mode = os.environ.get('FLASK_DEBUG', 'False').lower() == 'true'
    socketio.run(app, host='0.0.0.0', port=Config.WEBSOCKET_PORT, debug=debug_mode)

