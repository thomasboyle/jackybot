from flask import Flask, jsonify, request, session, redirect, send_file
from flask_cors import CORS
from flask_socketio import SocketIO, emit
import requests
from urllib.parse import urlencode
import secrets
import os
import logging
import threading
import time
import tempfile
import ffmpeg
import signal
import subprocess
import threading
from PIL import Image
from werkzeug.utils import secure_filename
from config import Config
from cog_manager import CogManager

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

app = Flask(__name__)
app.config.from_object(Config)

# Configure Flask to trust proxy headers (needed for proper HTTPS detection behind Nginx)
from werkzeug.middleware.proxy_fix import ProxyFix
app.wsgi_app = ProxyFix(app.wsgi_app, x_proto=1, x_host=1)

# When behind an HTTPS proxy (like Nginx), detect HTTPS from X-Forwarded-Proto header
# If WEB_INTERFACE_URL is HTTPS, assume we're behind an HTTPS proxy
if Config.WEB_INTERFACE_URL.startswith('https://'):
    app.config['SESSION_COOKIE_SECURE'] = True
    logger.info("Session cookie Secure set to True (HTTPS enabled)")
else:
    app.config['SESSION_COOKIE_SECURE'] = False
    logger.info("Session cookie Secure set to False (HTTP only)")

# Ensure SameSite allows cookies to work cross-site if needed
if app.config.get('SESSION_COOKIE_SAMESITE') == 'Strict':
    app.config['SESSION_COOKIE_SAMESITE'] = 'Lax'
    logger.info("Session cookie SameSite set to Lax for compatibility")

CORS(app, origins=Config.CORS_ORIGINS, supports_credentials=True)

socketio = SocketIO(app, cors_allowed_origins=Config.CORS_ORIGINS, async_mode='threading')

@app.before_request
def log_request_info():
    if request.path.startswith('/auth') or request.path.startswith('/api'):
        logger.info(f"Request: {request.method} {request.path}")
        logger.info(f"  Host: {request.host}, Origin: {request.headers.get('Origin')}")
        logger.info(f"  Cookies received: {list(request.cookies.keys())}")
        logger.info(f"  Session keys: {list(session.keys())}")

cog_manager = CogManager(Config.COG_SETTINGS_PATH, Config.COG_METADATA_PATH)

# Global list to track running FFmpeg processes
ffmpeg_processes = []
ffmpeg_processes_lock = threading.Lock()

def cleanup_ffmpeg_processes():
    """Clean up any running FFmpeg processes"""
    with ffmpeg_processes_lock:
        for proc in ffmpeg_processes[:]:  # Copy list to avoid modification during iteration
            try:
                if proc.poll() is None:  # Process is still running
                    logging.info(f"Terminating FFmpeg process {proc.pid}")
                    proc.terminate()
                    # Wait a bit for graceful termination
                    try:
                        proc.wait(timeout=5)
                    except subprocess.TimeoutExpired:
                        logging.warning(f"Force killing FFmpeg process {proc.pid}")
                        proc.kill()
                        proc.wait()
                ffmpeg_processes.remove(proc)
            except Exception as e:
                logging.error(f"Error cleaning up FFmpeg process: {e}")

def signal_handler(signum, frame):
    """Handle shutdown signals"""
    logging.info(f"Received signal {signum}, cleaning up...")
    cleanup_ffmpeg_processes()
    exit(0)

# Register signal handlers
signal.signal(signal.SIGINT, signal_handler)
signal.signal(signal.SIGTERM, signal_handler)


DISCORD_OAUTH2_URL = 'https://discord.com/oauth2/authorize'
DISCORD_TOKEN_URL = 'https://discord.com/api/oauth2/token'

_refresh_locks = {}  # Maps refresh_token -> (lock, condition, in_progress, result, new_access_token)
_refresh_locks_lock = threading.Lock()  # Protects _refresh_locks dict

