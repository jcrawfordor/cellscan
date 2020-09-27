import threading
import time
import logging
import serial

log = logging.getLogger('radio')

class RadioException(Exception):
    pass

class RadioThread(threading.Thread):
    def __init__(self, q, ATPort):
        threading.Thread.__init__(self)
        self.q = q
        self.ATPort = ATPort
        self.live = True
        self.atx = None

    def run(self):
        log.debug(f"Connecting to radio on {self.ATPort} to configure...")
        self.atx = serial.Serial(self.ATPort)
        self.__atReset()
        modemModel = self.__atIdentify()
        log.info(f"Connected to modem {modemModel}")
        log.debug("Enabling unsolicited NMEA data...")
        self.__atEnableNMEA()
        
        while self.live:
            try:
                sites = self.__networkScan()
                self.q.put(['NetworkData', {'sites': sites}])
            except Exception:
                log.exception("Network scan failed.")
            time.sleep(1)
    
    def __networkScan(self):
        log.debug("Starting network scan")
        lines = self.__atGetResp(b'AT#CSURV')
        log.debug("End of network scan, parsing")
        sites = []
        for line in lines.split("\n"):
            log.debug(f"Parsing line: {line}")
            if line.startswith("uarfcn"):
                # Indicates a 3G cell
                lineItems = line.split()
                mcc = lineItems[5]
                mnc = lineItems[7]
                scr = lineItems[10]
                cellid = lineItems[12]
                lac = [14]
                sites.append({'mcc': mcc, 'mnc': mnc, 'lac': lac, 'cellid': cellid})

            if line.startswith("arfcn"):
                # Indicates a 3G cell
                lineItems = line.split()
                mcc = lineItems[9]
                mnc = lineItems[11]
                lac = lineItems[13]
                cellid = lineItems[15]
                sites.append({'mcc': mcc, 'mnc': mnc, 'lac': lac, 'cellid': cellid})

        return sites

    def __atReset(self):
        # This is kind of a weird set of steps designed to put the modem into a good state even if
        # it had previously received a partial command or was in a weird config (e.g. echo on).
        # I kept running into this stuff in testing/debugging.
        self.atx.write(b'\r\n') # Clear any partial command it may have received
        self.atx.write(b'ATZ\r\n') # Soft reset modem (turns off weird modes)
        time.sleep(1)
        self.atx.reset_input_buffer() # Discard anything the modem returned (echos, etc)
    
    def __atIdentify(self):
        return self.__atGetResp(b'AT+GMM').strip()

    def __atEnableNMEA(self):
        # Enable power to GPS module
        self.__atGetResp(b'AT$GPSP=1', errorOK=True)
        # Enable NMEA stream via dedicated NMEA interface
        self.__atGetResp(b'AT$GPSNMUN=2,1,1,1,1,1,1')

    def __atGetResp(self, command, errorOK=False):
        self.atx.write(command + b'\r\n')
        log.debug(f"Sent command {command}")
        data = ''
        # Eat the echo back
        log.debug(f"AT Reply (echoback): {self.atx.readline().strip()}")
        # Get the actual response
        line = self.atx.readline().decode('ASCII').strip()
        while line != "OK" and line != "ERROR":
            if line != "":
                log.debug(f"AT Reply: {line}")
                data += line + '\n'
            line = self.atx.readline().decode('ASCII').strip()

        if line == "ERROR" and not errorOK:
            raise RadioException(f"Command {command}, Expected OK but got {line}")

        return data

    def stop(self):
        self.live = False
