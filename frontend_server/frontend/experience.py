experience_per_win = 250.0
experience_per_loss = 150.0

performance = "lllllwwwwwllwwllwlwllwwwllwwllwlwllwwwllww"

avg_time_per_match = 15.0 * 60.0  # in seconds

max_level = 30


level_wins = ( 0,  # initial zero since we start from level 1
               0.25, 1.0, 1.50, 2, 3, 3.75, 4.5, 5.0, 6.0, 6.5,   # 1-11
               7.0, 7.5, 8.0, 8.5, 9.5, 10.5, 12.5, 13.5, 14.0, 14.5, # 11-21
               16.0, 17.0, 18.0, 19.0, 20.0, 22.0, 23.5, 24.5, 25.5, 27 )  # 21-30 + 1st prestige


level_limits = []
req_exp_per_level = []

s = 0
for i in range( 0, 30 ):
    s += level_wins[i] * experience_per_win
    req_exp_per_level.append( level_wins[i] * experience_per_win )
    level_limits.append( int(s) )

prestige_req = int( req_exp_per_level[ -1 ] * 1.25 )

for i in range( 1, 30 ):
    print "Level %d-%d requires %d experience (%4.2f wins)" % ( i, i+1, req_exp_per_level[i], req_exp_per_level[i] / experience_per_win )

print "Experience cap at %4.2f total %4.2f wins required" % (sum(req_exp_per_level), sum(level_wins))
print "Guesstimated minimum play time %4.2f hours" % (((sum(req_exp_per_level) / experience_per_win) * avg_time_per_match) / 60.0 / 60.0, )
print "%d experience required per prestige level (%4.2f wins)" % (prestige_req, prestige_req / experience_per_win)

print "Progression for performace %s:" % (performance,)
exp = 0
level = 1
totgames = 0
for i in range(0, len(performance)):
    result = performance[i]
    if result == 'l':
        res_str = "loss"
        gain = experience_per_loss

    if result == 'w':
        res_str = "win"
        gain = experience_per_win


    exp += gain
    totgames += 1

    print "Game %d ends in %s total experience %d/%d" % (i+1, res_str, exp, level_limits[level])

    while exp >= level_limits[level]:
        level += 1
        print "  DING level %d!" % (level, )


print "Ended at level %d after %d games; approx %4.2f mins played" % (level, totgames, (totgames * avg_time_per_match) / 60.0)
print level_limits