def refresh_access_token():
    refresh_token = session.get('refresh_token')
    if not refresh_token:
        logger.warning("Attempted token refresh but no refresh_token in session")
        return False
    
    with _refresh_locks_lock:
        if refresh_token not in _refresh_locks:
            lock = threading.Lock()
            condition = threading.Condition(lock)
            _refresh_locks[refresh_token] = {
                'lock': lock,
                'condition': condition,
                'in_progress': False,
                'result': None,
                'new_access_token': None
            }
        refresh_state = _refresh_locks[refresh_token]
    
    lock = refresh_state['lock']
    condition = refresh_state['condition']
    
    with condition:
        if refresh_state['in_progress']:
            logger.info("Token refresh already in progress for this session, waiting for completion")
            condition.wait()
            if refresh_state['result'] and refresh_state['new_access_token']:
                session['access_token'] = refresh_state['new_access_token']
                logger.info("Updated session with refreshed token from concurrent request")
            return refresh_state['result']
        
        refresh_state['in_progress'] = True
        refresh_state['result'] = None
        refresh_state['new_access_token'] = None
    
    data = {
        'client_id': Config.DISCORD_CLIENT_ID,
        'client_secret': Config.DISCORD_CLIENT_SECRET,
        'grant_type': 'refresh_token',
        'refresh_token': refresh_token
    }
    
    headers = {'Content-Type': 'application/x-www-form-urlencoded'}
    
    try:
        response = requests.post(DISCORD_TOKEN_URL, data=data, headers=headers)
        response.raise_for_status()
        credentials = response.json()
        
        new_access_token = credentials['access_token']
        new_refresh_token = credentials.get('refresh_token')
        
        session['access_token'] = new_access_token
        if new_refresh_token:
            session['refresh_token'] = new_refresh_token
        session.permanent = True
        
        with condition:
            refresh_state['new_access_token'] = new_access_token
            refresh_state['in_progress'] = False
            refresh_state['result'] = True
            condition.notify_all()
        
        logger.info("Access token refreshed successfully")
        
        def cleanup_refresh_state():
            time.sleep(60)
            with _refresh_locks_lock:
                _refresh_locks.pop(refresh_token, None)
        threading.Thread(target=cleanup_refresh_state, daemon=True).start()
        
        return True
    except requests.exceptions.HTTPError as e:
        logger.error(f"Token refresh failed: {e.response.status_code} - {e.response.text}")
        session.clear()
        with condition:
            refresh_state['in_progress'] = False
            refresh_state['result'] = False
            condition.notify_all()
        return False
    except Exception as e:
        logger.error(f"Token refresh error: {str(e)}")
        with condition:
            refresh_state['in_progress'] = False
            refresh_state['result'] = False
            condition.notify_all()
        return False

def make_discord_request(method, endpoint, **kwargs):
    access_token = session.get('access_token')
    if not access_token:
        return None, 401

    headers = kwargs.get('headers', {})
    headers['Authorization'] = f'Bearer {access_token}'
    kwargs['headers'] = headers

    try:
        response = requests.request(method, f'{Config.DISCORD_API_BASE}{endpoint}', **kwargs)
        if response.status_code == 401:
            logger.info(f"Access token expired for {endpoint}, attempting refresh")
            if refresh_access_token():
                access_token = session.get('access_token')
                if not access_token:
                    logger.error("Token refresh succeeded but no access_token in session")
                    return None, 401
                headers['Authorization'] = f'Bearer {access_token}'
                logger.info(f"Retrying {endpoint} with refreshed token")
                response = requests.request(method, f'{Config.DISCORD_API_BASE}{endpoint}', **kwargs)
                if response.status_code == 401:
                    logger.error(f"Discord API still returned 401 after token refresh for {endpoint}: {response.text}")
                    return None, 401
                logger.info(f"Retry successful for {endpoint}, status: {response.status_code}")
            else:
                logger.error("Token refresh failed")
                return None, 401
        return response, response.status_code
    except Exception as e:
        logger.error(f"Error making Discord API request: {str(e)}")
        return None, 500

