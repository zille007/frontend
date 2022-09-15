from gevent import monkey; monkey.patch_all()
import database
from os import urandom
from hashlib import sha1
import UserState
import collections
import datetime
import threading
import matchmaking
from FrontendConfig import *

MATCH_STATE_UNKNOWN = 0
MATCH_STATE_OPEN = 1
MATCH_STATE_PLAYERS_IN = 2
MATCH_STATE_CREATED = 3
MATCH_STATE_PLAYERS_READY = 4
MATCH_STATE_COUNTDOWN = 5
MATCH_STATE_STARTED = 6
MATCH_STATE_ENDED = 7
MATCH_STATE_CLOSED = 8

PLAYER_STATE_UNKNOWN = 0
PLAYER_STATE_NOT_READY = 1
PLAYER_STATE_READY = 2

MATCH_TYPE_NONE = 0
MATCH_TYPE_PVP_1V1 = 1
MATCH_TYPE_PVP_2V2 = 2
MATCH_TYPE_SINGLE_PLAYER = 3
MATCH_TYPE_2P_COOP = 4
MATCH_TYPE_HEROES_ONLY_2V2 = 5
MATCH_TYPE_RANKED = 6
MATCH_TYPE_CUSTOM = 7
MATCH_TYPE_MATCHMAKING = 8
MATCH_TYPE_MATCHMAKING_DONE = 9
MATCH_TYPE_DEBUG = 10
MATCH_TYPE_MAX = MATCH_TYPE_DEBUG



class MatchAIPlayer(object):
    def __init__(self, hero = 0, difficulty = "easy"):
        self.selectedHero = hero
        self.difficulty = difficulty


