from datetime import datetime, timedelta

class SyscontrolState(object):
    def unsetDowntime(self):
        self.nextDowntime = None

    def setNextDowntimeByOffset( self, seconds ):
        self.nextDowntime = datetime.now() + timedelta(seconds=seconds)

    def getSecondsToDowntime(self):
        if self.nextDowntime == None:
            return -1

        if self.nextDowntime > datetime.now():
            return int( (self.nextDowntime - datetime.now()).total_seconds() )

        if datetime.now() > self.nextDowntime:
            return 0

        return self.nextDowntime

    def setSysMessage(self, message):
        self.messageNumber += 1
        self.currentMessage = message

    def __init__(self):
        self.messageNumber = 0
        self.currentMessage = ""
        self.messagePriority = "normal"
        self.nextDowntime = None

