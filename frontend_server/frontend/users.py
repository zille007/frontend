from database import User, UserStats, UserStatEvent, FriendAssociation, Achievement, MatchResult, UserPossession, ShopSKU

def write_log( db, user, entry_type, extra_data="" ):
    l = LogEntry( user.id, entry_type, extra_data )
    db.add( l )
    db.commit()

def user_create_stats( db, user ):
    if user is None:
        print "Cant create stats for a null user!"
        return

    stats = UserStats( user.id )
    db.add( stats )
    db.commit()

    return stats

def user_stats_for_user( db, user ):
    q = db.query( UserStats ).filter_by( user_id = user.id ).first()

    if q is None:
        return user_create_stats( db, user )

    return q

def eligible_postmatch_achievements( db, user, stats_dict ):
    if not stats_dict.has_key( user.username ):
        return []

    achs = []
    wins, losses = user_winloss_count( db, user )
    stats = user_stats_for_user( db, user )

    if wins >= 1:
        achs.append( "1-win")
    if wins >= 3:
        achs.append( "3-wins" )
    if wins >= 5:
        achs.append( "5-wins" )
    if wins >= 10:
        achs.append( "10-wins" )
    if wins >= 25:
        achs.append( "25-wins" )
    if wins >= 50:
        achs.append( "50-wins" )
    if wins >= 100:
        achs.append( "100-wins" )

    tk = stats_dict[ user.username ][ "total_kills" ] if stats_dict[user.username].has_key( "total_kills" ) else None
    if tk is not None:
        kills = int( stats_dict[ user.username ][ "total_kills" ] ) if stats_dict[user.username].has_key( "total_kills" ) else 0
        if kills >= 1:
            achs.append( "match-1-kill")
        if kills >= 3:
            achs.append( "match-3-kills" )
        if kills >= 5:
            achs.append( "match-5-kills" )
        if kills >= 10:
            achs.append( "match-10-kills" )
        if kills >= 25:
            achs.append( "match-25-kills" )

    level = stats_dict[ user.username ]["level"] if stats_dict[user.username].has_key( "level" ) else 1
    if level is not None:
        level = int(level)
        if level >= 2:
            achs.append( "leveled-up")
        if level >= 5:
            achs.append( "match-level-5" )
        if level >= 10:
            achs.append( "match-level-max" )


    tix = stats_dict[ user.username ]["team_tickets"] if stats_dict[user.username].has_key( "team_tickets" ) else 0
    if tix is not None:
        if tix == 400:
            achs.append( "perfect-win" )

    totalgames = wins+losses
    if totalgames >= 1:
        achs.append( "finished-game" )
    if totalgames >= 10:
        achs.append( "10-games" )
    if totalgames >= 20:
        achs.append( "20-games" )
    if totalgames >= 50:
        achs.append( "50-games" )
    if totalgames >= 100:
        achs.append( "100-games" )

    if stats.xp_level >= 2:
        achs.append( "first-player-level-up" )
    if stats.xp_level >= 5:
        achs.append( "player-level-5")
    if stats.xp_level >= 10:
        achs.append( "player-level-10")
    if stats.xp_level >=  15:
        achs.append( "player-level-15" )
    if stats.xp_level >= 20:
        achs.append( "player-level-20" )
    if stats.xp_level >= 25:
        achs.append( "player-level-25" )
    if stats.xp_level >= 30:
        achs.append( "player-level-max" )

    return achs


def hard_money_for_achievement( achievement ):
    d = {
          "1-win":10,
          "3-wins":10,
          "5-wins":10,
          "10-wins":10,
          "25-wins":10,
          "50-wins":10,
          "100-wins":10,
          "match-1-kill":10,
          "match-3-kills":10,
          "match-5-kills":10,
          "match-10-kills":10,
          "match-25-kills":10,
          "leveled-up":10,
          "match-level-5":10,
          "match-level-max":10,
          "perfect-win":10,
          "finished-game":10,
          "10-games":10,
          "20-games":10,
          "50-games":10,
          "100-games":10,
          "first-player-level-up":10,
          "player-level-5":10,
          "player-level-10":10,
          "player-level-15":10,
          "player-level-20":10,
          "player-level-25":10,
          "player-level-max":10
    }

    if achievement in d.keys():
        return d[achievement]

    return 0



def user_can_complete_achievement( db, user, achievement ):
    repeatable = ( "ach", "minutes-per-completion" )
    achs = user_get_achievements( db, user )
    pass

def user_get_achievement_state( db, user, achievement ):
    achs = db.query( Achievement ).filter_by( user_id = user.id, achievement_name = achievement ).all()
    if len(achs) == 0:
        return None

    return achs[0]

def user_get_achievements( db, user ):
    q = db.query( Achievement ).filter_by( user_id = user.id ).all()

    return q

def user_inventory_for_user( db, user ):
    pass

