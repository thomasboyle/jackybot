#!/bin/bash

set -e

echo "========================================="
echo "JackyBot Web UI - VPS Setup Script"
echo "========================================="
echo ""

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
BACKEND_DIR="$SCRIPT_DIR/backend"
FRONTEND_DIR="$SCRIPT_DIR/frontend"

echo "Project root: $PROJECT_ROOT"
echo "Backend dir: $BACKEND_DIR"
echo "Frontend dir: $FRONTEND_DIR"
echo ""

check_command() {
    if ! command -v $1 &> /dev/null; then
        return 1
    fi
    return 0
}

install_system_dependencies() {
    echo ">>> Installing system dependencies..."
    
    if check_command apt-get; then
        sudo apt-get update
        sudo apt-get install -y python3 python3-pip python3-venv curl
        
        if ! check_command node; then
            echo ">>> Installing Node.js via NodeSource..."
            curl -fsSL https://deb.nodesource.com/setup_20.x | sudo -E bash -
            sudo apt-get install -y nodejs
        fi
        
        sudo apt-get install -y nginx certbot python3-certbot-nginx
    elif check_command yum; then
        sudo yum install -y python3 python3-pip curl
        if ! check_command node; then
            echo ">>> Installing Node.js via NodeSource..."
            curl -fsSL https://rpm.nodesource.com/setup_20.x | sudo bash -
            sudo yum install -y nodejs
        fi
        sudo yum install -y nginx certbot python3-certbot-nginx
    elif check_command dnf; then
        sudo dnf install -y python3 python3-pip curl
        if ! check_command node; then
            echo ">>> Installing Node.js via NodeSource..."
            curl -fsSL https://rpm.nodesource.com/setup_20.x | sudo bash -
            sudo dnf install -y nodejs
        fi
        sudo dnf install -y nginx certbot python3-certbot-nginx
    else
        echo "Warning: Could not detect package manager. Please install: python3, pip, nodejs, npm, nginx manually"
    fi
    
    echo ">>> System dependencies installed"
    echo ">>> Python version: $(python3 --version)"
    echo ">>> Node.js version: $(node --version)"
    echo ">>> npm version: $(npm --version)"
    echo ""
}

setup_python_venv() {
    echo ">>> Setting up Python virtual environment..."
    
    if [ ! -d "$BACKEND_DIR/venv" ]; then
        python3 -m venv "$BACKEND_DIR/venv"
    fi
    
    source "$BACKEND_DIR/venv/bin/activate"
    pip install --upgrade pip
    pip install -r "$BACKEND_DIR/requirements.txt"
    
    echo ">>> Python virtual environment ready"
    echo ""
}

setup_nodejs() {
    echo ">>> Setting up Node.js dependencies..."
    
    cd "$FRONTEND_DIR"
    
    if [ ! -d "node_modules" ]; then
        echo ">>> Installing npm packages..."
        npm install
    else
        echo ">>> node_modules exists, skipping install..."
    fi
    
    echo ">>> Building frontend for production..."
    npm run build
    
    if [ ! -d "dist" ]; then
        echo "ERROR: Frontend build failed! dist directory not found."
        exit 1
    fi
    
    echo ">>> Frontend built successfully"
    cd "$SCRIPT_DIR"
    echo ""
}

