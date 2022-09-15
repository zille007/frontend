from hashlib import md5
from binascii import hexlify
from database import User, UserSession, MatchRequest, LogEntry
from datetime import datetime
from sqlalchemy import func
from inventory import grant_random_item_to_user, equip_item_for_user

def new_user( db, username, password, screenname, clantag, email, all_gems, all_items ):
    # TODO: salt these

    c = db.query(User).count() + 1

    if len(username) < 3 or len(password) < 5 or len(screenname) < 5:
        return False

    u = User( username )
    u.id = 60 + 30 + c
    u.password_hash = md5( password ).hexdigest()
    u.screenname = screenname
    u.clantag = clantag
    u.email = email
    u.allow_login = True
    u.account_type = 0
    u.rating = 1500

    db.add( u )
    db.commit()

    tier_1_gems = []
    for g in all_gems:
        #if g["tier"] == 1 and g.has_key( "gem_id"):
        tier_1_gems.append( g["gem_id"] )

    tier_1_items = []
    for i in all_items:
        #if i["tier"] == 1 and i.has_key( "item_id"):
        tier_1_items.append( i["item_id"] )

    #grant_random_item_to_user( db, u, "item", tier_1_items )
    #grant_random_item_to_user( db, u, "item", tier_1_items )
    #grant_random_item_to_user( db, u, "item", tier_1_items )
    #grant_random_item_to_user( db, u, "item", tier_1_items )
    #grant_random_item_to_user( db, u, "gem", tier_1_gems )
    #grant_random_item_to_user( db, u, "gem", tier_1_gems )
    #grant_random_item_to_user( db, u, "gem", tier_1_gems )
    #grant_random_item_to_user( db, u, "gem", tier_1_gems )

    return True

def grant_initial_items( db, u, all_items ):
    tier_1_items = []
    for i in all_items:
        if i["level"] == 1 and i.has_key( "item_id"):
            tier_1_items.append( i["item_id"] )

    i  = grant_random_item_to_user( db, u, "item", tier_1_items )
    i2 = grant_random_item_to_user( db, u, "item", tier_1_items )
    i3 = grant_random_item_to_user( db, u, "item", tier_1_items )
    i4 = grant_random_item_to_user( db, u, "item", tier_1_items )

    equip_item_for_user( db, u, "item", i.id, 0 )
    equip_item_for_user( db, u, "item", i2.id, 1 )
    equip_item_for_user( db, u, "item", i3.id, 2 )
    equip_item_for_user( db, u, "item", i4.id, 3 )



def new_user_steam( db, steamid, persona ):
    c = db.query(User).count() + 1
    u = User( "steam:%s" % (steamid,) )
    u.id = c + 100
    u.password_hash = "nonmatching_hash"
    u.steam_id = steamid
    u.screenname = persona
    u.clantag = ""
    u.email = ""
    u.allow_login = True
    u.account_type = 1
    u.rating = 1500

    return u

def new_user_ios( db, ipad_vendorid, screenname ):
    c = db.query(User).count() + 1
    u = User( "ios:%s" % (ipad_vendorid,))
    u.id = c + 100
    u.password_hash = "nonmatching_hash"
    u.screenname = screenname
    u.clantag = ""
    u.email = ""
    u.alloc_login = True
    u.account_type = 2
    u.rating = 1500

    return u

def create_session( db, sess_id, user_id = -1 ):
    sess = UserSession( user_id, sess_id )
    db.add( sess )
    db.commit()

    return sess

def delete_session( db, sess_id ):
    q = db.query( UserSession ).filter_by( session_id = sess_id ).first()
    db.delete( q )
    db.commit()

def get_session( db, sess_id ):
    return db.query( UserSession ).filter_by( session_id = sess_id ).first()

def get_session_for_user( db, user_or_username ):
    user = user_or_username
    if user_or_username is str:
        user = db.query( User ).filter_by( username=user_or_username ).first()

    if user is None:
        return None

    q = db.query( UserSession ).filter_by( user_id=user.id )

    if q.count() == 0:
        return None

    return q.first()

def get_user_for_session( db, session ):
    q = db.query( User ).filter_by( id = session.user_id )
    return q.first()

def update_session( db, sess_id ):
    sess = db.query( UserSession ).filter_by( session_id = sess_id ).first()
    now = datetime.now()
    if sess is None:
        return False

    #if  (now - sess.created).seconds > 300:
    #    db.delete( sess )
    #    db.commit()
    #    return False

    return True


def authenticate( db, username, hash ):
    user = db.query( User ).filter_by( username=username ).first()
    if user is not None:
        print "auth for user %s with hash %s (got %s)" % (username, hash, user.password_hash)
        if user.password_hash == hash:
            return user

    return None