def make_bot_discord_request(method, endpoint, **kwargs):
    """Make Discord API request using bot token instead of user OAuth2 token"""
    bot_token = Config.DISCORD_BOT_TOKEN
    if not bot_token:
        logger.error("Bot token not configured")
        return None, 500

    headers = kwargs.get('headers', {})
    headers['Authorization'] = f'Bot {bot_token}'
    kwargs['headers'] = headers

    try:
        response = requests.request(method, f'{Config.DISCORD_API_BASE}{endpoint}', **kwargs)
        return response, response.status_code
    except Exception as e:
        logger.error(f"Error making bot Discord API request: {str(e)}")
        return None, 500

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
    
    if not Config.DISCORD_CLIENT_ID:
        logger.error("DISCORD_CLIENT_ID not configured")
        return jsonify({'error': 'Discord OAuth not configured'}), 500
    
    if not Config.DISCORD_REDIRECT_URI:
        logger.error("DISCORD_REDIRECT_URI not configured")
        return jsonify({'error': 'Discord redirect URI not configured'}), 500
    
    redirect_uri = Config.DISCORD_REDIRECT_URI
    if 'localhost' in redirect_uri or '127.0.0.1' in redirect_uri:
        logger.warning(f"Redirect URI contains localhost/127.0.0.1: {redirect_uri}. This will NOT work for external users accessing the site from other machines. Ensure DISCORD_REDIRECT_URI is set to your public URL (e.g., https://91.98.193.41:5173/callback)")
    
    if not redirect_uri.startswith('https://') and not redirect_uri.startswith('http://localhost'):
        logger.warning(f"Redirect URI is not HTTPS: {redirect_uri}. Discord requires HTTPS for non-localhost URIs.")
    
    params = {
        'client_id': Config.DISCORD_CLIENT_ID,
        'redirect_uri': redirect_uri,
        'response_type': 'code',
        'scope': 'identify email guilds',
        'state': state
    }
    
    auth_url = f"{DISCORD_OAUTH2_URL}?{urlencode(params)}"
    logger.info(f"OAuth login initiated, redirect_uri={redirect_uri}, state saved: {state[:8]}..., full URL: {auth_url}")
    return jsonify({'url': auth_url})

@app.route('/auth/callback')
def callback():
    code = request.args.get('code')
    state = request.args.get('state')
    error = request.args.get('error')
    
    callback_url = request.url
    logger.info(f"OAuth callback received: URL={callback_url}, remote_addr={request.remote_addr}")
    logger.info(f"Session before token exchange - keys: {list(session.keys())}, has oauth_state: {bool(session.get('oauth_state'))}")
    
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
    
    redirect_uri = Config.DISCORD_REDIRECT_URI
    logger.info(f"Exchanging code for token using redirect_uri={redirect_uri}")
    
    data = {
        'client_id': Config.DISCORD_CLIENT_ID,
        'client_secret': Config.DISCORD_CLIENT_SECRET,
        'grant_type': 'authorization_code',
        'code': code,
        'redirect_uri': redirect_uri
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
        
        logger.info(f"OAuth callback successful - Session keys after save: {list(session.keys())}, has access_token: {bool(session.get('access_token'))}")
        logger.info(f"Session cookie secure: {app.config.get('SESSION_COOKIE_SECURE')}, same_site: {app.config.get('SESSION_COOKIE_SAMESITE')}")
        
        response = redirect(f'{Config.WEB_INTERFACE_URL}/dashboard')
        return response
    except requests.exceptions.HTTPError as e:
        error_detail = e.response.text if e.response else str(e)
        logger.error(f"Discord API error during token exchange: {e.response.status_code} - {error_detail}. redirect_uri used: {redirect_uri}")
        if e.response.status_code == 400:
            logger.error("This often indicates a redirect_uri mismatch. Ensure DISCORD_REDIRECT_URI matches exactly what's registered in Discord Developer Portal.")
        return jsonify({'error': f'Discord API error: {e.response.status_code}'}), 500
    except Exception as e:
        logger.error(f"OAuth callback error: {str(e)}")
        return jsonify({'error': str(e)}), 500

@app.route('/auth/user')
def get_user():
    logger.info(f"GET /auth/user - Session keys: {list(session.keys())}, has access_token: {bool(session.get('access_token'))}")
    if not session.get('access_token'):
        logger.debug("GET /auth/user - No access token in session")
        return jsonify({'error': 'Not authenticated'}), 401
    
    response, status_code = make_discord_request('GET', '/users/@me')
    
    if not response:
        session.clear()
        return jsonify({'error': 'Not authenticated'}), 401
    
    if status_code != 200:
        logger.error(f"Discord API error in get_user: {status_code} - {response.text}")
        if status_code == 401:
            session.clear()
            return jsonify({'error': 'Not authenticated'}), 401
        return jsonify({'error': f'Discord API error: {status_code}'}), status_code
    
    return jsonify(response.json())

@app.route('/auth/logout', methods=['POST'])
def logout():
    session.clear()
    return jsonify({'success': True})

@app.route('/api/servers')
def get_servers():
    logger.info(f"GET /api/servers - Session keys: {list(session.keys())}, has access_token: {bool(session.get('access_token'))}")
    logger.info(f"  Cookies received: {list(request.cookies.keys())}")
    if not session.get('access_token'):
        logger.warning("GET /api/servers - No access token in session")
        return jsonify({'error': 'Not authenticated'}), 401
    
    response, status_code = make_discord_request('GET', '/users/@me/guilds')
    
    if not response:
        session.clear()
        return jsonify({'error': 'Not authenticated'}), 401
    
    if status_code != 200:
        logger.error(f"Discord API error in get_servers: {status_code} - {response.text}")
        if status_code == 401:
            session.clear()
            return jsonify({'error': 'Not authenticated'}), 401
        return jsonify({'error': f'Discord API error: {status_code}'}), status_code
    
    guilds = response.json()
    admin_guilds = [g for g in guilds if (int(g['permissions']) & 0x8) == 0x8]
    
    return jsonify(admin_guilds)

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
    })
    
    return jsonify(updated_settings)

