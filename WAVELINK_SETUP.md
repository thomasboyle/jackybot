# Wavelink Music Bot Setup

This guide explains how to set up the new wavelink-based music cog for VPS deployment.

## Prerequisites

- Java 11 or higher installed on your VPS
- The `music_wavelink.py` cog (already created)

## Step 1: Install Lavalink

Lavalink is required for wavelink to work. Use the provided setup script:

**For Linux/Mac (VPS):**
```bash
chmod +x lavalink_setup.sh
./lavalink_setup.sh
```

**For Windows (local testing):**
```batch
lavalink_setup.bat
```

This will:
1. Download the latest Lavalink JAR
2. Create a basic `application.yml` configuration
3. Start Lavalink on port 2333

## Step 2: Environment Variables

Add these to your `.env` file:

```env
LAVALINK_HOST=127.0.0.1
LAVALINK_PORT=2333
LAVALINK_PASSWORD=youshallnotpass
```

**Note:** YouTube authentication is now handled via OAuth (see YouTube OAuth section below), not environment variables.

## Step 3: Install Dependencies

```bash
pip install wavelink>=2.0.0
```

## Step 4: Update Bot

1. Replace the old music cog import with the new one in your bot.py:
   ```python
   # Remove: from cogs.music import MusicBotCog
   # Add: from cogs.music_wavelink import MusicWavelinkCog
   ```

2. Update the cog registration:
   ```python
   # Remove: await bot.add_cog(MusicBotCog(bot))
   # Add: await bot.add_cog(MusicWavelinkCog(bot))
   ```

## Step 5: Run Lavalink in Background

The setup script creates several ways to run Lavalink:

**Quick Start:**
```bash
# Linux/Mac
./start_lavalink.sh

# Windows
start_lavalink.bat
```

**For Production (Linux):**
```bash
# Using the generated systemd service
sudo cp lavalink.service /etc/systemd/system/
sudo systemctl enable lavalink
sudo systemctl start lavalink

# Or using screen
screen -S lavalink
./start_lavalink.sh
# Detach with Ctrl+A, D
```

**For Production (Windows):**
Use Windows Services or run in a separate command window. For 24/7 operation, consider using a process manager like NSSM.

## Features

The wavelink version includes:
- **YouTube Support**: Full YouTube integration via lavalink-devs/youtube-source plugin
- **YouTube Music**: Dedicated YouTube Music search and playback
- **Better Performance**: Distributed audio processing
- **Built-in Seeking**: Native seek support
- **Automatic Queue**: Better queue management with shuffle, clear, remove
- **Lyrics Support**: Same lyrics functionality as before
- **Control Buttons**: Pause, skip, seek, loop, lyrics
- **Playlist Support**: Automatic YouTube playlist detection and queueing
- **VPS Optimized**: Better resource management
- **Multiple Clients**: Uses MUSIC, ANDROID_TESTSUITE, WEB, and TVHTML5EMBEDDED clients for reliability

## Commands

### Playback Commands
- `!play <query>` - Play music (auto-detects source or uses YouTube by default)
- `!ytplay <query>` - Play specifically from YouTube
- `!ytmusic <query>` - Play from YouTube Music
- `!pause` - Pause/resume playback
- `!skip` - Skip current track
- `!stopmusic` or `!musicstop` - Stop playback and clear queue
- `!disconnect` - Disconnect from voice channel

### Queue Management
- `!queue` - Show current queue
- `!clear` - Clear the queue
- `!shuffle` - Shuffle the queue
- `!remove <position>` - Remove track at position from queue
- `!np` or `!nowplaying` - Show currently playing track

### Playback Control
- `!volume <0-100>` - Set playback volume
- `!loop` - Toggle loop mode for current track

## YouTube Plugin Configuration

The bot uses the youtube-source plugin from lavalink-devs for enhanced YouTube support.

### Plugin Details
- **Repository**: https://github.com/lavalink-devs/youtube-source
- **Plugin File**: `youtube-plugin.jar` (located in `plugins/` directory)
- **Configuration**: Set in `application.yml` under `plugins.youtube`

### YouTube OAuth Authentication (Age-Restricted Videos)
To play age-restricted videos and avoid bot detection, YouTube OAuth authentication is supported.

**Configuration in `application.yml`:**
```yaml
plugins:
  youtube:
    oauth:
      enabled: true
```

**OAuth Flow:**
1. When Lavalink starts with OAuth enabled (first time only), it will:
   - Display a code in the terminal/logs
   - Ask you to visit YouTube's OAuth page
   - Enter the code to authorize

