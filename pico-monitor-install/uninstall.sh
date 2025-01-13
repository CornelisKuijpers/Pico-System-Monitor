#!/bin/bash

# uninstall.sh
echo "Uninstalling Pico System Monitor..."

# Check if script is run as root
if [ "$EUID" -ne 0 ]; then 
    echo "Please run as root"
    exit 1
fi

SERVICE_NAME="pico-monitor"
INSTALL_DIR="/opt/pico-monitor"
CONFIG_DIR="/etc/pico-monitor"

# Stop and disable service
echo "Stopping and disabling service..."
systemctl stop $SERVICE_NAME
systemctl disable $SERVICE_NAME

# Remove service file
echo "Removing service file..."
rm -f /etc/systemd/system/$SERVICE_NAME.service

# Remove directories
echo "Removing installed files..."
rm -rf $INSTALL_DIR
rm -rf $CONFIG_DIR

# Reload systemd
systemctl daemon-reload

echo "Uninstallation complete!"
