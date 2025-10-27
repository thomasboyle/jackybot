#!/bin/bash

# Set terminal color to yellow
echo -e "\033[0;33m"
echo "Starting JackyBot..."
echo ""

# Set Hugging Face token via environment variable or .env file
# export HF_TOKEN=your_token_here

echo "Ensuring pip is available..."
python3 -m ensurepip --upgrade || python3 -c "import sys; print('pip installation check complete')"
echo ""
echo "Installing/upgrading dependencies..."
python3 -m pip install --upgrade pip
python3 -m pip install --upgrade -r requirements.txt
echo ""
echo "Launching bot..."
python3 bot.py

# Reset terminal color
echo -e "\033[0m"
