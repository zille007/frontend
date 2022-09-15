import mechanize
import urllib
import datetime
import json
import time
import random

class LoginState:
    def requestEndpoint(self, endpoint, **kwargs):
        d = dict(kwargs)
        d2 = { "request_data": json.dumps(d) }
        self.mechanize.open( self.endpointUrl( endpoint ), urllib.urlencode( d2 ) )
        res = json.loads( self.mechanize.response().get_data() )
        return res

    def doLogin(self):
        res = self.requestEndpoint( "login", username=self.username, password=self.password, clientversion=self.clientVersion, clientplatform=self.clientPlatform )
        print res["is_admin"]

    def doPing(self):
        res = self.requestEndpoint( "ping" )

    def enterQueue(self):
        self.requestEndpoint( "match/create", type="matchmaking" )
        self.requestEndpoint( "match/find_new/start" )
        self.inMatchmakingQueue = True

    def leaveQueue(self):
        if self.inMatchmakingQueue:
            self.requestEndpoint( "match/find_new/end" )
        self.inMatchmakingQueue = False


    def endpointUrl(self, endpoint):
        return "%s%s" % (self.frontendUrl, endpoint)

    def recreateUrl(self):
        self.frontendUrl = "http://%s:%d/" % (self.host, self.port)

    def setHostPort(self, host, port=7070):
        self.host = host
        self.port = port
        self.recreateUrl()

    def __init__(self, uname, passwd, clientVersion = "0.3.0.4", clientPlatform = "TEST"):
        self.mechanize = mechanize.Browser()
        self.username = uname
        self.password = passwd
        self.host = "127.0.0.1"
        self.port = 7071
        self.clientVersion = clientVersion
        self.clientPlatform = clientPlatform
        self.setHostPort( self.host, self.port )
        self.inMatchmakingQueue = False

if __name__ == "__main__":
    i = 8
    users = []

    for i in xrange( 1, i ):
        u = LoginState( "thtest%d" % (i,), "foobar" )
        u.doLogin()
        users.append( u )

    while True:
        for u in users:
            u.doPing()

            if not u.inMatchmakingQueue:
                if random.randint( 0, 10 ) < 5:
                    # 5 in 10 chance to enter queue
                    u.enterQueue()
            else:
                if random.randint( 0, 10 ) < 5:
                    # 5 in 10 chance to leave queue
                    u.leaveQueue()

        time.sleep( 2 )
