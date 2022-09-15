from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
import database
import sys
import datetime
import hashlib
import string
import random

def create_key( prefix ):
    # str =
    return prefix + (''.join(random.choice("ABCDEFGHJKLMNPQRTUVWXYZ12346789") for x in range(16)))

engine = create_engine( "postgresql+psycopg2://tdta:foobar42@10.0.0.1/tdta" )
Session = sessionmaker(bind=engine)

db = Session()

if len( sys.argv ) < 4:
    print "usage: %s [count] [prefix] [do_insert]" % (sys.argv[0],)
    sys.exit(1)


count = int( sys.argv[1])
prefix = sys.argv[2]
do_insert = sys.argv[3]

keys = []
for i in range( 0, count ):
    k = create_key(prefix)
    keys.append( k )
    print k


if do_insert == "y":
    print "Inserting %d keys..." % (len(keys),)
    for i in range( 0, len(keys) ):
        bi = database.BetaInvite( keys[i] )
        db.add( bi )

db.commit()