@app.route('/api/servers/<server_id>/channels/<channel_name>')
def check_channel_exists(server_id, channel_name):
    # This endpoint now uses bot token instead of user OAuth2 token
    # since channel checking requires bot permissions
    response, status_code = make_bot_discord_request('GET', f'/guilds/{server_id}/channels')

    if not response:
        logger.error(f"Failed to fetch channels for server {server_id}: status {status_code}")
        return jsonify({'error': 'Failed to fetch channels'}), status_code or 500

    if status_code != 200:
        logger.error(f"Discord API error for server {server_id}: {status_code} - {response.text}")
        return jsonify({'error': f'Discord API error: {status_code}'}), status_code

    channels = response.json()
    channel_exists = any(ch.get('name') == channel_name and ch.get('type') == 0 for ch in channels)

    return jsonify({'exists': channel_exists})

@app.route('/api/servers/<server_id>/channels')
def get_server_channels(server_id):
    """Get all text channels for a server"""
    if not session.get('access_token'):
        return jsonify({'error': 'Not authenticated'}), 401

    # Use bot token to fetch channels (requires bot permissions)
    response, status_code = make_bot_discord_request('GET', f'/guilds/{server_id}/channels')

    if not response:
        logger.error(f"Failed to fetch channels for server {server_id}: status {status_code}")
        return jsonify({'error': 'Failed to fetch channels'}), status_code or 500

    if status_code != 200:
        logger.error(f"Discord API error for server {server_id}: {status_code} - {response.text}")
        return jsonify({'error': f'Discord API error: {status_code}'}), status_code

    channels = response.json()
    # Filter to only text channels (type 0)
    text_channels = [
        {'id': ch['id'], 'name': ch['name']}
        for ch in channels
        if ch.get('type') == 0  # TEXT CHANNEL
    ]

    return jsonify(text_channels)

@app.route('/api/servers/<server_id>/cogs/highlights/channel')
def get_highlights_channel(server_id):
    """Get the current highlights channel setting"""
    if not session.get('access_token'):
        return jsonify({'error': 'Not authenticated'}), 401

    channel_name = cog_manager.get_cog_setting(server_id, 'highlights', 'channel_name')
    return jsonify({'channel_name': channel_name})