2. After successful authorization:
   - A `refreshToken` will be displayed in logs
   - Copy and save this token
   - Add it to `application.yml` to skip the flow on restart:

```yaml
plugins:
  youtube:
    oauth:
      enabled: true
      refreshToken: "your_refresh_token_here"
```

**Important Notes:**
- OAuth is needed for age-restricted videos and to bypass bot detection
- The OAuth flow is YouTube's official authentication method
- Use a burner/dedicated account (NOT your personal account)
- The refresh token allows automatic re-authentication
- Look for log level `INFO` on `dev.lavalink.youtube.http.YoutubeOauth2Handler` to see OAuth details
- OAuth may trigger rate limits in high-traffic environments

### Remote Cipher Integration (yt-cipher)
The setup includes integration with **yt-cipher** (https://github.com/kikkia/yt-cipher) for improved YouTube signature decryption:
- **Public Instance**: `https://cipher.kikkia.dev`
- **Rate Limit**: 10 requests/sec (sufficient for up to 1000+ active players)
- **Purpose**: Handles YouTube signature decryption to improve playback reliability
- **Fallback**: If cipher service is unavailable, plugin falls back to local decryption

**IMPORTANT**: You must disable the built-in Lavalink YouTube source to use the plugin:

Configuration in `application.yml`:
```yaml
lavalink:
  server:
    sources:
      youtube: false  # MUST be false to use youtube-source plugin

plugins:
  youtube:
    enabled: true
    remoteCipher:
      url: "https://cipher.kikkia.dev"
      userAgent: "JackyBot"
```

If `youtube: true` is set in sources, Lavalink will use the old built-in source (lavaplayer) which doesn't support remote cipher or OAuth.

### Supported Search Prefixes
- `ytsearch:` - YouTube search (default for !play)
- `ytmsearch:` - YouTube Music search (used by !ytmusic)
- Direct YouTube URLs - Automatically detected

### Client Configuration
The plugin uses multiple YouTube clients for reliability:
1. **MUSIC** - YouTube Music client (best for music)
2. **ANDROID_TESTSUITE** - Android client (good fallback)
3. **WEB** - Web client (standard fallback)
4. **TVHTML5EMBEDDED** - TV client (additional fallback)

If one client fails, Lavalink automatically tries the next one.

### HTTP Timeouts
Extended timeouts are configured to handle cipher service latency:
- Connect timeout: 10 seconds
- Connection request timeout: 10 seconds
- Socket timeout: 10 seconds

## Troubleshooting

1. **Lavalink Connection Failed**: Check if Lavalink is running on the correct port
2. **No Audio**: Ensure Lavalink has internet access for fetching streams
3. **High CPU**: Lavalink may need more resources; consider upgrading VPS
4. **YouTube Playback Issues**: 
   - Verify `youtube-plugin.jar` is in the `plugins/` directory
   - Check `application.yml` has correct plugin configuration
   - Restart Lavalink server after configuration changes
5. **Age-Restricted Video Errors**:
   - Enable OAuth in `application.yml` (see YouTube OAuth section)
   - Complete the OAuth flow when Lavalink starts for the first time
   - Save the `refreshToken` from logs and add it to `application.yml`
   - Check Lavalink logs for OAuth errors or authentication issues
   - Make sure log level for `dev.lavalink.youtube.http.YoutubeOauth2Handler` is set to INFO
6. **Rate Limiting**: If experiencing YouTube rate limits, the multiple client fallback should help automatically
7. **Cipher Service Issues**:
   - Public cipher instance (`cipher.kikkia.dev`) has 10 req/sec rate limit
   - Plugin will fall back to local decryption if cipher service is down
   - For high-traffic bots (1000+ concurrent players), consider self-hosting yt-cipher
   - Check Lavalink logs for cipher-related errors
8. **Timeout Errors**: If getting read timeout errors, the timeouts are already configured to 10 seconds. You can increase them further in `application.yml` if needed
9. **OAuth Flow Issues**:
   - Watch Lavalink terminal/logs on first startup for OAuth instructions
   - You'll see a code and URL to visit YouTube's authorization page
   - Enter the code on the YouTube page to complete authorization
   - Look for the `refreshToken` in the logs after successful authorization
   - If you don't see OAuth prompts, check that `oauth.enabled: true` is set

## Migration Notes

The wavelink version maintains similar command syntax but offers better stability for 24/7 operation. All lyrics and control functionality is preserved.