configure_environment() {
    echo ">>> Configuring environment variables..."
    
    ENV_FILE="$PROJECT_ROOT/.env"
    
    if [ ! -f "$ENV_FILE" ]; then
        echo "Creating .env file from template..."
        cp "$SCRIPT_DIR/env_example.txt" "$ENV_FILE"
        
        SECRET_KEY=$(openssl rand -hex 32)
        sed -i "s/FLASK_SECRET_KEY=.*/FLASK_SECRET_KEY=$SECRET_KEY/" "$ENV_FILE"
        echo ">>> Generated FLASK_SECRET_KEY automatically"
    fi
    
    echo ""
    echo "========================================="
    echo "IMPORTANT: Configure these variables in"
    echo "$ENV_FILE"
    echo "========================================="
    echo ""
    echo "Required variables:"
    echo "  DISCORD_CLIENT_ID=your_client_id"
    echo "  DISCORD_CLIENT_SECRET=your_client_secret"
    echo "  DISCORD_REDIRECT_URI=https://your-domain.com/auth/callback"
    echo "  WEB_INTERFACE_URL=https://your-domain.com"
    echo ""
    echo "Optional (already set with defaults):"
    echo "  FLASK_SECRET_KEY (auto-generated if not set)"
    echo "  WEBSOCKET_PORT=5000"
    echo ""
    
    read -p "Press Enter after you've configured .env file to continue..."
    echo ""
}

create_systemd_service() {
    echo ">>> Creating systemd service..."
    
    read -p "Enter your VPS domain name (e.g., bot.example.com): " DOMAIN_NAME
    read -p "Enter your VPS user (usually your username): " VPS_USER
    
    if [ -z "$DOMAIN_NAME" ]; then
        echo "Warning: No domain provided. Skipping systemd service creation."
        return
    fi
    
    SERVICE_FILE="/etc/systemd/system/jackybot-web-backend.service"
    
    sudo tee "$SERVICE_FILE" > /dev/null <<EOF
[Unit]
Description=JackyBot Web Interface Backend
After=network.target

[Service]
Type=simple
User=$VPS_USER
WorkingDirectory=$BACKEND_DIR
Environment="PATH=$BACKEND_DIR/venv/bin"
ExecStart=$BACKEND_DIR/venv/bin/python $BACKEND_DIR/app.py
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
EOF

    sudo systemctl daemon-reload
    sudo systemctl enable jackybot-web-backend.service
    
    echo ">>> Systemd service created: jackybot-web-backend.service"
    echo ">>> Start with: sudo systemctl start jackybot-web-backend"
    echo ""
}

configure_nginx() {
    echo ">>> Configuring Nginx..."
    
    read -p "Enter your domain name (e.g., bot.example.com): " DOMAIN_NAME
    
    if [ -z "$DOMAIN_NAME" ]; then
        echo "Warning: No domain provided. Skipping Nginx configuration."
        return
    fi
    
    NGINX_CONFIG="/etc/nginx/sites-available/jackybot-web"
    
    sudo tee "$NGINX_CONFIG" > /dev/null <<EOF
server {
    listen 80;
    server_name $DOMAIN_NAME;

    client_max_body_size 20M;

    location /api {
        proxy_pass http://127.0.0.1:5000;
        proxy_http_version 1.1;
        proxy_set_header Upgrade \$http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto \$scheme;
        proxy_read_timeout 86400;
    }

    location /auth {
        proxy_pass http://127.0.0.1:5000;
        proxy_http_version 1.1;
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto \$scheme;
    }

    location /socket.io {
        proxy_pass http://127.0.0.1:5000;
        proxy_http_version 1.1;
        proxy_set_header Upgrade \$http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto \$scheme;
        proxy_read_timeout 86400;
    }

    location / {
        root $FRONTEND_DIR/dist;
        try_files \$uri \$uri/ /index.html;
        add_header Cache-Control "no-cache, no-store, must-revalidate";
    }
}
EOF

    sudo ln -sf "$NGINX_CONFIG" /etc/nginx/sites-enabled/jackybot-web
    
    if [ -f /etc/nginx/sites-enabled/default ]; then
        sudo rm /etc/nginx/sites-enabled/default
    fi
    
    sudo nginx -t
    sudo systemctl reload nginx
    
    echo ">>> Nginx configured successfully"
    echo ""
    
    read -p "Do you want to set up SSL with Let's Encrypt? (y/n): " SETUP_SSL
    if [ "$SETUP_SSL" = "y" ] || [ "$SETUP_SSL" = "Y" ]; then
        echo ">>> Setting up SSL certificate..."
        sudo certbot --nginx -d "$DOMAIN_NAME"
        echo ">>> SSL certificate installed"
    fi
    echo ""
}