def user_grant_shop_item( db, user, item_id, description="" ):
    pass

def user_winloss_count( db, user ):
    matches = db.query( MatchResult ).filter( MatchResult.user_id == user.id ).all()
    won = 0
    lost = 0
    for m in matches:
        if m.result == "won":
            won += 1
        if m.result == "lost":
            lost += 1
    return (won, lost)

def xp_required_for_level( exp_level ):
    level_limits = [0,
                    212,  462, 837, 1337,  2087, 3025, 4150, 5400, 6900, 8525,
                    10275,  12150,  14150,  16275,  18650,  21275,  24400,  27775, 31275,  34900,
                    38900,  43150,  47650,  52400,  57400,   62900,   68775,   74900,  81275]

    prestige_exp_req = 7968
    if exp_level <= 0:
        return 0

    if exp_level >= len(level_limits):
        return level_limits[-1] + (prestige_exp_req * (exp_level - len(level_limits)))

    return level_limits[ exp_level ]


def level_limit_for_exp( exp ):
    level_limits = [0,
                    212,  462, 837, 1337,  2087, 3025, 4150, 5400, 6900, 8525,
                    10275,  12150,  14150,  16275,  18650,  21275,  24400,  27775, 31275,  34900,
                    38900,  43150,  47650,  52400,  57400,   62900,   68775,   74900,  81275]
    prestige_exp_req = 7968

    i = 0
    while i < len(level_limits) and exp >= level_limits[i]:
        i += 1

    if i >= len(level_limits):
        last = level_limits[-1]
        next_prestige_level = ((exp-last) / prestige_exp_req) + 1
        return last + (prestige_exp_req * next_prestige_level)
        #return level_limits[-1] + (i - len(level_limits)) * prestige_exp_req

    return level_limits[i]


def user_potentially_grant_new_character( db, user, level_override=None ):
    if level_override is None:    
        level = user.dbStats.xp_level
    else:
        level = level_override
    chargrants = [ (2, "Sniper"), (5, "Beaver"), (10, "Stone elemental"), (15, "Fyrestein"), (20, "Rogue") ]
    didGrants = False
    for cg in chargrants:
        cg_level, char = cg
        if cg_level <= level:
            print "User %s will potentially gain character %s..." % (user.username, char)
            # see if the user already has this char
            q = db.query( UserPossession ).filter( UserPossession.user_id == user.id, UserPossession.p_type == "character", UserPossession.p_item == char ).first()
            if q is None:
                print "User did not have level up character %s, granting it..." % (char,)
                newchar = UserPossession( user.id, "character", char, "Leveled up to level %d" % (level,) )
                db.add( newchar )
                didGrants = True
            else:
                print "User already has this character; not granting."
    return didGrants

def user_grant_experience( db, user, xp_amount, match_token = "", description=""):
    assert( user is not None )

    level_limits = [0,
                    212,  462, 837, 1337,  2087, 3025, 4150, 5400, 6900, 8525,
                    10275,  12150,  14150,  16275,  18650,  21275,  24400,  27775, 31275,  34900,
                    38900,  43150,  47650,  52400,  57400,   62900,   68775,   74900,  81275]
    prestige_exp_req = 7968

    stats = user_stats_for_user( db, user )

    oldxp = stats.xp_current
    newxp = oldxp + xp_amount
    level = stats.xp_level
    limit = level_limits[ level ] if level < len(level_limits) else level_limits[-1] + (prestige_exp_req * (level - len(level_limits)))

    e = UserStatEvent( user.id, "xp_current", "inc", xp_amount, oldxp )
    e.match_token = match_token
    e.description = description
    db.add( e )

    didLevelUp = False
    if newxp >= limit:
        # grant level
        oldlevel = level
        oldlimit = level_limits[ level ] if level < len(level_limits) else level_limits[-1] + (prestige_exp_req * (level - len(level_limits)))
        level += 1
        limit = level_limits[ level ] if level < len(level_limits) else level_limits[-1] + (prestige_exp_req * (level - len(level_limits)))
        e2 = UserStatEvent( user.id, "xp_level", "inc", 1, oldlevel )
        e2.match_token = match_token
        e2.description = description

        e3 = UserStatEvent( user.id, "xp_next", "assign", limit, oldlimit )
        e3.match_token = match_token
        e3.description = description + ", level up"
        db.add( e2 )
        db.add( e3 )

        didLevelUp = True
        # potential character grant

    stats.xp_current = newxp
    stats.xp_next = limit
    stats.xp_level = level

    if didLevelUp:
        user_potentially_grant_new_character( db, user, level )

    db.commit()
    return didLevelUp


