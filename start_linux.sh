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

# Check YouTube authentication for music bot
echo "Checking YouTube authentication..."
if [ -f "assets/cookies.txt" ]; then
    echo "YouTube cookies found - Full music functionality available"
else
    echo "Warning: No YouTube cookies found."
    echo "Music bot will have limited functionality."
    echo "Run 'python setup_youtube_auth.py' locally to extract browser cookies."
fi

echo "Launching bot..."
uv run python3 bot.py

# Reset terminal color
echo -e "\033[0m"
