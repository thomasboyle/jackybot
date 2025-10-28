#!/bin/bash

# Lavalink Setup for VPS
# This script downloads and configures Lavalink for use with the wavelink music cog

echo "Setting up Lavalink..."

# Check if Java is installed
if ! command -v java &> /dev/null; then
    echo "Java is not installed. Please install Java 11 or higher first."
    exit 1
fi

# Check Java version (minimum 11)
JAVA_VERSION=$(java -version 2>&1 | awk -F '"' '/version/ {print $2}' | cut -d'.' -f1)
if [ "$JAVA_VERSION" -lt 11 ]; then
    echo "Java version 11 or higher is required. Current version: $JAVA_VERSION"
    exit 1
fi

echo "Java version $JAVA_VERSION detected."

# Download Lavalink JAR
echo "Downloading Lavalink JAR..."
if command -v wget &> /dev/null; then
    wget -q https://github.com/lavalink-devs/Lavalink/releases/latest/download/Lavalink.jar
elif command -v curl &> /dev/null; then
    curl -L -o Lavalink.jar https://github.com/lavalink-devs/Lavalink/releases/latest/download/Lavalink.jar
else
    echo "Neither wget nor curl is available. Please install one of them."
    exit 1
fi

if [ ! -f "Lavalink.jar" ]; then
    echo "Failed to download Lavalink.jar"
    exit 1
fi

echo "Lavalink.jar downloaded successfully."

# Create application.yml configuration
echo "Creating application.yml configuration..."
cat > application.yml << 'EOF'
server:
  port: 2333
  address: 0.0.0.0

lavalink:
  server:
    password: 'youshallnotpass'
    sources:
      youtube: true
      bandcamp: true
      soundcloud: true
      twitch: true
      vimeo: true
      mixer: true
      http: true
      local: false
    filters:
      volume: true
      equalizer: true
      karaoke: true
      timescale: true
      tremolo: true
      vibrato: true
      distortion: true
      rotation: true
      channelMix: true
      lowPass: true
    bufferDurationMs: 400
    frameBufferDurationMs: 5000
    opusEncodingQuality: 10
    resamplingQuality: LOW
    trackStuckThresholdMs: 10000
    useSeekGhosting: true
    youtubePlaylistLoadLimit: 6
    playerUpdateIntervalMs: 5
    youtubeSearchEnabled: true
    soundcloudSearchEnabled: true
    gc-warnings: true

metrics:
  prometheus:
    enabled: false
    endpoint: /metrics

sentry:
  dsn: ''

logging:
  level:
    root: INFO
    lavalink: INFO

  request:
    enabled: true
    includeClientInfo: true
    includeHeaders: false
    includeQueryString: true
    includePayload: true
    maxPayloadLength: 10000
EOF

echo "Configuration created."

# Create a simple startup script
cat > start_lavalink.sh << 'EOF'
#!/bin/bash
echo "Starting Lavalink..."
java -jar Lavalink.jar
EOF

chmod +x start_lavalink.sh

# Create systemd service file
cat > lavalink.service << 'EOF'
[Unit]
Description=Lavalink
After=network.target

[Service]
Type=simple
User=root
WorkingDirectory=/root
ExecStart=/usr/bin/java -jar Lavalink.jar
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
EOF

echo ""
echo "Lavalink setup complete!"
echo ""
echo "To start Lavalink:"
echo "1. Run: ./start_lavalink.sh"
echo "2. Or install as service: sudo cp lavalink.service /etc/systemd/system/ && sudo systemctl enable lavalink && sudo systemctl start lavalink"
echo ""
echo "Make sure your bot's .env file has:"
echo "LAVALINK_HOST=127.0.0.1"
echo "LAVALINK_PORT=2333"
echo "LAVALINK_PASSWORD=youshallnotpass"
echo ""
echo "Files created:"
echo "- Lavalink.jar (main application)"
echo "- application.yml (configuration)"
echo "- start_lavalink.sh (startup script)"
echo "- lavalink.service (systemd service)"
