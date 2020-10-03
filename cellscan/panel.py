import threading
import time
import logging
from gpiozero import LED, Button

log = logging.getLogger('panel')

class PanelThread(threading.Thread):
    def __init__(self, q):
        threading.Thread.__init__(self)
        self.q = q
        self.live = True
        self.ledmode = 'off'

    def run(self):
        # LED expected to be on GPIO 18.
        led = LED(18)
        # Button expected to be on GPIO 4 and to be active low (e.g. connected to GND)
        button = Button(4)

        button.when_pressed = self.__startPress
        button.when_released = self.__endPress
        log.debug("Panel thread startup complete")
        
        # TODO: this state machine fuckery is turning into a pain. Should probably reimplement
        # LED control in a more event-based (e.g. sane) way.
        while self.live:
            if self.ledmode == 'blink':
                led.toggle()
            if self.ledmode == 'on':
                led.on()
            if self.ledmode == 'off':
                led.off()
            if self.ledmode == 'once':
                led.on()
                self.ledmode = "oncedone"
            if self.ledmode == 'oncedone':
                led.off()
                self.ledmode = "off"

            time.sleep(1)

    def stop(self):
        self.live = False

    def setLed(self, mode):
        self.ledmode = mode

    def __startPress(self):
        self.downTime = time.time()

    def __endPress(self):
        downtime = time.time() - self.downTime
        # Sending currently unnecessary "type" because I might add a second button in the future,
        # or even rocker switch for more tactile enable/disable of location recording.
        self.q.put(['PanelEvent', {'type': 'CtlButton', 'time': downtime}])
