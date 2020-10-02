import threading
import time
import logging
import subprocess
import re
import ipaddress

log = logging.getLogger('upload')

from cellscan.data import Cellsite, Location

class UploadException(Exception):
    pass

class UploadThread(threading.Thread):
    """
    This thread can be started to submit the collected data to the data collection server online.
    Because we upload using the cellular modem but we are mostly using the cellular modem to scan
    (which is an unusual use case not well supported by anything), this thread requires some
    special handling:

    * Do not start this thread during scanning. It will probably completely fail due to the running
      scan and may also break the scans (the Telit manual just says "don't do this," does not
      really expound on why).
    * This thread needs to cleanly exit before scans start or you could run into the same
      problems. Likewise, the scan thread should be cleanly terminated before starting this one.
    
    This all adds up to the upload process probably taking 1 minute or more to complete.

    This thread does a lot of stuff manually that would normally be done automatically by
    NetworkManager. The reason is basically that we want to very closely control the process so
    that we can confidently assert whether or not anything outside of our code is communicating
    with the modem. Tricky since normally commanding the modem is something that some daemon would
    just do in the background.

    This is also written for the situation where the modem is using a pay-per-MB cellular plan. So
    keeping the network config very "manual" prevents autoupdates or something hitting the modem,
    and in general we are trying to keep our network traffic to as few bytes as achievable.

    Finally, this all assumes that the modem can be connected using USB CDC, e.g. it is connected
    by USB and the kernal has CDC support so the modem "magically" appears as a network inteface.
    If this isn't the case, probably because you are connecting to the modem via UART, you will
    need to add some additional setup here for pppd over tty.

    Positional arguments:
    q -- queue object for communication with master thread
    target -- IP to submit data to

    Keyword arguments:
    modemIndex -- the index # of the modem according to mmcli. Normally '0' unless there are multiple.
    interface -- the name of the network interface for the modem. Normally 'wwan0'.
    apn -- APN to use for data bearer connection
    """

    def __init__(self, q, target, interface="wwan0", apn="hologram"):
        threading.Thread.__init__(self)
        self.q = q
        self.target = target
        self.modemIndex = 0
        self.bearerIndex = 0
        self.interface = interface
        self.apn = apn

    def run(self):
        log.info("Starting upload")
        self.__getDataConnection()
        self.__uploadData()
        self.__disableNetworkConnection()
        self.q.put(["UploadComplete", {}])

    def __getDataConnection(self):
        # Find out what index # the modem is, because it changes
        modemResp = subprocess.check_output(['mmcli', '-L']).decode('UTF-8')
        self.modemIndex = re.search(r"/Modem/(\d+) ", modemResp).group(1)

        log.debug("Reseting network config")
        # We do this stuff because several steps will fail if they are already setup from last time
        subprocess.check_output(["ip", "addr", "flush", "dev", self.interface])

        # Enable the modem, which is often disabled at boot
        log.debug(f"Enabling modem {self.modemIndex}")
        # This one must succeed, we let the exception propagate up if it doesn't
        subprocess.check_output(["mmcli", "-m", self.modemIndex, "-e"])

        # Run simple connect. This frequently fails because something takes too long to happen, so
        # we're going to run it once to load in the config and then connect in a retry loop.
        log.debug(f"Configuring modem for APN {self.apn}")
        try:
            subprocess.check_output(["mmcli", "-m", self.modemIndex, "--simple-connect", f"apn={self.apn}", "--timeout", "30"])
        except subprocess.CalledProcessError:
            log.debug("Initial modem connection failed, probably timeout, will retry")
        
        # Now we need to find the bearer # which also changes
        bearerResp = subprocess.check_output(['mmcli', '-m', self.modemIndex]).decode('UTF-8')
        self.bearerIndex = re.search(r"/Bearer/(\d+)", bearerResp).group(1)
        log.debug(f"Using data bearer channel {self.bearerIndex}")
        
        # Retry connecting until it works
        retryCount = 0
        bearerInfo = self.__checkModemBearerStatus()
        while bearerInfo == None:
            if retryCount > 5:
                raise UploadException("Could not connect modem after multiple retries.")
            retryCount += 1
            log.debug(f"Connecting modem for data, retry {retryCount}")

            try:
                subprocess.check_output(["mmcli", "-b", self.bearerIndex, "-c"])
            except subprocess.CalledProcessError:
                log.debug("Modem connect command failed, probably timeout")

            time.sleep(10)
            bearerInfo = self.__checkModemBearerStatus()
        
        # We should now have network time available, take this opportunity to set our local clock
        # to the cell network time, which is probably more accurate than the Pi's RTC when it's been
        # running independently for god knows how long.
        try:
            timeResp = subprocess.check_output(['mmcli', '-m', self.modemIndex, '--time']).decode('UTF-8')
            log.debug(f"mmcli says: {timeResp}")
            timeString = re.match(r"Time\W+\|\W+current: (.+)$", timeResp, re.MULTILINE).group(1)
            timeString = timeString[:-6].replace('T','')
            log.debug(f"Setting system time to {timeString}")
            subprocess.check_output(['timedatectl', 'set-time', timeString])
        except:
            log.exception("Error updating local time")
        
        log.debug(f"Adding IP and routes. Our IP {bearerInfo['ip']}, prefix {bearerInfo['prefix']}, gateway {bearerInfo['gateway']}, mtu {bearerInfo['mtu']}")
        # Set IP and MTU on device
        subprocess.check_output(["ip", "link", "set", "dev", self.interface, "up"])
        subprocess.check_output(["ip", "addr", "add", bearerInfo['ip'], "dev", self.interface])
        subprocess.check_output(["ip", "link", "set", "dev", self.interface, "mtu", bearerInfo['mtu']])
        # Figure out routes
        # We need to calculate the "network IP" for the route because mmcli doesn't give it to us
        # directly, but ip route will reject if we use a wack IP with a CIDR. non-strict parsing
        # in the ipaddress module seems to be fine with describing a network with an IP *in* it.
        net = ipaddress.IPv4Network(f"{bearerInfo['ip']}/{bearerInfo['prefix']}", strict=False)
        baseIP = net.network_address
        log.debug(f"Adding routes for {baseIP}/{bearerInfo['prefix']} and {self.target}")
        # Route to access gateway
        subprocess.check_output(["ip", "route", "add", f"{baseIP}/{bearerInfo['prefix']}", "dev", self.interface])
        # Route to access target via gateway
        subprocess.check_output(["ip", "route", "add", self.target, "via", bearerInfo['gateway']])
        # And just like that, there should now be network connectivity to just the target IP.
    
    def __uploadData(self):
        log.error("Would upload data, but that's not implemented.")
        pass

    def __disableNetworkConnection(self):
        log.debug("Disabling network connection")
        subprocess.check_output(["ip", "link", "set", "dev", self.interface, "down"])
        log.debug("Disconnecting bearer channel")
        subprocess.check_output(["mmcli", "-b", self.bearerIndex, "-x"])

    def __checkModemBearerStatus(self):
        try:
            # We are just assuming it's bearer 0... won't deal with more.
            checkBearer = subprocess.check_output(["mmcli", "-b", self.bearerIndex])
            checkBearer = checkBearer.decode('UTF-8')
            if "connected: yes" in checkBearer:
                netInfo = {}
                netInfo['ip'] = re.search(r"address: ([\d\.]+)", checkBearer).group(1)
                netInfo['prefix'] = re.search(r"prefix: ([\d\.]+)", checkBearer).group(1)
                netInfo['gateway'] = re.search(r"gateway: ([\d\.]+)", checkBearer).group(1)
                netInfo['mtu'] = re.search(r"mtu: ([\d\.]+)", checkBearer).group(1)
                return netInfo
            else:
                log.debug("Modem bearer check succeeded but did not show connected status")
                return None
        except subprocess.CalledProcessError:
            log.debug("Checking modem bearer status failed.")
            return None
