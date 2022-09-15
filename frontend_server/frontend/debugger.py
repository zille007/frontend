import mechanize
import argparse
import threading
import collections
import time
import datetime

class Login(object):
    def queueFrontendCommand(self, tag, endpoint, arguments, callback):
        pass

    def login(self, host, port, username, password):
        pingLoopThread = threading.Thread( group=None, target=self.pingLoop, "PingLoop-%s" % (self.username,) )
        pingLoopThread.start()

    def pingLoop(self):
        pass

    def __init__(self, host, port, username, password):
        self.host = host
        self.port = port
        self.username = username
        self.password = password
        self.frontendQueue = collections.deque()
        self.backendQueue = collections.deque()     # outgoing
        self.backendReceived = collections.deque()  # incoming
        self.mechanize = mechanize.Browser()
        self.lastPing = {}
        self.lastPingTime = None
        self.pingLoopThread = None
        self.state = "Initialized"


class CommandInterface(self):
    def __init__(self):
        self.commands = {}
        self.messageBuffer = collections.deque()
        self.lock = threading.Lock()


if __name__ == '__main__':
    ci = CommandInterface()


