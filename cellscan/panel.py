import threading
import time
import logging
from gpiozero import LED, Button

log = logging.getLogger()

class PanelThread(threading.Thread):
    def __init__(self, q):
        threading.Thread.__init__(self)
        self.q = q
        self.live = True
        self.ledmode = 'blink'

    def run(self):
        led = LED(27)
        button = Button(22)
        button.when_pressed = self.__startPress
        button.when_released = self.__endPress
        log.debug("Panel thread startup complete")
        
        while self.live:
            if self.ledmode == 'blink':
                led.toggle()
            if self.ledmode == 'on':
                led.on()
            if self.ledmode == 'off':
                led.off()
            time.sleep(1)

    def stop(self):
        self.run = False

    def setLed(self, mode):
        self.ledmode = mode

    def __startPress(self):
        self.downTime = time.clock()

    def __endPress(self):
        downtime = time.clock() - self.downTime
        log.debug(f"Button held for {downtime} seconds.")