def user_modify_ladder_value( db, user, ladder_modifier, match_token = "", description = "" ):
    assert( user is not None )

    stats = user_stats_for_user( db, user )
    oldladder = stats.ladder_value
    stats.ladder_value += ladder_modifier

    if stats.ladder_value > 13.0:
        stats.ladder_value = 13.0

    if stats.ladder_value < 1.0:
        stats.ladder_value = 1.0

    e = UserStatEvent( user.id, "ladder_value", "change", ladder_modifier, oldladder )
    e.match_token = match_token
    e.description = description
    db.add( e )
    db.commit()

def user_modify_rating( db, user, rating_modifier, match_token = "", description=""):
    assert( user is not None )

    stats = user_stats_for_user( db, user )
    oldrating = stats.rating
    stats.rating += rating_modifier

    e = UserStatEvent( user.id, "rating", "change", rating_modifier, oldrating )
    e.match_token = match_token
    e.description = description
    db.add( e )
    db.commit()


def user_grant_soft_money( db, user, count, match_token = "", description=""):
    assert( user is not None )

    stats = user_stats_for_user( db, user )

    oldvalue = stats.soft_money
    stats.soft_money += count

    e = UserStatEvent( user.id, "soft_money", "inc", count, oldvalue )
    e.match_token = match_token
    e.description = description
    db.add( e )
    db.commit()


def user_grant_hard_money( db, user, count, match_token = "", description=""):
    assert( user is not None )

    stats = user_stats_for_user( db, user )

    oldvalue = stats.hard_money
    stats.hard_money += count
    e = UserStatEvent( user.id, "hard_money", "inc", count, oldvalue )
    e.match_token = match_token
    e.description = description

    db.add( e )
    db.commit()
    pass

def user_deduct_hard_money( db, user, count, description="", match_token = "" ):
    pass

def user_deduct_soft_money( db, user, count, description="", match_token = ""):
    assert( user is not None )

    stats = user_stats_for_user( db, user )

    if count > stats.soft_money:
        print "WARNING: wanted to set negative soft money for user %s" % (user.username,)
        error_e = UserStatEvent( user.id, "soft_money", "negative_result", stats.soft_money - count )
        error_e.description = "NEGATIVE AMOUNT: " + description
        db.add( error_e )
        count = stats.soft_money

    oldvalue = stats.soft_money
    stats.soft_money -= count

    e = UserStatEvent( user.id, "soft_money", "dec", count, oldvalue )
    e.match_token = match_token
    e.description = description
    db.add( e )
    db.commit()
    pass

def user_get_friends( db, user ):
    #assert( user is not None )

    try:
        friend_assocs = db.query( FriendAssociation ).filter( FriendAssociation.user_id == user.id ).all()
        friends = []

        if friend_assocs is not None:
            print "Got %d friends for user %s" % (len(friend_assocs), user.username)
            for assoc in friend_assocs:
                u = db.query( User ).filter( User.id == assoc.friend_id ).one()
                friends.append( u )

        return friends
    except Exception as e:
        print e.message

    return None

def user_is_friends_with( db, user, friend_id ):
    try:
        friend_test = db.query( FriendAssociation ).filter( FriendAssociation.user_id == user.id, FriendAssociation.friend_id == friend_id ).first()
        if friend_test is not None:
            return True

        return False
    except Exception as e:
        print "Exception in user_is_friends_with: "+e.message

    return False

def elo_to_rank( rating ):
    rankstr =   [ "D+", "C-", "C",  "C+", "B-", "B",  "B+", "A-", "A", "A+", "S-", "S", "S+", "SS", "SSS" ]
    ranklimit = [ 1400, 1450, 1500, 1525, 1550, 1575, 1600, 1650,1700, 1750, 1800, 1850, 1900, 1950, 2000 ]

    if rating <= ranklimit[0]:
        return rankstr[0]

    ret = ""
    for i in range( 0, len(ranklimit) ):
        if rating >= ranklimit[i]:
            ret = rankstr[i]
        else:
            break

    return ret

def user_elo_to_rank( db, user ):

    stats = user_stats_for_user( db, user )
    rating = stats.rating

    return elo_to_rank( rating )


def user_grant_shop_sku( db, user, sku_id, grant_description = "" ):
    skuid_to_character_map = {
        "CHARACTER-BEAVER": "Beaver",
        "CHARACTER-FYRE": "Fyrestein",
        "CHARACTER-ALCHEMIST": "Alchemist",
        "CHARACTER-STONE": "Stone elemental",
        "CHARACTER-ROGUE": "Rogue"
    }

    sku = db.query( ShopSKU ).filter_by( id = sku_id ).one()
    if sku is not None:
        if sku.category == "character" and skuid_to_character_map.has_key( sku.sku_internal_identifier ):
            c = skuid_to_character_map[ sku.sku_internal_identifier ]
            newchar = UserPossession( user.id, "character", c, grant_description )
            db.add( newchar )
            db.commit()
        else:
            print "Want to grant SKU %s with category %s but don't know how to handle it!" % (sku.sku_internal_identifier, sku.category)
            raise Exception( "" )

