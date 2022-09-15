from datetime import datetime, timedelta
from collections import deque
import random
import UserState

class MatchmakingResult(object):
    def playerCountForTeam(self, team):
        return sum( [g.playerCount for g in self.teams[team]] )

    def teamsFull(self):
        #print "Teamsfull: %d/%d" % (len( self.teams[0] + self.teams[1] ), self.playersPerTeam*2)
        if self.playerCountForTeam(0) + self.playerCountForTeam(1) == self.playersPerTeam * 2:
            return True
        return False

    def addGroup(self, group):
        if not self.canFitGroup(group):
            return

        if self.playerCountForTeam(0) + group.playerCount <= self.playersPerTeam:
            self.teams[0].append( group )
            return

        if self.playerCountForTeam(1) + group.playerCount <= self.playersPerTeam:
            self.teams[1].append( group )
            return


    def canFitGroup(self, group):
        if self.playerCountForTeam(0) + group.playerCount <= self.playersPerTeam:
            return True

        if self.playerCountForTeam(1) + group.playerCount <= self.playersPerTeam:
            return True

        return False

    def __init__(self, players_per_team):
        self.teams = [ [], [] ]
        self.playersPerTeam = players_per_team


class Matchmaker(object):
    def doPass(self):
        # 1) take completes (groups that are of size teamSize/2) and pair all of them together
        # 2) create maximum number of completes from the pool
        # - take first
        # - iterate over rest and fill as you go
        # - if result is complete, complete the result
        # - move on to next one, make sure to iterate from index+1

        if self.passInProgress:  # poor man's locking
            return []

        self.passInProgress = True
        results = []
        q_list = list( self.queue )
        random.shuffle( q_list )   # random order for safety
        for i in xrange( 0, len(q_list) ):
            g = q_list[i]
            if g.playerCount > self.teamSize:
                print "Trying to matchmake for %d players per team but have a group with %d players???  =>  ignored and removed" % (self.teamSize, g.playerCount)
                if g in self.queue:   # for sanity
                    self.queue.remove( g )
                continue

            if g.matchmakingResult is not None:
                continue

            g.passCount += 1
            g.lastPassTime = datetime.now()
            res = MatchmakingResult( self.teamSize )
            res.addGroup( g )

            for j in xrange( 0, len(q_list) ):
                candidate = q_list[j]

                if candidate is g or candidate.matchmakingResult is not None:
                    continue

                if not res.teamsFull():
                    if res.canFitGroup( candidate ):
                        res.addGroup( candidate )
                else:
                    # teams are full so what are we waiting for, this is complete result
                    # TODO we can do ranking adjustment here to drop players we don't want

                    break

            if res.teamsFull():
                for group in res.teams[0] + res.teams[1]:
                    group.matchmakingResult = res
                    group.matchmaker = None
                    group.finishTime = datetime.now()
                    self.addResultTime( (group.finishTime - group.creationTime).seconds )
                    if group in self.queue:
                        self.queue.remove(group)
                results.append( res )
            else:
                g.lastPassEmptySlots = self.gameSize - res.playerCountForTeam(0) - res.playerCountForTeam(1)

        self.totalPasses += 1
        self.lastPassTimestamp = datetime.now()
        self.passInProgress = False
        return results


    def addGroup(self, group):
        assert( group.matchmaker is None )

        group.matchmaker = self
        self.queue.append( group )


    def removeGroup(self, group):
        assert( group.matchmaker is self )

        if group in self.queue:
            self.queue.remove( group )
        group.matchmaker = None

    def addResultTime(self,secs):
        if len(self.resultTimes) > 120:
            self.resultTimes.pop(0)

        self.resultTimes.append( secs )

    def getAverageResultTime(self):
        if len(self.resultTimes) == 0:
            return 0

        return sum(self.resultTimes) / len(self.resultTimes)

    def __init__(self, gameSize):
        self.gameSize = gameSize
        self.teamSize = gameSize / 2
        self.considerRating = False
        self.queue = []
        self.totalPasses = 0
        self.lastPassTimestamp = datetime.now()
        self.passInProgress = False
        self.resultTimes = []



class MatchmakingGroup(object):
    """
    A group of players that need to be matched together. A group of one is fine.
    """
    def removePlayer(self, player):
        if player is self.players:
            self.players.remove(player)

        self.playerCount = len(self.players)

    def addPlayer(self, player):
        assert( type(player) is UserState.UserState )

        if player not in self.players:
            self.players.append( player )
            self.playerCount = len(self.players)


    def __init__(self, players = None):
        self.creationTime = datetime.now()
        self.lastPassTime = datetime.now()
        self.finishTime = None
        self.matchmakingResult = None
        self.playerCount = 0
        self.players = []   # actual UserState entries
        self.passCount = 0
        self.lastPassEmptySlots = -1
        self.rankSpread = 1.0  # the rank spread for this group (in both directions)
        self.matchmaker = None   # the matchmaker that we are using

        if players is not None and len(players) > 0:
            [self.addPlayer(p) for p in players]



if __name__ == "__main__":
    # some test stuff
    mm = Matchmaker( 6 )

    for i in range( 0, 10 ):
        mg = MatchmakingGroup()
        mg.playerCount = random.randint( 1, 3 )
        mm.addGroup(mg)

    print "Queue length at start %d" % (len(mm.queue),)
    results = mm.doPass()
    for r in results:
        print str(r)
        print "TEAM 0: "
        for g in r.teams[0]:
            print "  Group with %d players" % (g.playerCount,)
        print "TEAM 1: "
        for g in r.teams[1]:
            print "  Group with %d players" % (g.playerCount,)
    print "Queue length at end %d" % (len(mm.queue),)