create_startup_script() {
    echo ">>> Creating startup script..."
    
    STARTUP_SCRIPT="$SCRIPT_DIR/start_services.sh"
    
    cat > "$STARTUP_SCRIPT" <<'EOF'
#!/bin/bash

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BACKEND_DIR="$SCRIPT_DIR/backend"

echo "Starting JackyBot Web Interface services..."

if systemctl is-active --quiet jackybot-web-backend; then
    echo "Backend service is already running"
else
    sudo systemctl start jackybot-web-backend
    echo "Backend service started"
fi

if systemctl is-active --quiet nginx; then
    echo "Nginx is already running"
else
    sudo systemctl start nginx
    echo "Nginx started"
fi

echo ""
echo "Services status:"
sudo systemctl status jackybot-web-backend --no-pager -l | head -5
sudo systemctl status nginx --no-pager -l | head -5
EOF

    chmod +x "$STARTUP_SCRIPT"
    
    echo ">>> Startup script created: $STARTUP_SCRIPT"
    echo ""
}

create_stop_script() {
    echo ">>> Creating stop script..."
    
    STOP_SCRIPT="$SCRIPT_DIR/stop_services.sh"
    
    cat > "$STOP_SCRIPT" <<'EOF'
#!/bin/bash

echo "Stopping JackyBot Web Interface services..."

sudo systemctl stop jackybot-web-backend
echo "Backend service stopped"

echo ""
echo "Services stopped"
EOF

    chmod +x "$STOP_SCRIPT"
    
    echo ">>> Stop script created: $STOP_SCRIPT"
    echo ""
}

print_summary() {
    echo "========================================="
    echo "Setup Complete!"
    echo "========================================="
    echo ""
    echo "Next steps:"
    echo ""
    echo "1. Configure .env file at: $PROJECT_ROOT/.env"
    echo "   - Set DISCORD_CLIENT_ID and DISCORD_CLIENT_SECRET"
    echo "   - Set DISCORD_REDIRECT_URI to: https://your-domain.com/auth/callback"
    echo "   - Set FLASK_SECRET_KEY (generate with: openssl rand -hex 32)"
    echo "   - Set WEB_INTERFACE_URL to: https://your-domain.com"
    echo ""
    echo "2. Update Discord OAuth2 redirect URI in Discord Developer Portal:"
    echo "   https://your-domain.com/auth/callback"
    echo ""
    echo "3. Start services:"
    echo "   sudo systemctl start jackybot-web-backend"
    echo "   sudo systemctl status jackybot-web-backend"
    echo ""
    echo "4. Check logs:"
    echo "   sudo journalctl -u jackybot-web-backend -f"
    echo ""
    echo "5. Access your web interface at: https://your-domain.com"
    echo ""
    echo "Useful commands:"
    echo "  Start:  sudo systemctl start jackybot-web-backend"
    echo "  Stop:   sudo systemctl stop jackybot-web-backend"
    echo "  Status: sudo systemctl status jackybot-web-backend"
    echo "  Logs:   sudo journalctl -u jackybot-web-backend -f"
    echo "  Restart: sudo systemctl restart jackybot-web-backend"
    echo ""
}

main() {
    echo "Starting setup process..."
    echo ""
    
    install_system_dependencies
    setup_python_venv
    setup_nodejs
    configure_environment
    
    read -p "Do you want to set up systemd service? (y/n): " SETUP_SERVICE
    if [ "$SETUP_SERVICE" = "y" ] || [ "$SETUP_SERVICE" = "Y" ]; then
        create_systemd_service
    fi
    
    read -p "Do you want to configure Nginx? (y/n): " SETUP_NGINX
    if [ "$SETUP_NGINX" = "y" ] || [ "$SETUP_NGINX" = "Y" ]; then
        configure_nginx
    fi
    
    create_startup_script
    create_stop_script
    
    print_summary
}

main

