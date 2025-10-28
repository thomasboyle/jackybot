#!/bin/bash

# Load environment variables from .env file
if [ -f .env ]; then
    echo "Loading environment variables from .env..."
    set -a
    source .env
    set +a
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

echo "Starting Lavalink..."
java -jar Lavalink.jar
