__version__ = '1.0'

from bottle import request, response
from hashlib import sha1
from os import urandom
from time import time
from binascii import hexlify
from collections import defaultdict
from userauth import get_session, update_session, get_user_for_session, create_session, delete_session
import UserState


_data = defaultdict(dict)
_users = defaultdict(dict)

def getUsersDictItems():
    return _users.items()

def getUserById( id ):
    return _users[id]

def removeUserById( id ):
    #destroySessionWithId( _users[id].sessionId )
    del _users[id]

def setUserById( id, state ):
    print "Setting user %d: %s" % (id,state)
    _users[id] = state

def start(func):
    'Creates a new session or accesses an existing one.'

    def wrapper(*a, **k):
        db = k["db"]
        user = None
        sess = None

        try:
            try:
                remote_addr = request["REMOTE_ADDR"]
            except:
                remote_addr = "127.0.0.1"

            if request.get_cookie('PYSESSID') is None:
                sid = hexlify(urandom(32))
                response.set_cookie('PYSESSID', sid)
                sid = sha1('%s%s' % (sid, remote_addr)).hexdigest()
            else:
                sid = request.get_cookie('PYSESSID')
                sid = sha1('%s%s' % (sid, remote_addr)).hexdigest()
            _data[sid]['__date'] = time() + 300
            sess = get_session( db, sid )
            user = None
            if sess is not None and update_session( db, sess.session_id ):
                db_user = get_user_for_session( db, sess )
                if db_user is not None:
                    if not _users.has_key( db_user.id ):
                        print "Adding user %s to local user dict" % (db_user.username,)
                        _users[db_user.id] = UserState.UserState( db_user.username, db )
                    user = _users[db_user.id]
            else:
                sess = create_session( db, sid )


            for ssid in dict(_data):
                if _data[ssid]['__date'] < time():
                    del _data[ssid]
        except Exception as e:
            print "Database exception while getting session: %s; ignored." % (repr(e),)
            pass

        return func(sess, user, *a, **k)
    return wrapper

def destroySessionWithId( db, sid ):
    try:
        delete_session( db, sid )
        del _data[sid]
    except Exception as e:
        pass


def destroy( db ):
    'Destroys the session of the current user.'
    try:
        sid = request.get_cookie('PYSESSID')
        sid = sha1('%s%s' % (sid, request['REMOTE_ADDR'])).hexdigest()
        destroySessionWithId( db, sid )
    except Exception:
        pass