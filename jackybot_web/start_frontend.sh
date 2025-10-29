#!/bin/bash
echo "Starting JackyBot Web Interface Frontend on https://jackybot.xyz..."
cd frontend

if [ ! -d "ssl" ]; then
    echo "Warning: SSL directory not found. Creating self-signed certificate..."
    mkdir -p ssl
    openssl req -x509 -newkey rsa:4096 -nodes -keyout ssl/key.pem -out ssl/cert.pem -days 365 -subj "/CN=jackybot.xyz" 2>/dev/null || {
        echo "Error: Failed to generate SSL certificate. Make sure OpenSSL is installed."
        echo "Falling back to HTTP mode..."
        npm run dev
        exit 1
    }
fi

npm run dev

