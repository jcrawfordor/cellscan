#!/bin/bash

# TODO: eliminate this file entirely, it was a lazy hack

cd /home/pi/cellscan
source /etc/profile
sleep 30 # Seems to take nearly this long for ModemManager to reliable discover the modem
mmcli -L
pipenv run python -m cellscan.start -l DEBUG
