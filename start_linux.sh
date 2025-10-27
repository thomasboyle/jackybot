#!/bin/bash

# Set terminal color to yellow
echo -e "\033[0;33m"
echo "Starting JackyBot..."
echo ""

# Set Hugging Face token via environment variable or .env file
# export HF_TOKEN=your_token_here

echo "Upgrading pip..."
python3 -m pip install --upgrade pip
echo ""
echo "Upgrading yt-dlp..."
pip install --upgrade --no-cache-dir yt-dlp
echo ""
echo "Upgrading discord.py..."
pip install --upgrade --no-cache-dir discord.py
echo ""
echo "Launching bot..."
python3 bot.py

# Reset terminal color
echo -e "\033[0m"
