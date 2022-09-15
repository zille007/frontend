from gevent import monkey; monkey.patch_all()

from FrontendConfig import *
from binascii import hexlify
from datetime import datetime
from database import User, Match, MatchRequest, MatchResult, FriendAssociation, GameInvite, MatchBasicInfo, MatchPlayerInfo
from inventory import equipsheet_with_names, equipsheet_with_names_for_user
import MatchEntry
import telnetlib
import random
import json

def match_had_ai_players( db, match_id ):
        mpis = db.query( MatchPlayerInfo ).filter( MatchPlayerInfo.match_id == match_id )
        have_ais = False
        for mpi in mpis:
            if not mpi.human:
                have_ais = True
                break

        return have_ais


def clear_matchreqs_for_user( db, user ):
    print "Clearing match requests for user %s" % (user.username,)
    reqs = db.query( MatchRequest ).filter_by( user_id = user.id )
    reqs.delete()
    db.commit()

def match_for_id( db, match_id ):
    try:
        res = db.query( Match ).filter_by( id = match_id ).one()
    except Exception:
        return None
    return res

def matchresults_for_token( db, token ):
    try:
        res = db.query( MatchResult ).filter_by( match_token = token ).all()
    except Exception:
        return None
    return res

def matchresult_for_user( db, user, token ):
    try:
        req = db.query( MatchResult ).filter_by( user_id = user.id, match_token = token ).one()
    except Exception:
        return None
    return req

def matchrequest_for_user( db, user, status_in=2 ):
    try:
        req = db.query( MatchRequest ).filter_by( user_id = user.id ).one()
    except Exception:
        return None
    return req

def create_matchrequest( db, user, map_pref ):
    mr = MatchRequest( user.id )
    mr.map_preference = map_pref
    mr.skill_hint = user.rating
    mr.status = 0
    #mr.found_match_id = 13

    db.add( mr )
    db.commit()

    return mr

def matchpair_1v1( db, request_a, request_b ):
    pass

def matchmaking_score_pair( request_a, request_b ):
    return abs( request_a.skill_hint - request_b.skill_hint )


def matchmaking_pass( db, all_items, all_gems, user_equip_sheet_dict ):
    maps = ALLOWED_MAPS

    unresolved = db.query( MatchRequest ).filter( MatchRequest.status < 2, MatchRequest.gametype=='1v1', MatchRequest.controltype=='master' ).all()
    if len(unresolved) > 1:
        # pair the first two, do the others on next pass

        a = unresolved[0]
        b = unresolved[1]

        user_a = db.query( User ).filter_by( id = a.user_id ).first()
        user_b = db.query( User ).filter_by( id = b.user_id ).first()

        d = { user_a.username:equipsheet_with_names_for_user( db, user_a, all_items, all_gems ) ,
              user_b.username:equipsheet_with_names_for_user( db, user_b, all_items, all_gems ) }

        user_dict = { user_a.username:user_a.id, user_b.username:user_b.id}

        match = create_match( db, 0, maps[random.randint(1,2)-1], 2, 4, 2, d, user_dict)
        mr_a = MatchResult( a.user_id, match.token, 'in_progress')
        mr_b = MatchResult( b.user_id, match.token, 'in_progress')

        db.add( mr_a )
        db.add( mr_b )

        a.found_match_id = match.id
        b.found_match_id = match.id
        a.status = 2
        b.status = 2
        db.commit()

    masters = db.query( MatchRequest ).filter( MatchRequest.status < 2, MatchRequest.gametype == '2v2', MatchRequest.controltype == 'master' ).all()
    heroes = db.query( MatchRequest ).filter( MatchRequest.status < 2, MatchRequest.gametype == '2v2', MatchRequest.controltype == 'hero').all()
    if len(masters) > 1 and len(heroes) > 1:
        # pair the first entries from masters and heroes
        m1 = masters[0]
        m2 = masters[1]
        h1 = heroes[0]
        h2 = heroes[1]
        user_m1 = db.query( User ).filter_by( id = m1.user_id ).first()
        user_m2 = db.query( User ).filter_by( id = m2.user_id ).first()
        user_h1 = db.query( User ).filter_by( id = h1.user_id ).first()
        user_h2 = db.query( User ).filter_by( id = h2.user_id ).first()

        d = { user_m1.username:equipsheet_with_names_for_user( db, user_m1, all_items, all_gems ),
              user_m2.username:equipsheet_with_names_for_user( db, user_m2, all_items, all_gems ),
              user_h1.username:equipsheet_with_names_for_user( db, user_h1, all_items, all_gems ),
              user_h2.username:equipsheet_with_names_for_user( db, user_h2, all_items, all_gems )
        }

        match = create_match( db, 0, maps[random.randint(1,2)-1], 4, 4, 2, d )

        m1_mr = MatchResult( m1.user_id, match.token, 'in_progress' )
        m2_mr = MatchResult( m2.user_id, match.token, 'in_progress' )
        h1_mr = MatchResult( h1.user_id, match.token, 'in_progress' )
        h2_mr = MatchResult( h2.user_id, match.token, 'in_progress' )

        m1.found_match_id = match.id
        m2.found_match_id = match.id
        h1.found_match_id = match.id
        h2.found_match_id = match.id
        m1.status = 2
        m2.status = 2
        h1.status = 2
        h2.status = 2

        db.commit()