@app.route('/api/servers/<server_id>/cogs/highlights/channel', methods=['POST'])
def set_highlights_channel(server_id):
    """Set the highlights channel setting"""
    if not session.get('access_token'):
        return jsonify({'error': 'Not authenticated'}), 401

    data = request.json
    channel_name = data.get('channel_name')

    if channel_name is None:
        return jsonify({'error': 'Missing channel_name'}), 400

    updated_settings = cog_manager.update_cog_setting(server_id, 'highlights', 'channel_name', channel_name)

    socketio.emit('cog_update', {
        'server_id': server_id,
        'cog_name': 'highlights',
        'settings': updated_settings
    })

    return jsonify({'channel_name': channel_name})

@app.route('/api/convert/video', methods=['POST'])
def convert_video():
    """Convert uploaded video to AV1 format"""
    if not session.get('access_token'):
        return jsonify({'error': 'Not authenticated'}), 401

    if 'file' not in request.files:
        return jsonify({'error': 'No file provided'}), 400

    file = request.files['file']
    if file.filename == '':
        return jsonify({'error': 'No file selected'}), 400

    # Validate file type
    allowed_video_types = ['video/mp4', 'video/quicktime', 'video/x-msvideo', 'video/webm']
    if file.content_type not in allowed_video_types:
        return jsonify({'error': 'Unsupported video format'}), 400

    # Check file size (1GB limit)
    if file.content_length and file.content_length > 1024 * 1024 * 1024:
        return jsonify({'error': 'File too large (max 1GB)'}), 400

    try:
        with tempfile.TemporaryDirectory() as temp_dir:
            # Save uploaded file
            input_filename = secure_filename(file.filename)
            input_path = os.path.join(temp_dir, input_filename)
            file.save(input_path)

            # Determine output filename
            output_filename = os.path.splitext(input_filename)[0] + '_av1.mp4'
            output_path = os.path.join(temp_dir, output_filename)

            # Convert video to AV1 using SVT-AV1 with adaptive settings based on file size
            # Get video info to determine optimal settings
            probe_cmd = [
                'ffprobe', '-v', 'quiet', '-print_format', 'json', '-show_format', '-show_streams', input_path
            ]
            probe_result = subprocess.run(probe_cmd, capture_output=True, text=True)
            video_info = {}

            if probe_result.returncode == 0:
                import json
                probe_data = json.loads(probe_result.stdout)
                video_stream = next((s for s in probe_data.get('streams', []) if s.get('codec_type') == 'video'), {})
                width = video_stream.get('width', 1920)
                height = video_stream.get('height', 1080)
                duration = float(probe_data.get('format', {}).get('duration', '0'))

                video_info = {
                    'width': width,
                    'height': height,
                    'duration': duration,
                    'resolution': width * height
                }

                # Adaptive settings based on resolution and duration
                if video_info['resolution'] > 3840 * 2160:  # 8K+
                    preset = '6'  # Slightly slower but more stable
                    crf = '40'    # Lower quality to reduce file size
                    scale_filter = '-vf scale=-2:2160'  # Scale down to 4K
                elif video_info['resolution'] > 1920 * 1080:  # 4K
                    preset = '7'  # Good balance of speed/quality
                    crf = '38'    # Good quality
                    scale_filter = '-vf scale=-2:1440'  # Scale down to 1440p
                else:  # HD or lower
                    preset = '8'  # Fastest for smaller videos
                    crf = '35'    # High quality
                    scale_filter = ''  # No scaling needed
            else:
                # Fallback settings if probing fails
                preset = '7'
                crf = '38'
                scale_filter = ''

            # Build FFmpeg command with adaptive settings
            cmd = [
                'ffmpeg', '-y', '-i', input_path,
                '-c:v', 'libsvtav1',  # SVT-AV1 encoder
                '-preset', preset,    # Adaptive speed preset
                '-crf', crf,          # Adaptive quality
                '-c:a', 'aac',
                '-b:a', '128k',
                '-movflags', '+faststart',  # Optimize for web streaming
            ]

            # Add scaling filter if needed
            if scale_filter:
                cmd.extend(scale_filter.split())

            cmd.append(output_path)

            # Run FFmpeg process and track it
            proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            with ffmpeg_processes_lock:
                ffmpeg_processes.append(proc)

            try:
                # Adaptive timeout based on video duration (minimum 5 minutes, max 20 minutes)
                duration = video_info.get('duration', 0)
                timeout_seconds = max(300, min(1200, int(duration * 2)))  # 2x duration, clamped between 5-20 min
                logging.info(f"Starting conversion with {timeout_seconds}s timeout for {duration}s video")

                # Wait for completion
                stdout, stderr = proc.communicate(timeout=timeout_seconds)

                if proc.returncode != 0:
                    error_msg = stderr.decode() if stderr else "Unknown FFmpeg error"
                    raise Exception(f"FFmpeg failed with return code {proc.returncode}: {error_msg}")

            finally:
                # Remove from tracked processes
                with ffmpeg_processes_lock:
                    if proc in ffmpeg_processes:
                        ffmpeg_processes.remove(proc)

            # Return the converted file
            return send_file(output_path, as_attachment=True, download_name=output_filename)

    except subprocess.TimeoutExpired:
        logging.error('FFmpeg conversion timed out after 5 minutes')
        cleanup_ffmpeg_processes()  # Clean up in case of timeout
        return jsonify({'error': 'Video conversion timed out'}), 500
    except Exception as e:
        logging.error(f'Conversion error: {str(e)}')
        cleanup_ffmpeg_processes()  # Clean up on any error
        return jsonify({'error': 'Video conversion failed'}), 500

