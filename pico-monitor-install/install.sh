#!/bin/bash

echo "Installing Pico System Monitor..."

# Check if script is run as root
if [ "$EUID" -ne 0 ]; then 
    echo "Please run as root"
    exit 1
fi

# Set up directories
INSTALL_DIR="/opt/pico-monitor"
SERVICE_NAME="pico-monitor"

# Create directories
echo "Creating directories..."
mkdir -p $INSTALL_DIR

# Install system packages
echo "Installing system packages..."
apt update
apt install -y python3-pip python3-venv bluetooth bluez radeontop

# Create virtual environment
echo "Setting up Python virtual environment..."
python3 -m venv $INSTALL_DIR/venv
source $INSTALL_DIR/venv/bin/activate

# Install Python requirements
echo "Installing Python packages..."
$INSTALL_DIR/venv/bin/pip3 install --upgrade pip
$INSTALL_DIR/venv/bin/pip3 install bleak psutil asyncio

# Copy the monitor script
echo "Installing monitor script..."
cp pico_monitor.py $INSTALL_DIR/
chmod +x $INSTALL_DIR/pico_monitor.py

# Add user to required groups
usermod -a -G bluetooth $SUDO_USER
usermod -a -G dialout $SUDO_USER

# Set permissions
echo "Setting permissions..."
chown -R $SUDO_USER:$SUDO_USER $INSTALL_DIR
chmod 755 $INSTALL_DIR

# Create systemd service
echo "Creating systemd service..."
cat > /etc/systemd/system/$SERVICE_NAME.service << EOL
[Unit]
Description=Pico System Monitor
After=bluetooth.service network.target
Requires=bluetooth.service

[Service]
Type=simple
Environment=PYTHONUNBUFFERED=1
Environment=BLEAK_LOGGING=1
Environment=DISPLAY=:0
ExecStartPre=/bin/sleep 10
ExecStart=$INSTALL_DIR/venv/bin/python3 $INSTALL_DIR/pico_monitor.py
WorkingDirectory=$INSTALL_DIR
User=$SUDO_USER
Group=bluetooth
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
EOL

# Reload systemd and enable service
echo "Enabling and starting service..."
systemctl daemon-reload
systemctl enable $SERVICE_NAME
systemctl restart $SERVICE_NAME

# Show status
echo "Installation complete!"
echo "To check status: systemctl status $SERVICE_NAME"
echo "To view logs: journalctl -u $SERVICE_NAME -f"
echo "Service should start automatically after reboot"

# Add user to groups without requiring logout
newgrp bluetooth
