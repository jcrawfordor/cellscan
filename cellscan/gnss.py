import threading
import time
import logging
import serial
import pynmea2

log = logging.getLogger('gnss')

class GnssThread(threading.Thread):
    def __init__(self, q, NMEAPort):
        threading.Thread.__init__(self)
        self.q = q
        self.NMEAPort = NMEAPort
        self.live = True
        self.nmea = None

    def run(self):
        log.debug(f"Listening for NMEA on {self.NMEAPort}...")
        self.nmea = serial.Serial(self.NMEAPort)
        
        while self.live:
            line = self.nmea.readline().decode('ASCII')
            if line.startswith("$GPGGA"):
                log.debug(f"sentence: {line.strip()}")
                sentence = pynmea2.parse(line)
                if sentence.gps_qual != 0:
                    # Only send on valid fixes
                    self.q.put(['LocationFix', {'lat': sentence.latitude, 'lon': sentence.longitude, 'alt': sentence.altitude}])

    def stop(self):
        self.live = False