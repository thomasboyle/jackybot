@echo off
REM Lavalink Setup for Windows
REM This script downloads and configures Lavalink for use with the wavelink music cog

echo Setting up Lavalink...

REM Check if Java is installed
java -version >nul 2>&1
if %errorlevel% neq 0 (
    echo Java is not installed. Please install Java 11 or higher first.
    pause
    exit /b 1
)

REM Download Lavalink JAR
echo Downloading Lavalink JAR...
if exist Lavalink.jar (
    echo Lavalink.jar already exists, skipping download.
) else (
    powershell -Command "Invoke-WebRequest -Uri 'https://github.com/lavalink-devs/Lavalink/releases/latest/download/Lavalink.jar' -OutFile 'Lavalink.jar'"
    if not exist Lavalink.jar (
        echo Failed to download Lavalink.jar
        pause
        exit /b 1
    )
)

echo Lavalink.jar downloaded successfully.

REM Create application.yml configuration
echo Creating application.yml configuration...
(
echo server:
echo   port: 2333
echo   address: 0.0.0.0
echo.
echo lavalink:
echo   server:
echo     password: 'youshallnotpass'
echo     sources:
echo       youtube: true
echo       bandcamp: true
echo       soundcloud: true
echo       twitch: true
echo       vimeo: true
echo       mixer: true
echo       http: true
echo       local: false
echo     filters:
echo       volume: true
echo       equalizer: true
echo       karaoke: true
echo       timescale: true
echo       tremolo: true
echo       vibrato: true
echo       distortion: true
echo       rotation: true
echo       channelMix: true
echo       lowPass: true
echo     bufferDurationMs: 400
echo     frameBufferDurationMs: 5000
echo     opusEncodingQuality: 10
echo     resamplingQuality: LOW
echo     trackStuckThresholdMs: 10000
echo     useSeekGhosting: true
echo     youtubePlaylistLoadLimit: 6
echo     playerUpdateIntervalMs: 5
echo     youtubeSearchEnabled: true
echo     soundcloudSearchEnabled: true
echo     gc-warnings: true
echo.
echo metrics:
echo   prometheus:
echo     enabled: false
echo     endpoint: /metrics
echo.
echo sentry:
echo   dsn: ''
echo.
echo logging:
echo   level:
echo     root: INFO
echo     lavalink: INFO
echo.
echo   request:
echo     enabled: true
echo     includeClientInfo: true
echo     includeHeaders: false
echo     includeQueryString: true
echo     includePayload: true
echo     maxPayloadLength: 10000
) > application.yml

REM Create startup script
echo Creating startup scripts...
(
echo @echo off
echo echo Starting Lavalink...
echo java -jar Lavalink.jar
echo pause
) > start_lavalink.bat

echo.
echo Lavalink setup complete!
echo.
echo To start Lavalink:
echo 1. Run: start_lavalink.bat
echo.
echo Make sure your bot's .env file has:
echo LAVALINK_HOST=127.0.0.1
echo LAVALINK_PORT=2333
echo LAVALINK_PASSWORD=youshallnotpass
echo.
echo Files created:
echo - Lavalink.jar (main application)
echo - application.yml (configuration)
echo - start_lavalink.bat (startup script)
echo.
pause
