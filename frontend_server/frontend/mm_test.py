import math
import random
import collections
from operator import attrgetter

mm_queue = collections.deque()

MM_RUN_TIME = 60 * 60 * 24  # 24 hours
MINIMUM_WAIT = 20   # in seconds
MAXIMUM_WAIT = 120

QUEUE_WAIT_TIME = 5 # the queue will wait for this long for new players for each new entry

AVG_QUEUE_JOIN_PERIOD = 10   # in seconds

MINIMUM_MEMBERS_PER_TEAM = 2   # leads to 3v3 matches
RANK_SPREAD = ( 6.0, 13.0 )



queue_max_len = 0
entry_add_count = 0
elapsed = 0
next_queue_add = -1
all_created_entries = []
all_matches = []

class MM_Entry(object):
    def __repr__(self):
        return "<MM_Entry: %d, LV %4.2f>" % (self.identifier, self.ladderValue)

    def __init__(self, identifier, add_time, maxwait = 60, ladder_rank = 13.0):
        self.addTime = add_time
        self.identifier = identifier
        self.maxWaitTime = maxwait
        self.ladderValue = ladder_rank

        self.wasMatched = False
        self.totalTimeInQueue = -1

def create_new_match( members ):
    log( "New match created. Queue length is now %d" % (len(mm_queue),))
    match = []
    for m in members:
        m.totalTimeInQueue = elapsed - m.addTime
        m.wasMatched = True
        match.append(m)
    all_matches.append( tuple(match) )

def mm_pass():
    pushback = []
    while len(mm_queue) >= MINIMUM_MEMBERS_PER_TEAM * 2:
        potentials = []
        for i in xrange(0, len(mm_queue)):
            e = mm_queue.pop()
            if elapsed - e.addTime <= QUEUE_WAIT_TIME:
                pushback.append( e )
            else:
                potentials.append( e )
        while len(potentials) >= MINIMUM_MEMBERS_PER_TEAM * 2:
            potentials = sorted( potentials, key=attrgetter("ladderValue") )
            nextmatch = []
            for i in xrange( 0, MINIMUM_MEMBERS_PER_TEAM*2):
                nextmatch.append( potentials.pop() )

            create_new_match( nextmatch )

        for i in xrange(0, len(potentials)):
            pushback.append(potentials[i])

    for pb in pushback:
        mm_queue.append( pb )

def expiry_pass():
    to_remove = []
    for e in mm_queue:
        if (elapsed - e.addTime) >= e.maxWaitTime:
            to_remove.append( e )

    for e in to_remove:
        mm_queue.remove( e )
        e.totalTimeInQueue = (elapsed-e.addTime)
        log( "Removed entry %d after waiting for %d seconds"  % (e.identifier, (elapsed - e.addTime)) )

def log(s):
    hours = math.floor(elapsed / 3600)
    minutes = math.floor( (elapsed / 60) % 60 )
    seconds = elapsed % 60
    print "(%02d:%02d:%02d)  %s" % (hours, minutes, seconds, s)

def add_entry(a):
    global entry_add_count

    entry_add_count += 1
    rank = random.uniform( RANK_SPREAD[0], RANK_SPREAD[1] )
    maxwait = random.randint( MINIMUM_WAIT, MAXIMUM_WAIT )
    log( "Adding new entry (%d) with rank %4.2f maxwait %d" % (entry_add_count, rank, maxwait) )
    e = MM_Entry( entry_add_count, elapsed, maxwait, rank )
    mm_queue.append( e )
    all_created_entries.append( e )

if __name__ == '__main__':
    log( "Starting matchmaking simulation; will run for %d simulated seconds..." % (MM_RUN_TIME, ) )
    log( " * Matchmaking target is %dv%d" % (MINIMUM_MEMBERS_PER_TEAM, MINIMUM_MEMBERS_PER_TEAM) )
    log( " * A new player will join the queue every %d seconds (on average)" % (AVG_QUEUE_JOIN_PERIOD,))
    log( " * New players will wait a minimum of %d up to a maximum of %d seconds for a match" % (MINIMUM_WAIT, MAXIMUM_WAIT))
    log( " * Rank spread is %4.2f - %4.2f" % (RANK_SPREAD[1], RANK_SPREAD[0]))

    while elapsed < MM_RUN_TIME:
        if next_queue_add <= elapsed:
            per_half = AVG_QUEUE_JOIN_PERIOD / 2
            next_queue_add = elapsed + random.randint( 0, AVG_QUEUE_JOIN_PERIOD * 2 )
            add_entry(1)

        expiry_pass()
        mm_pass()
        elapsed += 1

        if len(mm_queue) > queue_max_len:
            queue_max_len = len(mm_queue)

    not_matched_count = 0
    matched_queue_time = 0.0
    everyone_queue_time = 0.0
    for e in all_created_entries:
        if not e.wasMatched:
            not_matched_count += 1
        else:
            matched_queue_time += float( e.totalTimeInQueue )
        everyone_queue_time += float( e.totalTimeInQueue )

    log( "FINISHED")
    log( " * Queue max len was %d" % (queue_max_len,) )
    log( " * %d players seen (%d not matched)" % (entry_add_count, not_matched_count) )
    log( " * %d games created" % (len(all_matches),))
    log( " * Average wait for match %4.2f seconds" % (matched_queue_time / float(len(all_created_entries),)))
    log( " * Average wait (ALL) %4.2f seconds" % (everyone_queue_time / float(len(all_created_entries),)))