@app.route('/api/convert/image', methods=['POST'])
def convert_image():
    """Convert uploaded image to AVIF format"""
    if not session.get('access_token'):
        return jsonify({'error': 'Not authenticated'}), 401

    if 'file' not in request.files:
        return jsonify({'error': 'No file provided'}), 400

    file = request.files['file']
    if file.filename == '':
        return jsonify({'error': 'No file selected'}), 400

    # Validate file type
    allowed_image_types = ['image/jpeg', 'image/png', 'image/webp', 'image/gif', 'image/bmp']
    if file.content_type not in allowed_image_types:
        return jsonify({'error': 'Unsupported image format'}), 400

    # Check file size (50MB limit)
    if file.content_length and file.content_length > 50 * 1024 * 1024:
        return jsonify({'error': 'File too large (max 50MB)'}), 400

    try:
        with tempfile.TemporaryDirectory() as temp_dir:
            # Save uploaded file
            input_filename = secure_filename(file.filename)
            input_path = os.path.join(temp_dir, input_filename)

            # Determine output filename
            output_filename = os.path.splitext(input_filename)[0] + '.avif'
            output_path = os.path.join(temp_dir, output_filename)

            # Open and convert image to AVIF
            with Image.open(file) as img:
                # Convert to RGB if necessary (AVIF supports RGB and RGBA)
                if img.mode in ('RGBA', 'LA', 'P'):
                    if img.mode == 'P':
                        img = img.convert('RGBA')
                    # For images with transparency, keep it
                elif img.mode != 'RGB':
                    img = img.convert('RGB')

                # Save as AVIF with good quality settings
                img.save(output_path, 'AVIF', quality=80, speed=6)

            # Return the converted file
            return send_file(output_path, as_attachment=True, download_name=output_filename)

    except Exception as e:
        logging.error(f'Image conversion error: {str(e)}')
        return jsonify({'error': 'Image conversion failed'}), 500



@app.teardown_appcontext
def teardown_appcontext(exception=None):
    """Clean up FFmpeg processes when app context ends"""
    cleanup_ffmpeg_processes()

@socketio.on('connect')
def handle_connect():
    print('Client connected')

@socketio.on('disconnect')
def handle_disconnect():
    print('Client disconnected')

if __name__ == '__main__':
    debug_mode = os.environ.get('FLASK_DEBUG', 'False').lower() == 'true'
    socketio.run(app, host='0.0.0.0', port=Config.WEBSOCKET_PORT, debug=debug_mode, allow_unsafe_werkzeug=True)

