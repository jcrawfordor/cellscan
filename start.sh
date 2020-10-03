#!/bin/bash
cd /home/pi/cellscan
source /etc/profile
sleep 30
mmcli -L
pipenv run python -m cellscan.start -l DEBUG