class MatchEntry(object):
    MatchTypeStrings = ( "NONE", "1v1", "2v2", "single", "coop", "ho_2v2", "ranked", "custom", "matchmaking", "matchmaking_done", "debug" )
    MatchTypeRequiredPlayers = ( 2, 2, 4, 1, 2, 4, 1, 1, 1, 1, 1 )
    MatchTypePlayersPerTeam = (1, 1, 2, 1, 1, 2, 1, 1, 1, 1, 1 )

    def typeString(self):
        return MatchEntry.MatchTypeStrings[ self.matchType ]

    def setMap(self, new_map):
        self.mapPreference = new_map

    def setGameType(self, new_type):
        print "Will set game type %s" % (new_type, )
        if type( new_type ) == str or type( new_type ) == unicode:
            self.matchType = MatchEntry.MatchTypeStrings.index( new_type )
        else:
            self.matchType = new_type

        if self.matchType == MATCH_TYPE_MATCHMAKING:
            for i in range(0, len(self.teams[1]) ):
                if self.teams[1][i] is not None and isinstance( self.teams[1][i], MatchAIPlayer ):
                    self.teams[1][i] = None

            for i in range(0, len(self.teams[2]) ):
                if  self.teams[2][i] is not None and isinstance( self.teams[2][i], MatchAIPlayer ):
                    self.teams[2][i] = None

            self.resize( MATCHMAKING_GAME_SIZE / 2 )
            self.repack( True )

        print "Match type is now %d" % (self.matchType,)

    def requiredPlayers(self):
        #assert( self.matchType > MATCH_TYPE_NONE and self.matchType <= MATCH_TYPE_MAX )
        return len(self.teams[1]) * 2
        #return MatchEntry.MatchTypeRequiredPlayers[ self.matchType ]

    def matchTypeString(self):
        assert( self.matchType > MATCH_TYPE_NONE and self.matchType <= MATCH_TYPE_MAX )
        return MatchEntry.MatchTypeStrings[ self.matchType ]

    def backendState(self, stateChange):
        pass

    def humansAndAisInTeam(self, team):
        return len( filter( lambda x: x is not None, self.teams[team] ) )

    def activePlayersInTeam(self, team):
        c = 0
        for i in range(0, len(self.teams[team]) ):
            if self.teams[team][i] != None:
                c += 1
        return c

    def firstFreeSlotInTeam(self, team):
        for i in range(0, len(self.teams[team])):
            if self.teams[team][i] == None:
                return i

        return -1


    def playerJoin(self, player, team = -1, index = -1):
        assert( not self.players.has_key( player.username ) )
        assert( player.match is None )
        assert( player not in self.teams[1] )
        assert( player not in self.teams[2] )

        if self.state == MATCH_STATE_OPEN and self.players.keys() == self.requiredPlayers():
            self.state = MATCH_STATE_PLAYERS_IN

        t1_c = self.activePlayersInTeam(1)
        t2_c = self.activePlayersInTeam(2)

        if team == -1:
            if t1_c <= t2_c:
                team = 1
            else:
                team = 2

        if index == -1 or self.teams[team][index] is not None:
            print "Player %s is trying to join team %d index %d but the slot is not free, trying next free index..." % (player.username, team, index)
            index = self.firstFreeSlotInTeam(team)
            if index == -1:
                otherteam = 1 if team == 2 else 2
                print "Cannot slot player to team %d on any index, trying team %d" % (team, otherteam)
                index = self.firstFreeSlotInTeam( otherteam )
                if index == -1:
                    print "Could not slot player to any team; rejecting join."
                else:
                    team = otherteam

        if self.teams[team][index] == None:
            self.teams[team][index] = player
            self.players[ player.username ] = player
            player.joinedMatch( self )
            print "Player %s JOINED match %s; team %d index %d" % (player.username, self.token, team, index)

        if self.creator is None:
            self.creator = player
            print "Match %s did not have a creator; reassigned to player %s" % (self.token, player.username)


    def playerLeave(self, player):
        # TODO players leaving should INVALIDATE MATCHMAKING STATE

        assert( self.players.has_key( player.username ) )
        assert( player.match is self )

        if self.state == MATCH_STATE_PLAYERS_IN and self.players.keys() < self.requiredPlayers():
            self.state = MATCH_STATE_OPEN

        index = -1
        if player in self.teams[1]:
            index = self.teams[1].index( player )
            self.teams[1][index] = None

        if player in self.teams[2]:
            index = self.teams[2].index( player )
            self.teams[2][index] = None

        del self.players[player.username]
        player.leftMatch( self )

        print "Player %s LEFT match %s (was index %d)" % (player.username, self.token, index)

        # take the match out of matchmaking queue when users leave
        if self.matchmakingGroup is not None:
            self.endMatchmaking( self.matchmakingGroup.matchmaker )

        if player is self.creator:
            if len(self.players) > 0:
                newCreator = self.players.values()[0]
                self.creator = newCreator
                print "Creator of match %s left; creator status reassigned to player %s" % (self.token,self.creator.username)
            else:
                self.creator = None
                print "Creator of match %s left and match has no more players. Setting empty creator." % (self.token,)

    def swap(self, from_team, from_slot, to_team, to_slot ):
        with self.lock:
            p1 = self.teams[from_team][from_slot]
            p2 = self.teams[to_team][to_slot]

            self.teams[from_team][from_slot] = p2
            self.teams[to_team][to_slot] = p1

    def addAI(self, team, index, hero, difficulty):
        with self.lock:
            if self.teams[team][index] == None:
                ai = MatchAIPlayer( hero, difficulty )
                self.teams[team][index] = ai
                return True

            return False

    def setAI(self, team, slot, hero, difficulty):
        with self.lock:
            ai = self.teams[team][slot]
            if isinstance( ai, MatchAIPlayer ):
                ai.selectedHero = hero
                ai.difficulty = difficulty
                self.teams[team][slot] = ai

    def kickSlot(self, team, slot):
        p = self.teams[team][slot]
        if isinstance( p, UserState.UserState ):
            self.playerLeave(p)
        self.teams[team][slot] = None

    def start(self):
        with self.lock:
            assert( self.state == MATCH_STATE_CREATED )
            self.state = MATCH_STATE_STARTED
            print "Match %s is now in state STARTED" % (self.token,)

    def create(self, db):
        self.state = MATCH_STATE_CREATED
        print "Match %s is now in state CREATED" % (self.token,)
        pass

    def canStart(self):
        if self.humansAndAisInTeam(1) == 0 or self.humansAndAisInTeam(2) == 0:
            return False

        playersReady = True if (self.activePlayersInTeam(1) == len(self.teams[1]) and self.activePlayersInTeam(2) == len(self.teams[2]) ) else False

        for p in self.players.keys():
            if self.players[p].state != UserState.USER_READY:
                playersReady = False
                break

        if self.state in (MATCH_STATE_PLAYERS_IN, MATCH_STATE_OPEN) and playersReady:
           return True

        return False

    def repack(self, singleTeam = False):
        t1 = [None] * self.playersPerTeam
        t2 = [None] * self.playersPerTeam

        if singleTeam:   # pack everyone into team 1 until we cant anymore
            i = 0
            for u in self.teams[1] + self.teams[2]:
                if u is not None:
                    if i < len(t1):
                        t1[i] = u
                        i += 1
                    else:
                        self.playerLeave( u )
        else:
            i = 0
            for u in self.teams[1]:
                if u is not None:
                    t1[i] = u
                    i += 1
            i = 0
            for u in self.teams[2]:
                if u is not None:
                    t2[i] = u
                    i += 1
        self.teams[1] = t1
        self.teams[2] = t2


    def resize(self, newsize):
        with self.lock:
            if len( self.teams[1] ) != newsize and newsize > 0 and newsize < 10:
                if newsize > len(self.teams[1] ):
                    diff = newsize - len(self.teams[1])
                    for x in range( 0, diff ):
                        self.teams[1].append( None )
                        self.teams[2].append( None )
                else:
                    diff = len(self.teams[1]) - newsize
                    for x in range( 0, diff ):
                        e = self.teams[1].pop(-1)
                        if isinstance( e, UserState.UserState ):
                            self.playerLeave( e )
                        e = self.teams[2].pop(-1)
                        if isinstance( e, UserState.UserState ):
                            self.playerLeave( e )
                self.playersPerTeam = newsize


    def close(self):
        players = []
        for p in self.players.keys():
            players.append( self.players[p] )

        for p in players:
            self.playerLeave( p )
        self.players = {}
        self.state = MATCH_STATE_CLOSED
        print "Match %s is now in state CLOSED" % (self.token,)

    def touch(self):
        #print "Touch on match %s..." % (self.token,)
        with self.lock:
            # make sure we only have logged in users
            for p in self.players.keys():
                pass
            pass
        #print "Touch on match %s END..." % (self.token,)

    def setTimer(self, seconds):
        self.startTimer = datetime.datetime.now() + datetime.timedelta( seconds=seconds )

    def hasTimerExpired(self):
        if self.startTimer is None:
            return False

        return True if (self.startTimer - datetime.datetime.now()).seconds <= 0 else False

    def canStartMatchmaking(self):
        if self.matchType != MATCH_TYPE_MATCHMAKING:
            return False

        if self.state != MATCH_STATE_OPEN and self.state != MATCH_STATE_PLAYERS_IN:
            return False

        if self.matchmakingGroup != None:
            return False

        return True

    def startMatchmaking(self, matchmaker):
        self.matchmakingGroup = matchmaking.MatchmakingGroup()
        for p in self.players.keys():
            u = self.players[p]
            self.matchmakingGroup.addPlayer( u )
        matchmaker.addGroup( self.matchmakingGroup )

    def endMatchmaking(self, matchmaker):
        if self.matchmakingGroup is None:
            return

        if matchmaker is not None:
            matchmaker.removeGroup( self.matchmakingGroup )
        self.matchmakingGroup = None


    def __init__( self, type, creator ):
        #assert( type > MATCH_TYPE_NONE and type <= MATCH_TYPE_MAX )

        mid = urandom(32)
        mid_str = ":".join("{0:x}".format(ord(c)) for c in mid)
        self.mapPreference = "Snowy Mountain Pass"
        self.token = sha1(u'%s%s' % (mid_str, self.mapPreference)).hexdigest()
        self.matchType = MatchEntry.MatchTypeStrings.index( type )
        self.playersPerTeam = 1 # MatchEntry.MatchTypeRequiredPlayers[ self.matchType ]
        self.state = MATCH_STATE_OPEN
        self.creator = creator
        self.players = {}
        self.teams = { 1:[ None ] * self.playersPerTeam, 2:[ None ] * self.playersPerTeam }
        self.lock = threading.Lock()
        self.isTutorial = False
        self.matchmakingGroup = None
        self.startTimer = None

        if type == "matchmaking":
            self.setGameType( "matchmaking" )
            self.resize( 3 )


