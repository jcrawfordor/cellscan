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
                # Little silly to use PyNMEA2 for just this one thing, but the NMEA sentence format
                # is oddly complicated and this saves doing our own lat/lon format conversions.
                sentence = pynmea2.parse(line)
                # Only send on valid fixes, before gps_qual changes the results are either null or
                # have very high error.
                if sentence.gps_qual != 0:
                    self.q.put(['LocationFix', {'lat': sentence.latitude, 'lon': sentence.longitude, 'alt': sentence.altitude}])

    def stop(self):
        self.live = False