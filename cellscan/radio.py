import threading
import time
import logging
import serial

log = logging.getLogger()

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
            log.debug("Starting network scan")
            try:
                sites = self.__networkScan()
                self.q.put(['NetworkData', {'sites': sites}])
            except Exception:
                log.exception("Network scan failed.")
            time.sleep(1)
    
    def __networkScan(self):
        self.atx.write(b'AT#CSURV')
        line = ""
        sites = []
        while line != "OK":
            line = self.atx.readline().decode('ASCII')
            log.debug(f"Scan data: {line}")

            if line.startswith("uarfcn"):
                # Indicates a 3G cell
                lineItems = line.split()
                mcc = lineItems[5]
                mnc = lineItems[7]
                scr = lineItems[10]
                cellid = lineItems[12]
                lac = [14]
                sites.append([mcc, mnc, lac, cellid])

            if line.startswith("arfcn"):
                # Indicates a 3G cell
                lineItems = line.split()
                mcc = lineItems[9]
                mnc = lineItems[11]
                lac = lineItems[13]
                cellid = lineItems[15]
                sites.append([mcc, mnc, lac, cellid])

        log.debug("End of network scan")
        return sites

    def __atReset(self):
        # This is kind of a weird set of steps designed to put the modem into a good state even if
        # it had previously received a partial command or was in a weird config (e.g. echo on).
        # I kept running into this stuff in testing/debugging.
        self.atx.write(b'\r\n') # Clear any partial command it may have received
        self.atx.write(b'ATE0\r\n') # Turn off echoing of commands
        self.atx.write(b'ATZ\r\n') # Soft reset modem (turns off weird modes)
        self.atx.reset_input_buffer() # Discard anything the modem returned (echos, etc)
    
    def __atIdentify(self):
        return self.__atGetResp(b'AT+GMM')

    def __atEnableNMEA(self):
        # Enable power to GPS module
        self.__atExpectOK(b'AT$GPSP=1')
        # Enable NMEA stream via dedicated NMEA interface
        self.__atExpectOK(b'AT$GPSNMUN=2,1,1,1,1,1,1')
    
    def __atExpectOK(self, command):
        # This raises an exception if the modem responds with other than "OK". Useful because a
        # large portion of AT commands expect "OK" or error message.
        res = self.__atGetResp(command)
        if res.endswith("OK"):
            return res
        else:
            raise RadioException(f"Command {command}, Expected OK but got {res}")

    def __atGetResp(self, command):
        self.atx.write(command + b'\r\n')
        log.debug(f"Sent command {command}")
        data = ''
        # Get the actual response
        line = self.atx.readline().decode('ASCII')
        while line != "OK":
            data += line + '\n'
            line = self.atx.readline().decode('ASCII').strip()
        data += line

        log.debug(f"{command} --> {data}")
        return data

    def stop(self):
        self.live = False