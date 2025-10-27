@echo off
color 06
echo Starting JackyBot...
echo.

REM Set Hugging Face token via environment variable or .env file
REM set HF_TOKEN=your_token_here

echo Upgrading pip...
python.exe -m pip install --upgrade pip
echo.
echo Upgrading yt-dlp...
pip install --upgrade --no-cache-dir yt-dlp
echo.
echo Upgrading discord.py...
pip install --upgrade --no-cache-dir discord.py
echo.
echo Launching bot...
python bot.py
pause
