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

# Detect the operating system
if [ -f /etc/os-release ]; then
    . /etc/os-release
    OS=$ID
else
    echo "Unsupported operating system"
    exit 1
fi

# Install system packages based on the operating system
echo "Installing system packages..."
if [ "$OS" == "ubuntu" ] || [ "$OS" == "debian" ]; then
    apt update
    apt install -y python3-pip python3-venv bluetooth bluez radeontop
elif [ "$OS" == "steamos" ]; then
    pacman -Syu --noconfirm
    pacman -S --noconfirm python python-pip python-virtualenv bluez bluez-utils radeontop
else
    echo "Unsupported operating system: $OS"
    exit 1
fi

# Create virtual environment
echo "Setting up Python virtual environment..."
if [ "$OS" == "ubuntu" ] || [ "$OS" == "debian" ]; then
    python3 -m venv $INSTALL_DIR/venv
    source $INSTALL_DIR/venv/bin/activate
    PIP_CMD="$INSTALL_DIR/venv/bin/pip3"
    PYTHON_CMD="$INSTALL_DIR/venv/bin/python3"
elif [ "$OS" == "steamos" ]; then
    python -m venv $INSTALL_DIR/venv
    source $INSTALL_DIR/venv/bin/activate
    PIP_CMD="$INSTALL_DIR/venv/bin/pip"
    PYTHON_CMD="$INSTALL_DIR/venv/bin/python"
fi

# Install Python requirements
echo "Installing Python packages..."
$PIP_CMD install --upgrade pip
$PIP_CMD install bleak psutil asyncio

# Copy the monitor script
echo "Installing monitor script..."
cp pico_monitor.py $INSTALL_DIR/
chmod +x $INSTALL_DIR/pico_monitor.py

# Create bluetooth group if it doesn't exist
if ! grep -q "^bluetooth:" /etc/group; then
    groupadd bluetooth
fi

# Add user to required groups
usermod -a -G bluetooth $SUDO_USER
if [ "$OS" == "ubuntu" ] || [ "$OS" == "debian" ]; then
    usermod -a -G dialout $SUDO_USER
elif [ "$OS" == "steamos" ]; then
    usermod -a -G uucp $SUDO_USER
fi

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
ExecStart=$PYTHON_CMD $INSTALL_DIR/pico_monitor.py
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