def user_equip_sheet_dict_for_user( db, user ):
    pass

def matchmake_friends_1v1( db, all_items, all_gems ):
    maps = ALLOWED_MAPS

    unresolved = db.query( GameInvite ).filter( GameInvite.accepted == True, GameInvite.game_created == False ).all()
    for invite in unresolved:
        user_a = db.query( User ).filter_by( id = invite.receiver_user_id ).first()
        user_b = db.query( User ).filter_by( id = invite.sender_user_id ).first()

        # create a match first, THEN the match requests so matchmaking_pass above won't start fucking with them
        d = { user_a.username:equipsheet_with_names_for_user( db, user_a, all_items, all_gems ),   # user_equip_sheet_dict[user_a.username] ),
              user_b.username:equipsheet_with_names_for_user( db, user_b, all_items, all_gems ) }  # user_equip_sheet_dict[user_b.username] ) }

        user_dict = { user_a.username:user_a.id, user_b.username:user_b.id}
        match = create_match( db, 0, maps[random.randint(1,2)-1], 2, 4, 2, d, user_dict )

        if match is not None:
            req_a = MatchRequest( invite.receiver_user_id )
            req_a.found_match_id = match.id
            req_a.status = 2
            req_a.controltype = "master"
            req_a.gametype = "1v1"

            req_b = MatchRequest( invite.sender_user_id )
            req_b.found_match_id = match.id
            req_b.status = 2
            req_b.controltype = "master"
            req_b.gametype = "1v1"

        invite.game_created = True
        invite.match_token  = match.token

        mr_a = MatchResult( invite.receiver_user_id, match.token, 'in_progress')
        mr_b = MatchResult( invite.sender_user_id, match.token, 'in_progress')

        db.add( match )
        db.add( req_a )
        db.add( req_b )
        db.add( mr_a )
        db.add( mr_b )


    db.commit()

def create_1v1_match_with_users( db, token, all_items, all_gems, user_a, user_b ):
    maps = ALLOWED_MAPS

    # create a match first, THEN the match requests so matchmaking_pass above won't start fucking with them
    d = { user_a.username:equipsheet_with_names_for_user( db, user_a, all_items, all_gems ),   # user_equip_sheet_dict[user_a.username] ),
          user_b.username:equipsheet_with_names_for_user( db, user_b, all_items, all_gems ) }  # user_equip_sheet_dict[user_b.username] ) }

    user_dict = { user_a.username:user_a.id, user_b.username:user_b.id}
    match = create_match( db, 0, maps[random.randint(1,2)-1], 2, 4, 2, d, user_dict, token )

    if match is not None:
        req_a = MatchRequest( user_a.id )
        req_a.found_match_id = match.id
        req_a.status = 2
        req_a.controltype = "master"
        req_a.gametype = "1v1"

        req_b = MatchRequest( user_b.id )
        req_b.found_match_id = match.id
        req_b.status = 2
        req_b.controltype = "master"
        req_b.gametype = "1v1"

    mr_a = MatchResult( user_a.id, match.token, 'in_progress')
    mr_b = MatchResult( user_b.id, match.token, 'in_progress')

    db.add( match )
    db.add( req_a )
    db.add( req_b )
    db.add( mr_a )
    db.add( mr_b )


    db.commit()


def create_match_with_users( db, token, users, all_items, all_gems, difficulty="medium" ):
    maps = ALLOWED_MAPS
    # only allow 1, 2 or 4 users in the users list

    if len(users) != 1 and len(users) != 2 and len(users) != 4:
        return False

    match_type = ( "NONE", "single", "1v1", "NONE", "2v2" )[len(users)]

    d = {}
    user_dict = {}
    control_dict = {}
    i = 0
    for u in users:
        d[u.username] = equipsheet_with_names_for_user( db, u, all_items, all_gems )
        user_dict[u.username] = u.id
        control_dict[u.username] = "master" if i < 2 else "hero"
        i += 1

    match = create_match( db, 0, maps[random.randint(1,2)-1], len(users), 4, 2, d, user_dict, token, control_dict, difficulty )
    if match is not None:
        for u in users:
            req = MatchRequest( u.id )
            req.found_match_id = match.id
            req.status = 2
            req.controltype = control_dict[ u.username ]  #for now, need to clear this properly for 2v2
            req.gametype = match_type

            res = MatchResult( u.id, token, "in_progress" )

            db.add( res )
            db.add( req )
    db.commit()

