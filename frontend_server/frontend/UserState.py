from gevent import monkey; monkey.patch_all()

import datetime
import database
import MatchEntry
import users
import database
import discovery

USER_UNINITIALIZED = 0
USER_OFFLINE = 1
USER_IDLE = 2
USER_READY = 3
USER_MATCH_WAIT = 4
USER_INGAME = 5
USER_POSTGAME = 6
USER_DND = 6

class FriendInvite(object):
    def __init__(self, originator):
        self.originator = originator
        self.accepted = False
        self.acknowledged = False

class MatchInvite(object):
    def __init__(self, target, originator, inv_token, match_token, team, slot):
        self.originator = originator
        self.target = target
        self.inviteToken = inv_token
        self.matchToken = match_token
        self.targetTeam = team
        self.targetSlot = slot
        self.accepted = False
        self.acknowledged = False
        self.creationTime = datetime.datetime.now()


class UserStatsProxy(object):
    def refreshFromDb(self, db, dbUser):
        if self.user_id == -1:
            return

        dbStats = users.user_stats_for_user( db, dbUser )
        self.xp_level = dbStats.xp_level
        self.xp_current = dbStats.xp_current
        self.xp_next = dbStats.xp_next
        self.xp_rested = dbStats.xp_rested
        self.rating = dbStats.rating
        self.hard_money = dbStats.hard_money
        self.soft_money = dbStats.soft_money
        self.ladder = dbStats.ladder_value

    def __init__(self, userid):
        self.user_id = userid
        self.id = self.user_id
        self.xp_level = 1
        self.xp_current = 0
        self.xp_next = 62
        self.xp_rested = 0
        self.rating = 1500
        self.hard_money = 0
        self.soft_money = 0
        self.ladder = 13.0

