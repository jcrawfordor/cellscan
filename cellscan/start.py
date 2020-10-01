#!/usr/bin/env/python3

import logging
import argparse
import time
import queue
import json

from cellscan.panel import PanelThread
from cellscan.radio import RadioThread
from cellscan.gnss import GnssThread

def __main__():
    parser = argparse.ArgumentParser(description='CellScan service.')
    parser.add_argument('-l', '--log', dest='logLevel', choices=['DEBUG', 'INFO', 'WARNING', 'ERROR', 'CRITICAL'], default='INFO', help='Set the logging level')
    parser.add_argument('-o', '--out', dest='out', default='output.json', help='Output file')
    args = parser.parse_args()

    logging.basicConfig(level=getattr(logging, args.logLevel))
    log = logging.getLogger("cellscan")
    log.info("CellScan starting up.")

    # We will use this queue to receive messages from threads
    q = queue.Queue()

    # Set up panel
    panel = PanelThread(q)
    panel.start()

    # Set up radio
    # Note: The Telit modem in use (LE910C1) exposes multiple USB serial devices for different purposes,
    # and the composition is configurable (see the LE9xx AT reference manual). Here is what seems to be
    # the case for the default configuration:
    # ttyUSB0 (???)  ttyUSB1 (NMEA)  ttyUSB2 (???)  ttyUSB3 (Hayes AT)  ttyUSB4 (???)
    radio = RadioThread(q, '/dev/ttyUSB3')
    radio.start()

    # Set up location monitoring
    gnss = GnssThread(q, '/dev/ttyUSB1')
    gnss.start()

    # Set up our output
    outfile = open(args.out, 'w')

    # And now we just go into event loop
    log.info("Startup complete.")
    locn = None
    while True:
        event = q.get(block=True)
        log.debug(f"Received {event[0]}: {event[1]}")

        # Handle events which can occur
        if event[0] == 'LocationFix':
            # New location fix from GPS
            # Turn on the LED if we just got the first good fix
            if locn == None:
                panel.setLed('on')
            # Stash the new most recent event for future use
            locn = event[1]

        elif event[0] == "NetworkData":
            # New network scan result
            if locn != None:
                sites = event[1]
                for bsn in sites:
                    bsn['lat'] = locn['lat']
                    bsn['lon'] = locn['lon']
                    bsn['alt'] = locn['alt']
                    outfile.write(json.dumps(bsn))
                    outfile.write("\n")

        elif event[0] == "PanelEvent":
            # User pressed a button
            if event[1]['type'] == 'CtlButton' and event[1]['time'] < 1:
                # Upload results
                # First stop the radio since we are going to use it
                radio.stop()
                radio.join()
                
                radio = RadioThread(q, '/dev/ttyUSB3')
                radio.start()
            pass

if __name__ == "__main__":
    __main__()
