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
