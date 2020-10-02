import threading
import time
import logging
import serial
import subprocess
import re

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
        # Find out what index # the modem is, because it changes
        modemResp = subprocess.check_output(['mmcli', '-L']).decode('UTF-8')
        self.modemIndex = re.search(r"/Modem/(\d+) ", modemResp).group(1)

        # Before we start using the modem, we need to make sure that ModemManager doesn't
        # try to interact with it while we are. The mechanism is a little weird, when we run this
        # command ModemManager closes its handles on the serial devices and promises not to touch
        # them again for as long as the process this starts lives. This is of course yet another
        # reason why this thread needs to terminate cleanly before uploads can run.
        log.debug(f"Inhibiting modem index {self.modemIndex}")
        mmProcess = subprocess.Popen(["mmcli", "-m", "0", "--inhibit"])

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
                self.q.put(['NetworkData', sites])
            except Exception:
                log.exception("Network scan failed.")
            time.sleep(1)
        
        mmProcess.kill()
    
    def __networkScan(self):
        log.debug("Starting network scan")
        lines = self.__atGetResp(b'AT#CSURV')
        log.debug("End of network scan, parsing")
        sites = []
        for line in lines.split("\n"):
            log.debug(f"Parsing line: {line}")
            if line.startswith("earfcn"):
                # Indicates a 4G cell
                lineItems = line.split()
                rx = lineItems[3]
                mcc = lineItems[5]
                mnc = lineItems[7]
                cellid = lineItems[9]
                # For simplicity we just call it a LAC even though in 4G it's technically TAC
                lac = lineItems[11]
                sites.append({'rx': rx, 'mcc': mcc, 'mnc': mnc, 'lac': lac, 'cellid': cellid, 'gen': '4g'})

            if line.startswith("uarfcn"):
                # Indicates a 3G cell
                lineItems = line.split()
                rx = lineItems[3]
                mcc = lineItems[5]
                mnc = lineItems[7]
                scr = lineItems[10]
                cellid = lineItems[12]
                lac = lineItems[14]
                sites.append({'rx': rx, 'mcc': mcc, 'mnc': mnc, 'lac': lac, 'cellid': cellid, 'gen': '3g'})

            if line.startswith("arfcn"):
                # Indicates a 2G cell
                lineItems = line.split()
                rx = lineItems[5]
                mcc = lineItems[9]
                mnc = lineItems[11]
                lac = lineItems[13]
                cellid = lineItems[15]
                sites.append({'rx': rx, 'mcc': mcc, 'mnc': mnc, 'lac': lac, 'cellid': cellid, 'gen': '2g'})

        return sites

    def __atReset(self):
        # This is kind of a weird set of steps designed to put the modem into a good state even if
        # it had previously received a partial command or was in a weird config (e.g. echo on).
        # I kept running into this stuff in testing/debugging.
        log.debug("Reset modem")
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
