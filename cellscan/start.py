#!/usr/bin/env/python3

import logging
import argparse
import time
import queue
import json

from cellscan.panel import PanelThread
from cellscan.radio import RadioThread
from cellscan.gnss import GnssThread
from cellscan.data import saveCellSite
from cellscan.upload import UploadThread

def __main__():
    # Note: The Telit modem in use (LE910C1) exposes multiple USB serial devices for different purposes,
    # and the composition is configurable (see the LE9xx AT reference manual). Here is what seems to be
    # the case for the default configuration:
    # ttyUSB0 (???)  ttyUSB1 (NMEA)  ttyUSB2 (???)  ttyUSB3 (Hayes AT)  ttyUSB4 (???)
    config = {
        'ATtty': '/dev/ttyUSB3',
        'NMEAtty': '/dev/ttyUSB1',
        'server': '8.8.8.8'
    }
    runner = Runner(config)
    runner.setup()
    while True:
        runner.step()

class Runner(object):
    def __init__(self, config):
        parser = argparse.ArgumentParser(description='CellScan service.')
        parser.add_argument('-l', '--log', dest='logLevel', choices=['DEBUG', 'INFO', 'WARNING', 'ERROR', 'CRITICAL'], default='INFO', help='Set the logging level')
        parser.add_argument('-o', '--out', dest='out', default='output.json', help='Output file')
        self.args = parser.parse_args()

        logging.basicConfig(level=getattr(logging, args.logLevel))
        self.log = logging.getLogger("cellscan")
        self.log.info("CellScan starting up.")

        self.locn = None
        self.config = config
    
    def setup(self):
        self.tm = ThreadManager(self.config)
        self.tm.startPanel()
        self.tm.startRadio()
        self.tm.startGnss()

    # And now we just go into event loop
    def step(self):
        event = self.tm.q.get(block=True)
        self.log.debug(f"Received {event[0]}: {event[1]}")

        # Handle events which can occur
        if event[0] == 'LocationFix':
            self.handleLocationFix(event)
        elif event[0] == "NetworkData":
            self.handleNetworkData(event)
        elif event[0] == "PanelEvent":
            self.handlePanelEvent(event)
    
    def handleLocationFix(self, event):
            # Stash the new most recent fix for future use
            self.locn = event[1]
    
    def handleNetworkData(self, event):
            # New network scan result
            if self.locn != None:
                self.tm.panel.setLed('once')
                sites = event[1]
                for bsn in sites:
                    bsn['lat'] = self.locn['lat']
                    bsn['lon'] = self.locn['lon']
                    bsn['alt'] = self.locn['alt']
                    saveCellSite(bsn)
    
    def handlePanelEvent(self, event):
            # User pressed a button
            if event[1]['type'] == 'CtlButton' and event[1]['time'] < 1:
                self.uploadData()
    
    def uploadData(self):
        # Stop the scanning, this will block until it's closed out
        self.log.debug("Stopping radio to upload data")
        self.tm.stopRadio()
        self.log.info("Starting data upload")
        self.tm.panel.setLed("blink")
        upload = UploadThread(self.tm.q, self.config['server'])
        upload.run()
        upload.join()
        self.tm.panel.setLed("off")
        self.tm.startRadio()

class ThreadManager(object):
    """This is just a dumb wrapper to save some typing on threads we need to start/stop repeatedly"""
    def __init__(self, config):
        self.q = queue.Queue()
        self.radio = None
        self.gnss = None
        self.panel = None
        self.upload = None
        self.config = config
    
    def startPanel(self):
        self.panel = PanelThread(self.q)
        self.panel.start()
    
    def startRadio(self):
        self.radio = RadioThread(self.q, self.config['ATtty'])
        self.radio.start()
    
    def stopRadio(self):
        if self.radio != None and self.radio.is_alive():
            self.radio.stop()
            self.radio.join()

    def startGnss(self):
        self.gnss = GnssThread(self.q, self.config['NMEAtty'])
        self.gnss.start()
    
    def checkThreads(self):
        if not self.panel.is_alive():
            log.warning("Panel thread died, restarting")
            self.startPanel()
        if not self.radio.is_alive():
            log.warning("Radio thread died, restarting")
            self.startRadio()
        if not self.gnss.is_alive():
            log.warning("Gnss thread died, restarting")
            self.startGnss()


if __name__ == "__main__":
    __main__()