class DiscoveryEngine(object):
    def isUserMatchmaking(self, user):
        return user in self.matchmakingQueue

    def removeWithUsername(self, username):
        l = []
        for u in self.matchmakingQueue:
            if u.username == username:
                l.append(u)

        for u in l:
            self.matchmakingQueue.remove(u)

    def memberNames(self):
        return map( lambda i: i.username if i is not None else '**NONE**', list(self.matchmakingQueue) )

    def matchmakingPass1v1(self):
        if len(self.matchmakingQueue) >= 2:
            p1 = self.matchmakingQueue.pop()
            p2 = self.matchmakingQueue.pop()

            if (datetime.datetime.now() - p1.lastActivity).seconds > 30:
                self.matchmakingQueue.append( p2 )
                return None

            if (datetime.datetime.now() - p2.lastActivity).seconds > 30:
                self.matchmakingQueue.append( p1 )
                return None


            match = MatchEntry( "ranked", p1 )
            match.playerJoin( p1, 1, 0 )
            match.playerJoin( p2, 2, 0 )

            return match

        return None

    def endMatchmaking(self, user):
        if user in self.matchmakingQueue:
            self.matchmakingQueue.remove( user )
        self.removeWithUsername( user.username )

    def startMatchmaking(self, user):
        if user.match is None and user not in self.matchmakingQueue:
            self.matchmakingQueue.append( user )

    def __init__(self):
        self.matchmakingQueue = collections.deque()
