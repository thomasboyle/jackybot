# Wavelink Music Bot Setup

This guide explains how to set up the new wavelink-based music cog for VPS deployment.

## Prerequisites

- Java 11 or higher installed on your VPS
- The `music_wavelink.py` cog (already created)

## Step 1: Install Lavalink

Lavalink is required for wavelink to work. Run the provided setup script:

```bash
./lavalink_setup.sh
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

For production, run Lavalink as a background service:

```bash
# Using screen
screen -S lavalink
java -jar Lavalink.jar

# Detach with Ctrl+A, D

# Or using systemd (create /etc/systemd/system/lavalink.service)
[Unit]
Description=Lavalink
After=network.target

[Service]
Type=simple
User=youruser
WorkingDirectory=/path/to/lavalink
ExecStart=/usr/bin/java -jar Lavalink.jar
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
```

## Features

The wavelink version includes:
- **Better Performance**: Distributed audio processing
- **Built-in Seeking**: Native seek support
- **Automatic Queue**: Better queue management
- **Lyrics Support**: Same lyrics functionality as before
- **Control Buttons**: Pause, skip, seek, loop, lyrics
- **Playlist Support**: Automatic playlist detection
- **VPS Optimized**: Better resource management

## Commands

- `!play <query>` - Play music from YouTube, SoundCloud, etc.
- `!queue` - Show current queue
- `!np` or `!nowplaying` - Show currently playing track

## Troubleshooting

1. **Lavalink Connection Failed**: Check if Lavalink is running on the correct port
2. **No Audio**: Ensure Lavalink has internet access for fetching streams
3. **High CPU**: Lavalink may need more resources; consider upgrading VPS

## Migration Notes

The wavelink version maintains similar command syntax but offers better stability for 24/7 operation. All lyrics and control functionality is preserved.
