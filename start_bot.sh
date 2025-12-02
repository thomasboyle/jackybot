#!/bin/bash

# Set terminal color to yellow
echo "Starting JackyBot..."
echo ""

# Load environment variables from .env file if it exists
if [ -f ".env" ]; then
    echo "Loading environment variables from .env file..."
    export $(grep -v '^#' .env | xargs)
else
    echo "Warning: .env file not found. Please create one with your API keys."
    echo "See env.example for the required format."
fi

# Check for required environment variables
if [ -z "$DISCORD_BOT_TOKEN" ]; then
    echo "Error: DISCORD_BOT_TOKEN environment variable not set."
    echo "Please set it in your .env file or as an environment variable."
    exit 1
fi

if [ -z "$GROQ_API_KEY" ]; then
    echo "Error: GROQ_API_KEY environment variable not set."
    echo "Please set it in your .env file or as an environment variable."
    exit 1
fi

echo "Fetching latest YouTube plugin version..."

YOUTUBE_PLUGIN_VERSION=$(curl -s "https://maven.lavalink.dev/releases/dev/lavalink/youtube/youtube-plugin/maven-metadata.xml" | grep -oP '<latest>\K[^<]+' || echo "1.19.0")

if [ -z "$YOUTUBE_PLUGIN_VERSION" ]; then
    echo "Failed to fetch latest version, using fallback: 1.19.0"
    YOUTUBE_PLUGIN_VERSION="1.19.0"
else
    echo "Latest YouTube plugin version: $YOUTUBE_PLUGIN_VERSION"
fi

LAVASRC_VERSION=$(curl -s "https://maven.lavalink.dev/releases/com/github/topi314/lavasrc/lavasrc-plugin/maven-metadata.xml" | grep -oP '<latest>\K[^<]+' || echo "4.8.1")

if [ -z "$LAVASRC_VERSION" ]; then
    echo "Failed to fetch latest LavaSrc version, using fallback: 4.8.1"
    LAVASRC_VERSION="4.8.1"
else
    echo "Latest LavaSrc plugin version: $LAVASRC_VERSION"
fi

echo "Updating application.yml with latest plugin versions..."

sed -i "s|dev.lavalink.youtube:youtube-plugin:[0-9.]*|dev.lavalink.youtube:youtube-plugin:$YOUTUBE_PLUGIN_VERSION|g" application.yml
sed -i "s|com.github.topi314.lavasrc:lavasrc-plugin:[0-9.]*|com.github.topi314.lavasrc:lavasrc-plugin:$LAVASRC_VERSION|g" application.yml

echo "Starting Lavalink in background..."
java -jar Lavalink.jar &
LAVALINK_PID=$!

echo "Waiting 10 seconds for Lavalink to start..."
sleep 10

echo "Launching bot..."
uv run python3 bot.py &
BOT_PID=$!

# Function to handle shutdown
cleanup() {
    echo ""
    echo "Shutting down services..."
    if kill -0 $BOT_PID 2>/dev/null; then
        kill $BOT_PID
        echo "Bot stopped."
    fi
    if kill -0 $LAVALINK_PID 2>/dev/null; then
        kill $LAVALINK_PID
        echo "Lavalink stopped."
    fi
    exit 0
}

# Set up signal handlers
trap cleanup SIGINT SIGTERM

echo "JackyBot and Lavalink are running. Press Ctrl+C to stop."

# Wait for either process to exit
wait $BOT_PID $LAVALINK_PID

# Reset terminal color
echo -e "\033[0m"