class UserState(object):
    def log(self, db, entry_type, extra_data):
        users.write_log( db, entry_type, extra_data )

    def clearMatchRequests(self, db):
        discovery.clear_matchreqs_for_user( db, self )

    def persist(self, db):
        pass

    def deleteSession(self):
        pass

    def deleteRequests(self, db):
        discovery.clear_matchreqs_for_user( db, self.dbUser )

    def refreshHeroesFromDb(self, db, hero_names):
        possessed_chars = db.query( database.UserPossession ).filter( database.UserPossession.user_id == self.id, database.UserPossession.p_type == "character" ).all()
        viewable_heroes = hero_names
        selectable_heroes = [ "Bear" ]

        for c in possessed_chars:
            if c.p_item in hero_names:
                if c.p_item not in selectable_heroes:
                    selectable_heroes.append( c.p_item )
                if c.p_item not in viewable_heroes:
                    viewable_heroes.append( c.p_item )

        # if we've fucked up, give the player at least something; maybe should actually be hero_names?
        if len(selectable_heroes) == 0:
            selectable_heroes.append( "Bear" )

        self.setSelectableHeroes( selectable_heroes )
        self.setViewableHeroes( viewable_heroes )

    def refreshFromDb(self, db):
        if self.id == -1:
            self.dbUser = db.query( database.User ).filter_by( username=self.username ).first()
        else:
            self.dbUser = db.query( database.User ).filter_by( id = self.id ).first()

        self.id = self.dbUser.id
        self.clantag = self.dbUser.clantag
        #self.screenname = self.dbUser.screenname
        self.account_type = self.dbUser.account_type
        self.allow_login = self.dbUser.allow_login
        self.steamId = self.dbUser.steam_id
        if self.dbStats == None:
            self.dbStats = UserStatsProxy( self.id )

        self.dbStats.refreshFromDb( db, self.dbUser )


    def joinedMatch(self, match):
        assert( self.match is None )
        assert( self.state not in (USER_UNINITIALIZED, USER_OFFLINE) )
        self.match = match
        self.setReadyState( False )


    def leftMatch(self, match):
        assert( self.match is not None )
        self.match = None
        self.state = USER_IDLE
        self.readyToPlay = False

    def matchCreated(self):
        assert( self.match is not None )
        self.state = USER_MATCH_WAIT

    def matchStarted(self):
        assert( self.match is not None )
        self.state = USER_INGAME

    def matchEnded(self):
        assert( self.match is not None )
        self.state = USER_POSTGAME

    def matchClosed(self):
        assert( self.match is not None )
        self.state = USER_IDLE
        self.readyToPlay = False

    def selectHero(self, hero):
        #assert( self.match is not None )
        #assert( self.match.state == MatchEntry.MATCH_STATE_OPEN or self.match.state == MatchEntry.MATCH_STATE_PLAYERS_IN )
        assert( self.state in (USER_READY, USER_IDLE) )

        self.selectedHero = hero

    def setReadyState(self, newState):
        assert( self.match is not None )
        assert( self.state in (USER_READY, USER_IDLE) )

        if self.match.state == MatchEntry.MATCH_STATE_OPEN or self.match.state == MatchEntry.MATCH_STATE_PLAYERS_IN:
            if newState == True:
                self.state = USER_READY
                self.readyToPlay = True
            else:
                self.state = USER_IDLE
                self.readyToPlay = False

    def login(self, version, platform):
        print "Login on user %s" % (self.username, )

        self.clientVersion = version
        self.clientPlatform = platform
        self.loginTime = datetime.datetime.now()
        self.lastActivity = datetime.datetime.now()
        self.state = USER_IDLE
        #self.deleteRequests( db )
        self.match = None
        self.loggedIn = True
        self.status = "Online"
        pass

    def logout(self):
        print "Logout on user %s id %d" % (self.username,self.id)
        if self.match is not None:
            if self.match.matchmakingGroup is not None:
                self.match.endMatchmaking( self.match.matchmakingGroup.matchmaker )
            self.match.playerLeave( self )
        self.state = USER_OFFLINE
        self.deleteSession()
        self.loggedIn = False
        self.status = "Offline"

    def touch(self):
        self.lastActivity = datetime.datetime.now()

    def logoutIfIdle(self):
        if self.loggedIn and (datetime.datetime.now() - self.lastActivity).seconds > 30.0:
            self.logout()

    def inviteToMatch(self, inviter, matchtoken, team, slot):
        if not inviter.loggedIn:
            return

        i = MatchInvite( self, inviter, self.inviteCount, matchtoken, team, slot )
        self.matchInvites.append( i )
        self.inviteCount += 1
        return i

    def declineMatchInvite(self, invite_token):
        inv = None
        for i in self.matchInvites:
            if i.inviteToken == invite_token:
                inv = i
                break
        if inv:
            inv.acknowledged = True
            inv.accepted = False
            self.matchInvites.remove( inv )
        else:
            print "Could not decline invite %d on user %s: no such invite" % (invite_token, self.username)

    def acceptMatchInvite(self, invite_token):
        inv = None
        for i in self.matchInvites:
            if i.inviteToken == invite_token:
                inv = i
                break
        if inv:
            inv.acknowledged = True
            inv.accepted = True
            self.matchInvites.remove( inv )
        else:
            print "Could not decline invite %d on user %s: no such invite" % (invite_token, self.username)

    def inviteAsFriend(self, inviter):
        self.friendInvites.append( FriendInvite( inviter ))

    def getInviteSentTo(self, username):
        for i in self.sentMatchInvites:
            if i.target is not None and i.target.username == username:
                return i

        return None

    def cullSentInvites(self):
        l = []
        for i in self.sentMatchInvites:
            if i.acknowledged:
                l.append(i)

        for i in l:
            self.sentMatchInvites.remove(i)

    def setSteamTxParams(self, country, currency, account_status ):
        self.steamTxCountry = country
        self.steamTxCurrency = currency
        self.steamTxAccountStatus = account_status
        self.haveSteamTxInfo = True

    def setSelectableHeroes(self, heroes):
        self.selectableHeroes = heroes

    def setViewableHeroes(self, heroes):
        self.viewableHeroes = heroes

    def __init__(self, username, db):
        assert( db is not None )

        self.state = USER_UNINITIALIZED

        self.id = -1
        self.username = username
        self.screenname = ""
        self.clantag = ""
        self.account_type = 0
        self.allow_login = True
        self.rating = 0
        self.inviteCount = 0
        self.steamId = ""

        self.serverPreference = "any"

        self.haveSteamTxInfo = False
        self.steamTxCountry = ""
        self.steamTxCurrency = ""
        self.steamTxAccountStatus = ""

        self.dbUser = None

        self.sessionId = None

        self.loggedIn = False
        self.isAdmin = False

        self.friendNames = []
        self.chatChannels = []

        self.gemEquipSheet = [ -1 ] * 8
        self.itemEquipSheet = [ -1 ] * 4

        self.inventory = None
        self.match = None
        self.readyToPlay = False
        self.selectedHero = 0
        self.matchItemsAndProcsDict = {}

        self.clientVersion = None
        self.clientPlatform = None

        self.loginTime = None
        self.lastActivity = datetime.datetime.now()
        self.status = "Idle"

        self.dbStats = None
        self.refreshFromDb(db)

        self.sentMatchInvites = []

        self.matchInvites = []
        self.friendInvites = []

        self.selectableHeroes = ()
        self.viewableHeroes = ()
