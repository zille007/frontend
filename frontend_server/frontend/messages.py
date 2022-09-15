from gevent import monkey; monkey.patch_all()

import Queue
import datetime
import time

CHANNEL_PUBLIC = 1
CHANNEL_PRIVATE_1TO1 = 2
CHANNEL_PRIVATE_PARTY = 3
CHANNEL_SYSTEM_BROADCAST = 4

MESSAGE_NORMAL = 1
MESSAGE_NOTICE = 2
MESSAGE_BROADCAST = 3
MESSAGE_ADMIN = 4

class Message(object):
    def __init__(self, sender, sender_uid, message_text, channel = None, message_type = MESSAGE_NORMAL ):
        self.sender = sender
        self.sender_uid = sender_uid
        self.text = message_text
        self.channel = None
        self.messageType = message_type
        self.timestamp = datetime.datetime.now()


class UserMessageQueue(object):
    def putMessage(self, message):
        self.queue.put( message, False )

    def getMessage(self):
        self.lastActivity = datetime.datetime.now()
        try:
            return self.queue.get( False )
        except Queue.Empty:
            pass
        return None

    def size(self):
        return self.queue.qsize()

    def empty(self):
        return self.queue.empty()

    def touch(self):
        self.lastActivity = datetime.datetime.now()

    def inactivitySeconds(self):
        return (datetime.datetime.now() - self.lastActivity).seconds

    def __init__(self, username, screenname, uid = -1 ):
        assert( username is not None )
        assert( len(username) > 0 )

        self.userid = uid
        self.username = username
        self.screenname = screenname
        self.queue = Queue.Queue()
        self.channels = []
        self.lastActivity = datetime.datetime.now()
        self.admin = False


class Channel(object):
    def userLeave(self, userq):
        if self.userQueues.has_key( userq.username ):
            del self.userQueues[userq.username]
            return True
        return False

    def userJoin(self, userq):
        if not self.userQueues.has_key( userq.username ):
            self.userQueues[userq.username] = userq
            return True
        return False

    def checkInactiveUsers(self):
        inactives = []
        for q in self.userQueues.values():
            if q.inactivitySeconds() > 30:
                inactives.append(q)
        filter( lambda u: self.userLeave(u), inactives )

    def postMessage(self, message):
        self.checkInactiveUsers()

        for q in self.userQueues.values():
            if q.screenname != message.sender:
                q.putMessage( message )
        self.lastMessage = datetime.datetime.now()

    def __init__(self, channelname, channeltype):
        self.channelname = channelname
        self.channeltype = channeltype
        self.lastMessage = datetime.datetime.now()
        self.userQueues = {}



class MessageCenter(object):
    def createChannel(self, channelname, channeltype):
        if not self.channels.has_key( channelname ):
            self.channels[channelname] = Channel( channelname, channeltype )
            return True

        return False

    def getChannel(self, channel):
        if self.channels.has_key( channel ):
            return self.channels[channel]
        else:
            print "No such channel %s" % (channel,)
        return None

    def getUserQueue(self, username):
        if self.users.has_key(username):
            return self.users[username]

        return None

    def userJoinChannel(self, username, channel ):
        if self.channels.has_key( channel ) and self.users.has_key( username ):
            channel = self.channels[channel]
            userq = self.users[username]
            if channel.userJoin( userq ):
                userq.channels.append( channel.channelname )
                return True

        return False

    def userLeaveChannel(self, username, channel):
        if self.channels.has_key( channel ) and self.users.has_key( username ):
            channel = self.channels[channel]
            userq = self.users[username]
            if channel.userLeave( userq ):
                userq.channels.remove( channel.channelname )
                return True

        return False

    def userLogin(self, username, screenname, userid = -1):
        if not self.users.has_key( username ):
            q = UserMessageQueue( username, screenname, userid )
            self.users[username] = q
            return q

        return None

    def userLogout(self, username):
        if self.users.has_key( username ):
            for ch in self.users[username].channels.__reversed__():
                self.userLeaveChannel( username, ch )

            del self.users[username]
            return True
        return False

    def postMessageToChannel(self, channel, message ):
        if self.channels.has_key(channel):
            channel = self.channels[channel]
            if channel.channeltype == CHANNEL_SYSTEM_BROADCAST:
                uq = self.getUserQueue( message.sender )
                if not uq or not uq.admin:
                    return False

            message.channel = channel
            channel.postMessage( message )
            return True

    def postToChannel(self, from_user, from_uid, channel, message_text, message_type = MESSAGE_NORMAL ):
        msg = Message( from_user, from_uid, message_text, message_type )
        return self.postMessageToChannel( channel, msg )

    def __init__(self):
        self.channels = {} # "channelname":Channel
        self.users = {}

        self.createChannel( "SYSTEM-NOTICES", CHANNEL_SYSTEM_BROADCAST )
        self.createChannel( "General", CHANNEL_PUBLIC )
