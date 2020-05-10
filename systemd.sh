#!/usr/bin/env bash

exec=`realpath server.py`
if [ ! -f $exec ]; then
        echo "Not found path: $exec"
        exit
fi

sudo echo "[Unit]
Description=tracking
After=network-online.target

[Service]
Type=simple
ExecStart=$exec
Restart=always
RestartSec=60

[Install]
WantedBy=multi-user.target" > /etc/systemd/system/tracking.service

sudo chmod 644 /etc/systemd/system/tracking.service

systemctl daemon-reload
sudo systemctl enable tracking.service
sudo systemctl restart tracking.service
sudo systemctl status tracking.service