def create_match_new( db, map_name, token, matchentry, all_items, all_gems, isTutorial = False ):
    server_choice = random.randint( 0, len( BACKEND_SERVERS )-1 )

    match = Match( map_name, 0 )
    match.map = map_name
    match.server_id = server_choice
    match.creation_time = datetime.now()
    match.token = matchentry.token
    db.add( match )
    db.commit()

    bi = MatchBasicInfo( match.id, matchentry.typeString(), 400, 0 )
    db.add( bi )
    db.commit()

    playerConfig = {}
    humans = []
    c = 0
    for team in range( 1, 3 ):
        t = matchentry.teams[team]
        playerConfig[team] = []
        ai_count = 0
        for i in range( 0, len(t) ):
            player = t[i]
            if player is not None:
                if isinstance( player, MatchEntry.MatchAIPlayer ):
                    ai_count += 1
                    playerConfig[team].append( ( "ai", "master" if i == 0 else "hero", player.difficulty, player.selectedHero, -1, c, { "item":[], "procs":[] } ) )
                    pi = MatchPlayerInfo( match.id, -1, "AI %d (%s)" % (ai_count, player.difficulty), team, 13.0 )
                    pi.hero = player.selectedHero
                    pi.human = False
                    pi.role = "master" if i == 0 else "hero"
                    pi.player_match_index = c
                    db.add( pi )
                else:

                    player_equips = player.matchItemsAndProcsDict # equipsheet_with_names_for_user( db, player.dbStats, all_items, all_gems )

                    # ULTRA HACK 4000: check if user has item 61 (the celestial duck item) and if so, monkey patch
                    # the increase into it
                    # "=Abilities.Summon.Summon unit" : "Celestial wolf"
                    #items = player_equips["item"]
                    #for it in items:
                    #    print it
                    #    if it["type_id"] == 61:
                    #        it["increases"]["hero"]["=Abilities.Summon.Summon unit"] = "Celestial wolf"

                    print "Player equips for player %s: %s" % (player.username, str(player_equips))
                    playerConfig[team].append( ( "human", "master" if i == 0 else "hero", player.screenname, player.selectedHero, player.id, c, player_equips ) )
                    humans.append( (player, "master" if i == 0 else "hero") )
                    pi = MatchPlayerInfo( match.id, player.id, player.screenname, team, player.dbStats.ladder )
                    pi.hero = player.selectedHero
                    pi.role = "master" if i == 0 else "hero"
                    pi.player_match_index = c
                    pi.human = True
                    db.add(pi)
                c += 1

    print "Creating %smatch; backend at %s:%s; playerConfig=%s" % ("TUTORIAL " if isTutorial else "", BACKEND_SERVERS[server_choice][0], BACKEND_SERVERS[server_choice][1], str(playerConfig) )

    srv = telnetlib.Telnet( BACKEND_SERVERS[server_choice][0], BACKEND_SERVERS[server_choice][1] )
    srv.write( '{ "cmd":"AUTH", "data":{ "user":"%s", "password":"%s" }}\r\n' % (BACKEND_SERVERS[server_choice][2], BACKEND_SERVERS[server_choice][3]) )
    srv.read_until( "AUTH_RES" )

    srv.write( '{ "cmd":"FE_MATCH_SETUP", "data":{ "token":"%s", "map_name":"%s", "playerConfig":%s, "tutorial":%s }}\r\n'
               % (str(token), str(map_name), json.dumps(playerConfig), str(isTutorial).lower()  ) )

    srv.close()
    match.status = 1
    db.commit()

    for p,control in humans:
        req = MatchRequest( p.id )
        req.found_match_id = match.id
        req.status = 2
        req.controltype = control
        req.gametype = "custom"

        res = MatchResult( p.id, token, "in_progress" )

        db.add( req )
        db.add( res )
    db.commit()

    return match



def create_match( db, server_id, map_name, req_players = 2, player_limit = 4, team_max = 2, item_dict = {}, allowed_user_dict = {}, use_token = '', user_control_dict = {}, ai_difficulty="easy" ):
    match = Match( map_name, 0 )
    match.map = map_name
    match.server_id = 0
    match.creation_time = datetime.now()
    if use_token != '':
        match.token = use_token
    db.add( match )
    db.commit()

    print "Creating match; backend at %s:%s; item_dict=%s" % (BACKEND_SERVERS[0][0], BACKEND_SERVERS[0][1], str(item_dict))

    # do external req (this is very, VERY bad, but lets go with this for now...)
    srv = telnetlib.Telnet( BACKEND_SERVERS[0][0], BACKEND_SERVERS[0][1] )
    srv.write( '{ "cmd":"AUTH", "data":{ "user":"%s", "password":"%s" }}\r\n' % (BACKEND_SERVERS[0][2], BACKEND_SERVERS[0][3]) )
    srv.read_until( "AUTH_RES" )

    srv.write( '{ "cmd":"FE_MATCH_CREATE", "data":{ "token":"%s", "map_name":"%s", "req_players":%d, "player_limit":%d, "team_max":%d, "item_dict":%s, "allowed_users":%s, "user_control":%s, "ai_difficulty":"%s" }}\r\n' %
               ( str(match.token), str(match.map), req_players, player_limit, team_max, str(json.dumps(item_dict)), str(json.dumps(allowed_user_dict)), str(json.dumps( user_control_dict )), str(ai_difficulty) ) )

    srv.close()

    match.status = 1
    db.commit()
    return match


