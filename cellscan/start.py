#!/usr/bin/env/python3

import logging
import argparse
import time
import queue

from cellscan.panel import PanelThread

def __main__():
    parser = argparse.ArgumentParser(description='CellScan service.')
    parser.add_argument('-l', '--log', dest='logLevel', choices=['DEBUG', 'INFO', 'WARNING', 'ERROR', 'CRITICAL'], default='INFO', help='Set the logging level')
    args = parser.parse_args()

    logging.basicConfig(level=getattr(logging, args.logLevel))
    log = logging.getLogger("cellscan")
    log.info("CellScan starting up.")

    # We will use this queue to receive messages from threads
    q = queue.Queue()

    panel = PanelThread(q)
    panel.start()
    time.sleep(10)

if __name__ == "__main__":
    __main__()
