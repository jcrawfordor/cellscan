import threading
import time
import logging
import subprocess
import re
import ipaddress
import json
import socket

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
    * Interacting with the cellular network at a low level is inherently unpredictable and some
      things will normally be retried a number of times before they succeed.
    
    This all adds up to the upload process probably taking 1 minute or more to complete. There is
    a generous chance that it will fail entirely for "normal" reasons (e.g. no cell reception).

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
    deviceID -- identification string for collection server to know who we are

    Keyword arguments:
    interface -- the name of the network interface for the modem. Normally 'wwan0'
    apn -- APN to use for data bearer connection
    """

    def __init__(self, q, target, deviceId, interface="wwan0", apn="hologram"):
        threading.Thread.__init__(self)
        self.q = q
        self.target = target
        self.deviceId = deviceId
        self.modemIndex = 0
        self.bearerIndex = 0
        self.interface = interface
        self.apn = apn

    def run(self):
        log.info("Starting upload")
        try:
            self.__getDataConnection()
            self.__uploadData()
            self.__disableNetworkConnection()
        except:
            log.exception("Upload failed")
        self.q.put(["UploadComplete", {}])

    def __getDataConnection(self):
        # Find out what index # the modem is, because it changes
        modemResp = subprocess.check_output(['mmcli', '-L']).decode('UTF-8')
        self.modemIndex = re.search(r"/Modem/(\d+) ", modemResp).group(1)

        # We do this because several steps will fail if the interface already has an IP.
        subprocess.check_output(["ip", "addr", "flush", "dev", self.interface])

        # Enable the modem, which is often disabled at boot
        log.debug(f"Enabling modem {self.modemIndex}")
        # This one must succeed, we let the exception propagate up if it doesn't
        subprocess.check_output(["mmcli", "-m", self.modemIndex, "-e"])

        # Run simple connect. This frequently fails because something takes too long to happen, so
        # we're going to run it once to load in the config and then connect in a retry loop.
        log.debug(f"Configuring modem for APN {self.apn}")
        try:
            subprocess.check_output(["mmcli", "-m", self.modemIndex, "--simple-connect", f"apn={self.apn}", "--timeout", "60"])
        except subprocess.CalledProcessError:
            log.debug("Initial modem connection failed, probably timeout, will retry")
        
        # Now we need to find the bearer # which also changes
        bearerResp = subprocess.check_output(['mmcli', '-m', self.modemIndex]).decode('UTF-8')
        self.bearerIndex = re.search(r"/Bearer/(\d+)", bearerResp).group(1)
        
        # Retry connecting until it works
        retryCount = 0
        bearerInfo = self.__checkModemBearerStatus()
        while bearerInfo == None:
            if retryCount > 10:
                raise UploadException("Could not connect modem after multiple retries.")
            retryCount += 1
            log.debug(f"Connecting modem for data, retry {retryCount}")

            try:
                subprocess.check_output(["mmcli", "-b", self.bearerIndex, "-c"])
            except subprocess.CalledProcessError:
                pass

            time.sleep(10)
            bearerInfo = self.__checkModemBearerStatus()
        
        # We should now have network time available, take this opportunity to set our local clock
        # to the cell network time, which is probably more accurate than the Pi's RTC when it's been
        # running independently for god knows how long.
        try:
            # timedatectl won't let us set clock when NTP is on. Besides, we wouldn't be bothering
            # with this if we thought there were any network connections for NTP to use.
            subprocess.check_output(['timedatectl', 'set-ntp', 'false'])
            timeResp = subprocess.check_output(['mmcli', '-m', self.modemIndex, '--time']).decode('UTF-8')
            timeString = re.search(r"Time\W+\|\W+current: (.+)\W", timeResp, re.MULTILINE).group(1)
            # mmcli tells us the time in strict ISO format, which oddly timedatectl does not
            # accept. We remove the TZ part and replace the 'T' with a space to make it happy.
            # Cell networks report local time so TZ is *NOT* zulu.
            # TODO: this will screw up time zones if the cell site does not match the OS TZ.
            # Need to intelligently correct TZ before going on any interstate trips.
            timeString = timeString[:-6].replace('T',' ')
            log.debug(f"Setting system time to {timeString}")
            subprocess.check_output(['timedatectl', 'set-time', timeString])
        except:
            log.exception("Error updating local time")
        
        log.debug(f"Cell network config: IP {bearerInfo['ip']}, prefix {bearerInfo['prefix']}, gateway {bearerInfo['gateway']}, mtu {bearerInfo['mtu']}")
        # Set IP and MTU on device
        subprocess.check_output(["ip", "link", "set", "dev", self.interface, "up"])
        subprocess.check_output(["ip", "addr", "add", bearerInfo['ip'], "dev", self.interface])
        subprocess.check_output(["ip", "link", "set", "dev", self.interface, "mtu", bearerInfo['mtu']])

        # Figure out routes
        # We need to calculate the "network IP" for the route because mmcli doesn't give it to us
        # directly, but ip route will reject if we use a wack IP with a CIDR. non-strict parsing
        # in the ipaddress module seems to be fine with describing a network using an IP *in* it.
        net = ipaddress.IPv4Network(f"{bearerInfo['ip']}/{bearerInfo['prefix']}", strict=False)
        baseIP = net.network_address
        # Route to access gateway
        subprocess.check_output(["ip", "route", "add", f"{baseIP}/{bearerInfo['prefix']}", "dev", self.interface])
        # Route to access target via gateway
        subprocess.check_output(["ip", "route", "add", self.target, "via", bearerInfo['gateway']])
        # And just like that, there should now be network connectivity to just the target IP.
        # TODO: add route to a DNS server so we can resolve collection server by name?
    
    def __uploadData(self):
        # We don't really need to worry about concurrent access here because the scan can't be
        # running during uploads, so we get to be a bit lazy...
        sites = Cellsite.select().where(Cellsite.uploaded == False)
        # This is just creating a transaction, we won't execute it unless we get positive
        # confirmation from the collection server.
        updateTx = Cellsite.update(uploaded=True).where(Cellsite.uploaded == False)

        siteList = []
        for site in sites:
            siteList.append({
                'lat': site.lat,
                'lon': site.lon,
                'alt': site.alt,
                'rx': site.rx,
                'mcc': site.mcc,
                'mnc': site.mnc,
                'cellid': site.cellid,
                'lac': site.lac,
                'gen': site.gen,
                'time': site.time.isoformat() # ugh
            })
        data = {'action': 'upload', 'device': self.deviceId, 'sites': siteList}
        dataString = json.dumps(data)

        # Here is a good place to describe our minimal "network protocol": the client sends a JSON
        # string as UTF-8 followed by an ASCII EOT character. It expects the server to reply
        # likewise. This is intended to be more economical with bytes than HTTP while still
        # allowing the server to have an opportunistic C2 channel for future features.
        # TODO: wrap this up with TLS. Consider implementing with Twisted to match the server code.

        attempts = 0
        while attempts < 5:
            attempts += 1
            log.debug(f"Sending data, attempt {attempts}")

            try:
                sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                sock.settimeout(20)
                sock.connect((self.target, 6402))
                sock.sendall(dataString.encode())
                sock.sendall(b'\x04')
                response = self.__receiveObject(sock)

                if response['status'] == 'OK':
                    updateTx.execute()
                    sock.close()
                    return
                else:
                    raise UploadException(f"Received bad response from server: {response}")
            except:
                log.exception("Sending data failed.")
        log.error("Gave up on uploading data after multiple attempts.")
    
    def __receiveObject(self, sock):
        message = b''
        while not message.endswith(b'\x04'):
            message += sock.recv(1024)
        return json.loads(message[:-1].decode('UTF-8'))

    def __disableNetworkConnection(self):
        log.debug("Disabling network connection")
        subprocess.check_output(["ip", "link", "set", "dev", self.interface, "down"])
        subprocess.check_output(["mmcli", "-b", self.bearerIndex, "-x"])

    def __checkModemBearerStatus(self):
        try:
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
                return None
        except subprocess.CalledProcessError:
            log.exception("Checking modem bearer status failed.")
            return None
