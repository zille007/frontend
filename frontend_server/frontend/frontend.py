# coding=utf8

#these are needed to run under pypy on live
#from psycopg2cffi import compat
#compat.register()

#import gevent_psycopg2; gevent_psycopg2.monkey_patch()
import psycogreen.gevent
psycogreen.gevent.patch_psycopg()                                                                              

from gevent import monkey; monkey.patch_all(socket=True, dns=True, time=True, select=True, thread=True, os=True, ssl=True, httplib=False, subprocess=False, sys=True, aggressive=True, Event=False)
from gevent.coros import Semaphore                                                                             

import gevent

import sys
from FrontendConfig import *

import json
import sessions
import bottle
import pymongo
import users
import inventory
import smtplib
import hashlib
import string
import urllib
from email.mime.text import MIMEText

from userauth import User, authenticate, new_user, new_user_steam, new_user_ios, grant_initial_items
from discovery import matchmaking_pass, create_match, matchrequest_for_user, matchresult_for_user, create_matchrequest, \
    clear_matchreqs_for_user, matchresults_for_token, match_for_id, create_match_new, match_had_ai_players
from bottle import route, request, response, run, Bottle
from bottle.ext import sqlalchemy
from bottle import static_file
from hashlib import md5
import random
from datetime import datetime, timedelta
from database import MatchRequest, MatchResult, BetaFeedback, \
    BetaInvite, GameInvite, FriendRequest, FriendAssociation, UserStatEvent, Achievement, \
    ShopSKU, ShopSKUPrice, ShopTransaction, ShopTransactionItem, MatchBasicInfo, \
    MatchPlayerInfo, MatchPlayerEvent, MatchTeamEvent, UserStats, UserPossession, UserBooster

from sqlalchemy import create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.pool import QueuePool 

from sqlalchemy.pool import NullPool, StaticPool

from database import Match
import elo
import messages
import time
import MatchEntry
import UserState

import traceback

import boto
import metrics
import syscontrol
import matchmaking

MATCH_STATUS_CREATED = 2
MATCH_STATUS_STARTED = 5
MATCH_STATUS_ENDED = 6

class GreenQueuePool(QueuePool):

    def __init__(self, *args, **kwargs):
        super(GreenQueuePool, self).__init__(*args, **kwargs)
        if self._overflow_lock is not None:
            self._overflow_lock = Semaphore()
            self._use_threadlocal = True

Base = declarative_base()
engine = create_engine("postgresql+psycopg2://%s:%s@%s/%s" % (DB_USERNAME, DB_PASSWORD, DB_HOST, DB_USERNAME), echo=False, poolclass=GreenQueuePool,
                       pool_size=120, max_overflow=80, pool_timeout=30, strategy='threadlocal' )

MAX_INVENTORY_SHEETS = 5

all_db_shop_items = [
    {"item_id": 1, "name": "A Bag of Gems", "description": "A random assortment of three gems", "price": 1000},
    {"item_id": 2, "name": "A Stack of Items", "description": "A random assortment of three items", "price": 2000},
]
all_db_items = []
all_db_item_ids = []
all_db_gems = []
all_db_gem_ids = []

user_equip_sheet_dict = {}    # [session_id]["gems|items"] => x-tuple
user_inventory_dict = {}      # [session_id]["gems|items"] => list

# TODO: online status stuff => refactor into a separate file

activeMatches = {}

discoveryEngine = MatchEntry.DiscoveryEngine()
matchmakingEngine = matchmaking.Matchmaker( MATCHMAKING_GAME_SIZE )   # 3vs3 only for now

messageCenter = messages.MessageCenter()

mongo = pymongo.Connection(MONGODB_HOST, MONGODB_PORT)
hero_names = ALLOWED_HEROES
all_db_heroes = {}

for i in mongo.tatd.items.find():
    all_db_items.append(i)

for g in mongo.tatd.gems.find():
    all_db_gems.append(g)

# make sure items and gems have a proper item id
item_ids = []
gem_ids = []
for i in all_db_items:
    if not i.has_key("item_id"):
        print "WARNING: item with no id: %s" % (str(i["_id"]),)
    elif i["item_id"] in item_ids:
        print "WARNING: item with duplicate id: %s (%s)" % (str(i["_id"]), i["name"])
    else:
        item_ids.append(i["item_id"])

for i in all_db_gems:
    if not i.has_key("gem_id"):
        print "WARNING: gem with no id: %s" % (str(i["_id"]),)
    elif i["gem_id"] in gem_ids:
        print "WARNING: gem with duplicate id: %s (%s)" % (str(i["_id"]), i["name"])
    else:
        gem_ids.append(i["gem_id"])

all_db_item_ids = item_ids
all_db_gem_ids = gem_ids

for h in hero_names:
    hero = mongo.tatd.prefabs.find_one({"name": h})
    d = {"name": h,
         "description": "This is a human-readable description for this hero. It should come from creative. This is a placeholder."}

    base_attrs = ( "Faction", "Hitpoints", "Mana", "Speed", "Damage minimum", "Damage maximum", "Attack range", "Description" )
    stats_attrs = ( "Strength", "Dexterity", "Intelligence", "Armor" )
    ability_attrs = ( "Type", "Cost", "Cooldown", "Damage minimum", "Damage maximum", "Range", "Slot", "Disply name" )

    stats_dict = {}
    ability_dict = {}

    for ba in base_attrs:
        if ba == "Description":
            if hero["components"]["ATTRIBUTES"].has_key( "Description" ):
                d["description"] = hero["components"]["ATTRIBUTES"][ba]
            else:
                continue
        else:
            d[ba] = hero["components"]["ATTRIBUTES"][ba]

    sd = {}
    for sa in stats_attrs:
        sd[sa] = hero["components"]["ATTRIBUTES"]["Stats"][sa]
    d["stats"] = sd

    ad = {}
    for ability in hero["components"]["ATTRIBUTES"]["Abilities"].keys():
        ad[ability] = {}
        for aa in ability_attrs:
            if hero["components"]["ATTRIBUTES"]["Abilities"][ability].has_key(aa):
                ad[ability][aa] = hero["components"]["ATTRIBUTES"]["Abilities"][ability][aa]
            else:
                ad[ability][aa] = 0.0
        ad[ability]["description"] = hero["components"]["ATTRIBUTES"]["Abilities"][ability]["Description"]
        if hero["components"]["ATTRIBUTES"]["Abilities"][ability].has_key("Display name"):
            ad[ability]["Display name"] = hero["components"]["ATTRIBUTES"]["Abilities"][ability]["Display name"]
        else:
            ad[ability]["Display name"] = ability

    d["abilities"] = ad

    all_db_heroes[h] = d
    print "Read hero %s" % (hero["name"],)

error_dict = json.dumps({"result": 0})


metrics.init()
adminControl = syscontrol.SyscontrolState()

app = Bottle()

from sqlalchemy.orm import scoped_session
from sqlalchemy.orm import sessionmaker

bsqa_sessionmaker = scoped_session(sessionmaker())
plugin = sqlalchemy.Plugin(
    engine,
    Base.metadata,
    keyword='db',
    create=True,
    commit=True,
    use_kwargs=True,
    create_session=bsqa_sessionmaker
)

app.install(plugin)

# static route for beta form files
@app.route("/static/<filepath:path>")
@metrics.collect
def server_static(filepath):
    print "Serving static file " + filepath
    return static_file(filepath, root="./static")


@app.route("/beta_confirm", method="GET")
@metrics.collect
def beta_confirm(db=None):
    error = ""
    try:
        key = request.query["key"]
        confirm = request.query["confirm"]

        invite = db.query(BetaInvite).filter(BetaInvite.beta_key == key).first()
        if invite is not None and not invite.consumed and invite.email_confirm_key == confirm:
            invite.consumed = True
            invite.email_confirmed = True
            new_user(db, invite.requested_username, invite.requested_password, invite.requested_username, "BETA",
                     invite.email_address, all_db_gems, all_db_items)
            invite.requested_password = ""
            invite.consumed_timestamp = datetime.now()
            db.commit()
            text = """
Welcome to Dethroned! beta testing (and thanks for participating)!

Download your copy from:

http://www.treehouse.fi/dethroned/beta/dethroned-windows.zip
http://www.treehouse.fi/dethroned/beta/dethroned-mac.zip

Howto (for Mac/Windows):
Unzip to a suitable directory (like "Desktop") and double-click Dethroned! icon inside "Dethroned" directory to start the game.

After the game has loaded, login with your player name and password. Select Battle and click begin for a quick game or see friend list for other players to see who's online. All current beta testers are shown in the friend list.

For more instructions, see this image:

http://www.treehouse.fi/dethroned/dethroned_help.jpg

The game is in beta and we'd love to hear your opinions and bug reports of it!

If your beta login doesn't work, send email to support@treehouse.fi and describe your problem.


Cheers,
Treehouse Ltd
"""
            msg = MIMEText(text)
            msg["Subject"] = "Your Dethroned! beta account"
            msg["From"] = "info@treehouse.fi"
            msg["To"] = invite.email_address

            print "Sending final confirmation email to %s..." % (invite.email_address,)
            s = smtplib.SMTP(SMTP_SERVER, SMTP_PORT)
            s.starttls()
            s.login(SMTP_USERNAME, SMTP_PASSWORD)
            try:
                s.sendmail("info@treehouse.fi", [invite.email_address], msg.as_string())
                s.quit()

                invite.email_sent = True
                db.commit()

                return bottle.template("dethroned_beta_success", requested_username=invite.requested_username,
                                       email=invite.email_address)
            except Exception as e:
                print str(e)
                error = "Error sending a confirmation email. Is the address you supplied: " + invite.email_address + " a correct one?"
                error += " Additional information: " + e.message
            pass

        else:
            return bottle.redirect("", 302)
    except Exception as e:
        print e.message
        error = "We could not confirm your beta participation. Something odd is going on."
        pass
    return bottle.template("dethroned_beta_failure", error=error)


@app.route("/account_create", method="POST")
@metrics.collect
def account_create( db=None ):
    print "Account creation..."
    error = "Something very bad??"
    try:
        fail = False
        req_uname = request.forms["requested_name"].strip()
        req_password = request.forms["password"].strip()
        email = request.forms["email"].strip()
        existing_user = db.query(User).filter(User.username == req_uname).first()

        print "Performing pre-checks..."

        if len(req_password) < 6:
            error = "Password must be longer than 6 characters."
            fail = True

        if len(req_uname) <= 4:
            error = "User name must be longer than 4 characters."
            fail = True

        if existing_user is not None:
            error = "The desired user name is not available."
            fail = True

        if not fail:
            new_user(db, req_uname, req_password, req_uname, "BETA", email, all_db_gems, all_db_items)
            db.commit()

            print "Success; returning with success template"
            return bottle.template("dethroned_beta_success", requested_username=req_uname,
                                   email=email)

    except Exception as e:
        print e.message
        pass

    return bottle.template("dethroned_beta_failure", error=error)


@app.route('/beta_signup', method="POST")
@metrics.collect
def beta_signup(db=None):
    print "Signup received..."
    error = "Something very bad??"

    try:
        fail = False
        key = request.forms["beta_key"].strip()
        req_uname = request.forms["requested_name"].strip()
        req_password = request.forms["password"].strip()
        email = request.forms["email"].strip()
        invite = db.query(BetaInvite).filter(BetaInvite.beta_key == key).first()
        existing_user = db.query(User).filter(User.username == req_uname).first()

        print "Performing pre-checks for key %s" % (key, )

        if len(req_password) < 6:
            error = "Password must be longer than 6 characters."
            fail = True

        if len(req_uname) <= 4:
            error = "User name must be longer than 4 characters."
            fail = True

        if invite is None:
            error = "Invalid beta key."
        elif existing_user is not None:
            error = "The desired user name is not available."

        print "fail=%s invite=%s existing_user=%s invite.consumed=%s invite.email_sent=%s" % (
            fail, invite, existing_user, invite.consumed, invite.email_sent)

        if not fail and invite is not None and existing_user is None and not invite.consumed:
            confirmkey = hashlib.sha1(
                '420~DE%sTHR0%sNeD!666' % (str(datetime.today()), request.remote_addr)).hexdigest()
            invite.email_confirm_key = confirmkey
            invite.requested_username = req_uname
            invite.requested_password = req_password
            invite.email_address = email

            srv_ip = FRONTEND_SERVER_HOSTNAME
            link = "http://%s:%d/beta_confirm?key=%s&confirm=%s" % (srv_ip, BIND_PORT, key, confirmkey)
            msg = MIMEText("""
Hey you!

Someone (probably you?) has used this email address to register for the Dethroned! beta.

Please confirm your beta participation by clicking this link:
""" + link)
            msg["Subject"] = "Dethroned! beta participation confirmation"
            msg["From"] = "info@treehouse.fi"
            msg["To"] = email

            print "Sending email to %s..." % (email,)
            s = smtplib.SMTP(SMTP_SERVER, SMTP_PORT)
            s.starttls()
            s.login(SMTP_USERNAME, SMTP_PASSWORD)
            try:
                s.sendmail("info@treehouse.fi", [email], msg.as_string())
                s.quit()

                invite.email_sent = True
                db.commit()

                return bottle.template("dethroned_beta_emailsent", email=email)
            except Exception as e:
                error = "Error sending a confirmation email. Is the address you supplied: " + email + " a correct one?"
                error += " Additional information: " + e.message
    except Exception as e:
        print e.message
        pass

    return bottle.template("dethroned_beta_failure", error=error)


@app.route('/motd', method='POST')
@sessions.start
@metrics.collect
def news(session, user, db):
    if user is None:
        return error_dict

    motd = ""
    with open("%s/%s" % (MOTD_FILE_PATH, MOTD_FILE)) as motd_file:
        data = motd_file.readlines()

    motd = ''.join(data)
    #motd = 'Welcome to the Dethroned! beta. Please report any issues you have during gameplay.\n\nScheduled maintenance is daily, 1pm to 2pm (GMT+2).'

    #if online_user_client_dict.has_key(user.username) and online_user_client_dict[user.username][0] == "0.3.0.0":
    #    plat = online_user_client_dict[user.username][1]
    #    motd = '[ff2222]Attention: your client is out of date!\n\nPlease download the updated client from:\n'

    #    if plat[0:3] == "OSX":
    #        motd += "\nhttp://www.treehouse.fi/dethroned/beta/dethroned-mac.zip\n"
    #    elif plat[0:7] == "Windows":
    #        motd += "\nhttp://www.treehouse.fi/dethroned/beta/dethroned-windows.zip\n"

    #    motd += '\nYou will not be able to join games with this client.'

    d = {'result': 1, 'motd': motd}
    return json.dumps(d)

def finalizeLogin( db, session, user, clientversion, clientplatform, screenName = None ):
        #print "Authentication OK user=" + str(user) + " sessuser=" + str(sessions.getUserById(user.id))

        session.user_id = user.id
        user.is_online = True
        sessions.setUserById(user.id, UserState.UserState(user.username, db))
        user = sessions.getUserById(user.id)
        user.login(clientversion, clientplatform)

        if screenName is not None:
            user.screenname = screenName

        discoveryEngine.endMatchmaking( user )
        discoveryEngine.removeWithUsername( user.username )

        if not messageCenter.userLogin(user.username, user.screenname, user.id ):
            # insurance here
            messageCenter.userLogout(user.username)
            messageCenter.userLogin(user.username, user.screenname, user.id)

        messageCenter.userJoinChannel(user.username, "General")

        db.commit()

        d = {}
        d["username"] = user.screenname
        d["screenname"] = user.screenname
        d["clantag"] = user.clantag
        d["is_admin"] = True if user.account_type == 9 else False

        d["ping_delay"] = CLIENT_PING_DELAY
        d["message_delay"] = CLIENT_MESSAGE_DELAY
        d["friend_delay"] = CLIENT_FRIEND_STATUS_DELAY

        clear_matchreqs_for_user(db, user)

        # clean up old match invites as well
        print "Removing old match invites for user %s" % (user.username,)
        oldinvs = db.query(GameInvite).filter(GameInvite.receiver_user_id == user.id)
        oldinvs.delete()
        db.commit()

        if not user_equip_sheet_dict.has_key(user.username):
            user_equip_sheet_dict[user.username] = {}
            user_equip_sheet_dict[user.username]["item"] = [-1, -1, -1, -1]
            user_equip_sheet_dict[user.username]["gem"] = [-1] * 4

        if not user_inventory_dict.has_key(user.username):
            # actually need to get this from db, but for now this will do
            user_inventory_dict[user.username] = {}
            user_inventory_dict[user.username]["item"] = range(0, len(all_db_items))


        # todo: do weekly rotation setups here

        u = sessions.getUserById(user.id)
        u.refreshHeroesFromDb( db, hero_names )

        d["allowed_maps"] = list(ALLOWED_MAPS)

        return d


def price_for_sku_id( db, sku_id, currency ):
    db_price = db.query( ShopSKUPrice ).filter_by( sku_id=sku_id, currency=currency ).first()
    if db_price:
        return db_price.unit_price
    return -1


@app.route('/steamtxn/<command>', method="POST")
@sessions.start
@metrics.collect
def steamtxn( session, user, db, command ):
    if user is None or user.steamId == "":
        return error_dict

    request_dict = json.loads( request.forms["request_data"] )
    d = { "result":0 }

    try:
        if command == "init":
            if user.steamId != "":
                item_id = request_dict[ "item_id" ]
                qty = request_dict[ "quantity" ]

                print "STEAM TX INIT from user ID %d steam ID %s: want %d units of item %d " % (user.id, user.steamId, qty, item_id)

                sku = db.query( ShopSKU ).filter_by( id=item_id, purchaseable=True ).one()
                unit_price = price_for_sku_id( db, item_id, user.steamTxCurrency  )
                if unit_price != -1 and sku is not None:
                    price = qty * unit_price
                    ourtxn = ShopTransaction( user.id, "steam", price, user.steamTxCurrency )
                    db.add( ourtxn )
                    db.commit()

                    txn_item = ShopTransactionItem( ourtxn.id, item_id, qty, user.steamTxCurrency, unit_price )
                    db.add( txn_item )
                    db.commit()

                    print "Created new transaction %d; contained item ID %d (%d @ %d %s)" % (ourtxn.id, txn_item.item_sku_id, qty, price, user.steamTxCurrency)

                    url = "https://api.steampowered.com/ISteamMicroTxnSandbox/InitTxn/v0002/?format=json&key=%s" % (STEAM_WEBAPI_KEY, )
                    params = urllib.urlencode( {
                        "orderid":ourtxn.id,
                        "steamid":user.steamId,
                        "appid":STEAM_APP_ID,
                        "itemcount":1,
                        "language":"EN",
                        "currency":ourtxn.currency,
                        #"usersession": "web",
                        "ipaddress": "91.152.237.83", # request.remote_addr,
                        "itemid[0]":txn_item.item_sku_id,
                        "qty[0]":txn_item.quantity,
                        "amount[0]":txn_item.unit_price * txn_item.quantity,
                        "description[0]":sku.description,
                        "category[0]":sku.category
                    } )
                    f = urllib.urlopen( url, params )
                    steam_response_raw = f.read()
                    print repr(steam_response_raw)
                    steam_response = json.loads( steam_response_raw )
                    data = steam_response["response"]
                    if data["result"] == "OK":
                        print "Steam returned OK for tx id %s (steam tx id %s)" % (data["params"]["orderid"], data["params"]["transid"])
                        ourtxn.merchant_txn_id = data["params"]["transid"]
                        ourtxn.tx_state = "wait_payment"
                        db.commit()
                        d["result"] = 1
                        #d["steamurl"] = data["params"]["steamurl"]
                    else:
                        error = "%s: %s" % (data["error"]["errorcode"], data["error"]["errordesc"])
                        print "Steam transaction init for ID %s failed: %s" % (user.steamId, error)

        elif command == "info":
            if user.haveSteamTxInfo:
                d["result"] = 1
                d["country"] = user.steamTxCountry
                d["currency"] = user.steamTxCurrency
                d["status"] = user.steamTxAccountStatus
                sku_list = []
                all_skus = db.query( ShopSKU ).filter_by( purchaseable=True, steam_sellable=True ).all()
                if all_skus is not None:
                    for sku in all_skus:
                        db_price = db.query( ShopSKUPrice ).filter_by( sku_id=sku.id, currency=d["currency"] ).first()
                        unit_price = 0
                        currency = "NONE"
                        if db_price:
                            unit_price = db_price.unit_price
                            currency = db_price.currency

                        if sku.category != 'character':
                            sku_list.append( { "id":sku.id, "name":sku.name, "description":sku.description, "category":sku.category, "price":unit_price, "currency":currency } )
                    d["shop_skus"] = sku_list
        elif command == "finalize":
            # query all transactions that are waiting for payment and see if they can be finalized
            order_id = request_dict["order_id"]
            if user.steamId != "":
                print "Attempting to finalize transaction %d for Steam ID %s" % (order_id, user.steamId )
                tx = db.query( ShopTransaction ).filter_by( id = order_id, user_id = user.id, tx_state = "wait_payment" ).one()
                if tx is not None:
                    steam_txid = tx.merchant_txn_id
                    url = "%s/QueryTxn/v0001/?format=json&key=%s&appid=%s&transid=%s" % (STEAM_WEBAPI_MICROTXN_URL, STEAM_WEBAPI_KEY, STEAM_APP_ID, steam_txid )
                    f = urllib.urlopen( url, None )
                    steam_response_raw = f.read()
                    print repr(steam_response_raw)
                    steam_response = json.loads( steam_response_raw )
                    data = steam_response["response"]

                    print "Transaction status from Steam for TX: " + data["params"]["status"]
                    if data["params"]["status"] == "Approved":
                        print "Will finalize transaction %s (orderid %d on user id %d)" % (steam_txid, tx.id, user.id)
                        params = urllib.urlencode( {
                            "orderid": order_id,
                            "appid": STEAM_APP_ID
                        })
                        url = "%s/FinalizeTxn/v0001/?format=json&key=%s" % (STEAM_WEBAPI_MICROTXN_URL, STEAM_WEBAPI_KEY)
                        f = urllib.urlopen( url, params )
                        steam_response_raw = f.read()
                        print "Steam TX finalize response: %s" % (str(steam_response_raw),)
                        steam_response = json.loads( steam_response_raw )
                        data = steam_response["response"]
                        if data["result"] == "OK":
                            print "Transaction finalized; will grant purchased items"
                            purchase_items = db.query( ShopTransactionItem ).filter_by( tx_id = order_id ).all()
                            for i in purchase_items:
                                users.user_grant_shop_sku( db, user, i.item_sku_id, "Steam order %s" % (order_id, ))
                            tx.tx_state = "completed"
                            db.commit()

    except Exception as e:
        _, _, tb = sys.exc_info()
        traceback.print_tb(tb) # Fixed format
    return json.dumps(d)



def steamDLCCheck( user, dlc_app_id ):
    # do a steam ownership check for all DLC
    if user.steamId is None or len(user.steamId) == 0:
        print "User has no Steam ID set, skipping DLC check"
        return

    has_dlc = False
    appid = dlc_app_id
    steamid = user.steamId

    try:
        url = "https://api.steampowered.com/ISteamUser/CheckAppOwnership/v0001/?key=%s&appid=%s&steamid=%s" % (STEAM_WEBAPI_KEY, appid, steamid)
        f = urllib.urlopen( url )
        steam_response = json.loads( f.read() )
        print steam_response
        if steam_response.has_key( "appownership"):
            has_dlc = steam_response["appownership"]["ownsapp"]
    except Exception as e:
        _, _, tb = sys.exc_info()
        traceback.print_tb(tb) # Fixed format

    return has_dlc

def checkAndGrantSteamDLC( db, user ):
    dlc_appids = { "284070":"early_access_pack" }
    print "Checking all DLC for user %s" % (user.username,)

    dlc_grants = []

    try:
        for k in dlc_appids.keys():
            dlc_appid, dlc_desc = k, dlc_appids[k]
            print "Checking DLC %s (%s) for user %s..." % (dlc_desc, dlc_appid, user.username)
            if steamDLCCheck( user, dlc_appid ):
                if dlc_desc == "base_game":
                    pass
                if dlc_desc == "early_access_pack":
                    q = db.query( UserPossession ).filter( UserPossession.user_id == user.id, UserPossession.p_type == "dlc", UserPossession.p_item == "early_access_pack" ).first()
                    if q is not None:
                        print "User %s has DLC %s and it has been granted" % (user.username, dlc_desc)

                        for hn in (): # hero_names:
                            h_query = db.query( UserPossession ).filter( UserPossession.user_id == user.id, UserPossession.p_type == "character", UserPossession.p_item == hn ).first()
                            if h_query is None:
                                h_up = UserPossession( user.id, "character", hn, "Early Access DLC grant" )
                                db.add( h_up )
                                print "Added missing hero %s to user %s" % (hn, user.username)
                        db.commit()
                    else:
                        print "User %s has DLC %s, but it has not been awarded yet. Awarding..." % (user.username, dlc_desc)
                        ########## DLC AWARDING #########
                        # 1. Grant all heroes
                        for hn in hero_names:
                            h_query = db.query( UserPossession ).filter( UserPossession.user_id == user.id, UserPossession.p_type == "character", UserPossession.p_item == hn ).first()
                            if h_query is None:
                                h_up = UserPossession( user.id, "character", hn, "Early Access DLC grant" )
                                db.add( h_up )
                                print "Added missing hero %s to user %s" % (hn, user.username)
                        # 2. Grant 1500 tokens
                        count = 1500
                        stats = users.user_stats_for_user( db, user )
                        oldvalue = stats.soft_money
                        stats.soft_money += count

                        e = UserStatEvent( user.id, "soft_money", "inc", count, oldvalue )
                        e.match_token = ""
                        e.description = "Early Access DLC grant"
                        db.add( e )
                        print "Granted %d units of soft money to user %s" % (count, user.username)

                        # 3. Grant the celestial bear item (id 61... this really should not be hardcoded)
                        if not inventory.user_has_item_with_itemid( db, user, 61 ):
                            print "Granting Celestial Duck summon item..."
                            item = inventory.random_item_with_baseid_to_user( db, user, 61 )
                            item.suit = "Fire"
                            db.add( item )
                        else:
                            print "User already has Celestial Duck summon item, not granting it..."

                        # TODO: 4. Grant token booster
                        print "Granting 25% token booster (delta=+7d)"
                        bst_expiry = datetime.now() + timedelta(days=7)
                        b = UserBooster( user.id, "token", 1.25, bst_expiry, "Steam Early Access DLC purchase" )
                        db.add( b )

                        # 5. Mark the DLC as granted
                        dlc_up = UserPossession( user.id, "dlc", "early_access_pack", "Steam Early Access DLC purchase")
                        db.add( dlc_up )
                        db.commit()

                        user.refreshHeroesFromDb( db, hero_names )
                        dlc_grants.append( dlc_desc )
    except Exception as e:
        _, _, tb = sys.exc_info()
        traceback.print_tb(tb) # Fixed format

    return tuple( dlc_grants )


@app.route('/recheck_dlc', method="POST")
@sessions.start
@metrics.collect
def steamdlc( session, user, db ):
    if user is None:
        return error_dict

    d = error_dict

    try:
        print "User %s requested DLC recheck." % (user.username,)
        grants = checkAndGrantSteamDLC( db, user )
        d = { "result":1, "new_dlc":grants, "new_dlc_count":len(grants) }
    except Exception as e:
        _, _, tb = sys.exc_info()
        traceback.print_tb(tb) # Fixed format

    return json.dumps(d)

@app.route('/ioslogin', method="POST")
@sessions.start
@metrics.collect
def ipadlogin( session, user, db ):
    request_dict = json.loads( request.forms["request_data"] )
    d = { "result": 0 }

    try:
        print request_dict
        proposed_vendorid = request_dict[ "vendorid" ]
        screenname = request_dict[ "screenname" ]
        clientversion = request_dict["clientversion"]
        clientplatform = request_dict["clientplatform"]

        print "iOS login with vendor ID %s screenname %s" % (proposed_vendorid,screenname)

        if clientversion not in ALLOW_CLIENT_VERSIONS:
            print "Client has been rejected as we allow only client versions %s" % (str(ALLOW_CLIENT_VERSIONS),)
            d = {"result": 0, "reason": "Client is out of date!", "oldclient": True,
                 "required_client": ALLOW_CLIENT_VERSIONS[0], "download_url": ""}
            return json.dumps(d)

        if proposed_vendorid is None or len(proposed_vendorid) < 5:  # length check just for sanity
            print "No vendorid in ios login!"
            return json.dumps(d)

        ok = False
        # this can be used to create dummy users but does it matter?
        u = db.query( User ).filter_by( username='ios:%s' % (proposed_vendorid,), screenname=screenname).first()
        print u
        if u is None:
            print "No user for iOS vendorid, creating new user with screenname %s..." % (screenname,)
            newu = new_user_ios( db, proposed_vendorid, screenname )
            db.add( newu )
            db.commit()
            users.user_create_stats( db, newu )
            grant_initial_items( db, newu, all_db_items )
            u = newu
            ok = True
        else:
            print "Found matching user with screenname %s (got screenname %s)" % (u.screenname, screenname)
            if screenname == u.screenname:
                ok = True

        if ok:
            res = finalizeLogin( db, session, u, "", "", screenname )
            res["result"] = 1
            d = res

            user = sessions.getUserById(u.id)

            print "iOSLogin will run potential character grants... level=%d" % (user.dbStats.xp_level,)
            if users.user_potentially_grant_new_character( db, user ):
                db.commit()
                user.refreshHeroesFromDb( db, hero_names )
        else:
            print "iOS: did not login successfully"

    except Exception as e:
        print "iOS login exception: " + e.message
        _, _, tb = sys.exc_info()
        traceback.print_tb(tb) # Fixed format

    return json.dumps(d)

@app.route('/steamlogin', method="POST")
@sessions.start
@metrics.collect
def steamlogin(session, user, db):
    request_dict = json.loads( request.forms["request_data"] )
    d = { "result": 0 }

    try:
        proposed_steamid = request_dict[ "steamid" ]
        auth_ticket = request_dict[ "ticket" ]
        persona = request_dict[ "persona" ]

        clientversion = request_dict["clientversion"]
        clientplatform = request_dict["clientplatform"]

        if clientversion not in ALLOW_CLIENT_VERSIONS:
            print "Client has been rejected as we allow only client versions %s" % (str(ALLOW_CLIENT_VERSIONS),)
            d = {"result": 0, "reason": "Client is out of date!", "oldclient": True,
                 "required_client": ALLOW_CLIENT_VERSIONS[0], "download_url": ""}
            return json.dumps(d)

        print "Steam login with proposed steam ID %s; doing Steam auth..." % (proposed_steamid,)
        url = "https://api.steampowered.com/ISteamUserAuth/AuthenticateUserTicket/v0001/?format=json&key=%s&appid=%s&ticket=%s" % (STEAM_WEBAPI_KEY, STEAM_APP_ID, auth_ticket)
        f = urllib.urlopen( url )
        steam_response_raw = f.read()
        steam_response = json.loads( steam_response_raw )
        data = steam_response["response"]

        if data.has_key("params") and data["params"]["result"] == "OK":
            steamid = str(data["params"]["steamid"])
            print "Steam replied with OK response; real steamid = %s" % (steamid,)
            if steamid == proposed_steamid:
                db_u = db.query( User ).filter_by( steam_id=steamid ).first()
                if db_u is not None:
                    print "Found matching user: uid=%d username=%s" % (db_u.id, db_u.username)
                else:
                    print "No user with matching steam ID; creating user entry..."
                    #new_user( db, "steam%s" % (steamid,), "NOPASSWORDNOPASSWORD", persona, "", "", all_db_items, all_db_gems )
                    #db_u = db.query( User ).filter_by( steam_id=steamid ).first()
                    newu = new_user_steam( db, steamid, persona )

                    db.add( newu )
                    db.commit()

                    users.user_create_stats( db, newu )
                    grant_initial_items( db, newu, all_db_items )
                    db_u = newu

                if db_u is not None and db_u.allow_login == True:

                    res = finalizeLogin( db, session, db_u, clientversion, clientplatform, screenName = persona )
                    res["result"] = 1

                    user = sessions.getUserById(db_u.id)

                    checkAndGrantSteamDLC( db, user )

                    print "Will run potential character grants... level=%d" % (user.dbStats.xp_level,)
                    if users.user_potentially_grant_new_character( db, user ):
                        db.commit()

                    user.refreshHeroesFromDb( db, hero_names )
                    user.setSteamTxParams( "XX", "EUR", "Trusted" )

                    # query user's microtransaction info from Steam for future reference...
                    url = "https://api.steampowered.com/ISteamMicroTxnSandbox/GetUserInfo/v0001/?format=json&key=%s&steamid=%s" % (STEAM_WEBAPI_KEY, steamid)
                    f = urllib.urlopen( url )
                    steam_response_raw = f.read()
                    steam_response = json.loads( steam_response_raw )
                    data = steam_response["response"]

                    if data["result"] == "OK":
                        txparams = data["params"]
                        user.setSteamTxParams( txparams["country"], txparams["currency"],txparams["status"] )
                        print "Steam microtransaction info for ID %s: %s/%s (%s)" % (steamid,  txparams["country"], txparams["currency"],txparams["status"])
                    else:
                        error = "%s: %s" % (data["error"]["errorcode"], data["error"]["errordesc"])
                        print "Could not query microtransaction info for ID %s: %s" % (steamid, error)

                    d = res
        else:
            print "Steam authentication FAILED, result: " + str(data)

    except Exception as e:
        _, _, tb = sys.exc_info()
        traceback.print_tb(tb) # Fixed format
    return json.dumps(d)



@app.route('/login', method='POST')
@sessions.start
@metrics.collect
def login(session, user, db):
    request_dict = json.loads(request.forms["request_data"])
    user = authenticate(db, request_dict["username"], md5(request_dict["password"]).hexdigest())

    clientversion = request_dict["clientversion"]
    clientplatform = request_dict["clientplatform"]

    print "%s authenticating with client version %s..." % (request_dict["username"], clientversion)

    if clientversion == "0.3.0.0":
        print "Will allow login, but use custom MOTD as the client is out-of-date..."
    elif clientversion not in ALLOW_CLIENT_VERSIONS:
        url = "http://www.treehouse.fi/dethroned/beta/dethroned-"

        if clientplatform[0:3] == "OSX":
            url += "mac.zip"
        elif clientplatform[0:7] == "Windows":
            url += "windows.zip"
        elif clientplatform[0:5] == "Linux":
            url += "linux.zip"
        else:
            url += "current.zip"

        print "Client has been rejected as we allow only client versions %s" % (str(ALLOW_CLIENT_VERSIONS),)
        d = {"result": 0, "reason": "Client is out of date!", "oldclient": True,
             "required_client": ALLOW_CLIENT_VERSIONS[0], "download_url": url}
        return json.dumps(d)

    d = {}

    if user is not None and user.allow_login == True:
        d = finalizeLogin( db, session, user, clientversion, clientplatform, screenName=user.username)

    d["result"] = 1 if user is not None else 0
    if user is not None:
        print "%s logged in" % (user.username,)
        d["allowed_maps"] = list(ALLOWED_MAPS)
        #user.log( db, "login" )
    else:
        print "Login failed; invalid username or password."

    print "login will return %s" % (json.dumps(d),)

    return json.dumps(d)


def finalizeLogout( db, user ):
    print "Will finalize logout for %s id %s" % (str(user), user.id)
    user.is_online = False

    if user in match_queue:
        match_queue.remove( user )

    sessions.destroySessionWithId( db, user.sessionId )
    sessions.removeUserById( user.id )

    discoveryEngine.endMatchmaking( user )
    discoveryEngine.removeWithUsername( user.username )

    messageCenter.userLogout(user.username)
    #user.log( db, "logout" )
    db.commit()


@app.route('/logout', method='POST')
@sessions.start
@metrics.collect
def logout(session, user, db):
    if user is None:
        return error_dict

    user.logout()
    finalizeLogout( db, user )
    print "LOGOUT from user %s" % (user.username, )

    d = {"result": 1}
    return json.dumps(d)


@app.route('/newuser', method='POST')
@sessions.start
@metrics.collect
def create_user(session, user, db):
    # cant create a new user if logged in
    if user != None:
        return error_dict

    request_dict = json.loads(request.forms["request_data"])
    req_keys = ( 'username', 'password', 'screenname', 'email' )
    print "Newuser with " + str(request_dict)
    for k in req_keys:
        if not request_dict.has_key(k):
            return error_dict

    try:
        if not new_user(db, request_dict["username"], request_dict["password"], request_dict["screenname"], "",
                        request_dict["email"], all_db_gems, all_db_items):
            return error_dict
    except Exception as e:
        print e

    print "New user created"

    d = {"result": 1, "username": request_dict["username"]}
    return json.dumps(d)


@app.route("/heroinfo", method="POST")
@sessions.start
@metrics.collect
def heroinfo(session, user, db):
    if user is None:
        return error_dict
    request_dict = json.loads(request.forms["request_data"])
    hero = request_dict["hero"]

    if not all_db_heroes.has_key(hero):
        return error_dict

    # gah, hardcoded
    chargrants = { "Sniper":2, "Beaver":5, "Stone elemental":10, "Fyrestein":15, "Rogue":20 }
    sku_ids = { "Beaver":2001, "Stone elemental":2004, "Fyrestein":2002, "Rogue":2005 }

    d = all_db_heroes[hero]
    d["unlock_level"] = chargrants[hero] if chargrants.has_key(hero) else -1
    d["sku_id"] = sku_ids[hero] if sku_ids.has_key(hero) else -1
    d["result"] = 1
    print "%s requested heroinfo for %s" % (user.username, hero)

    return json.dumps(d)


@app.route("/profile", method="POST")
@sessions.start
@metrics.collect
def profile(session, user, db):
    if user is None:
        return error_dict

    stats = users.user_stats_for_user(db, user)
    matches = db.query(MatchResult).filter(MatchResult.user_id == user.id).all()
    won = 0
    lost = 0
    for m in matches:
        if m.result == "won":
            won += 1
        if m.result == "lost":
            lost += 1

    print "Profile request for user %s: w/l: %d/%d" % (user.username, won, lost)

    d = {
        "result": 1,
        "username": user.screenname,
        "xp_level": stats.xp_level,
        "xp_amount": stats.xp_current,
        "xp_next": stats.xp_next,
        "rating": users.user_elo_to_rank(db, user),
        "ladder": stats.ladder_value,
        "cash": stats.soft_money,
        "hardcash": stats.hard_money,
        "wins": won,
        "lost": lost,

        "selectable_heroes":user.selectableHeroes,
        "viewable_heroes":user.viewableHeroes
    }

    print "Profile: " + str(d)
    return json.dumps(d)


@app.route("/friend_list", method="POST")
@sessions.start
@metrics.collect
def friend_list(session, user, db):
    if user is None:
        return error_dict

    #print "Friend list request from %s" % (user.username,)
    d = {"result": 1, "friends":[] }
    # friends = users.user_get_friends( db, user )
    # currently everyone is friends with everyone TODO: uncomment the line above for proper functionality
    # friends = db.query(User).filter(User.allow_login == True, User.id != user.id).all()
    friends = []
    for uid, u_user in sessions.getUsersDictItems():
        if isinstance( u_user, UserState.UserState ):
            friends.append( u_user )

    try:
        for f in friends:
            f_user = f #  sessions.getUserById(f.id)

            online = False
            status = "Offline"
            rating = f.rating
            if isinstance(f_user, UserState.UserState):
                if f_user.loggedIn:
                    f_user.logoutIfIdle()
                    if f_user.loggedIn == False:
                        finalizeLogout( db, f_user )
                rating = f_user.dbStats.rating
                level = f_user.dbStats.xp_level
                ladder = f_user.dbStats.ladder
                status = f_user.status
                if user.match is not None and f_user.loggedIn:
                    if user.match.state <= MatchEntry.MATCH_STATE_PLAYERS_READY:
                        status = "Idle"
                    elif user.match.state == MatchEntry.MATCH_STATE_STARTED:
                        status = "In Battle"
                online = f_user.loggedIn
            else:
                f_stats = users.user_stats_for_user(db, f)
                level = f_stats.xp_level


            if online and f_user is not user:
                f_dict = { "username": f.screenname, "user_id": f.id, "online": online, "status": status,
                          "rating": users.elo_to_rank(rating),  "xp_level": level, "ladder":ladder, "steam_id":str(f.steamId) }
                sent_inv = user.getInviteSentTo( f.username )
                if sent_inv:
                    f_dict["invite_sent"] = True
                    f_dict["invite_accepted"] = sent_inv.accepted
                    f_dict["invite_acknowledged"] = sent_inv.acknowledged
                    f_dict["invite_token"] = sent_inv.inviteToken

                d["friends"].append(f_dict)
        #if len( d["friends"] ) == 0:
        #    del d["friends"]
        user.cullSentInvites()

    except Exception as e:
        print e.message

    return json.dumps(d)


@app.route("/friend_request_send", method="POST")
@sessions.start
@metrics.collect
def friend_request_send(session, user, db):
    if user is None:
        return error_dict
    d = {"result": 0}

    try:
        request_dict = json.loads(request.forms["request_data"])
        #print "Friend request with request_dict %s" % (str(request_dict),)
        #uid = int( request_dict[ "user_id"] )
        uname = request_dict["username"]
        receiver = db.query(User).filter(User.username == uname).first()

        print "Friend request: user %s wants to friend user %d" % (user.username, receiver.id)

        if not users.user_is_friends_with(db, user, receiver.id):
            friendreq = FriendRequest(user.id, receiver.id)
            db.add(friendreq)
            db.commit()

    except Exception as e:
        print "Exception in friend_request_send: " + e.message

    return json.dumps(d)


@app.route("/friend_request_reply", method="POST")
@sessions.start
@metrics.collect
def friend_request_reply(session, user, db):
    if user is None:
        return error_dict

    d = {"result": 0}
    try:
        request_dict = json.loads(request.forms["request_data"])
        #print "Friend request reply with request_dict %s" % (str(request_dict),)

        token = int(request_dict["token"])
        cmd = request_dict["cmd"]

        print "Friend reply: %s from user %s" % ( cmd, user.username )

        invite = db.query(FriendRequest).filter(FriendRequest.id == token,
                                                FriendRequest.receiver_user_id == user.id).first()
        if invite is not None and cmd in ("accept", "reject") and not users.user_is_friends_with(db, user,
                                                                                                 invite.sender_user_id):
            if cmd == "accept":
                invite.accepted = True
                d["result"] = 1

                assoc = FriendAssociation(invite.receiver_user_id, invite.sender_user_id)
                assoc2 = FriendAssociation(invite.sender_user_id, invite.receiver_user_id)

                db.add(assoc)
                db.add(assoc2)
            else:
                invite.delete()
            db.commit()

    except Exception as e:
        print "Exception in friend_request_reply: " + e.message

    return json.dumps(d)


@app.route("/friend_invite_send", method="POST")
@sessions.start
@metrics.collect
def friend_invite_send(session, user, db):
    if user is None:
        return error_dict
    d = {"result": 0}

    try:
        request_dict = json.loads(request.forms["request_data"])

        print "Game invite with %s" % (str(request_dict),)
        uid = int(request_dict["user_id"])
        target_user = sessions.getUserById(uid)

        print "Game invite from %s to user id %d to match %s" % (user.username, uid, str(user.match))
        if user.match is None:
            print "User does not have an active match; invite canceled"
        elif not isinstance(target_user, UserState.UserState):
            print "User is not online; invite canceled"
        else:
            receive_u = db.query(User).filter(User.id == uid).first()
            oldreqs = db.query(GameInvite).filter(GameInvite.sender_user_id == user.id,
                                                  GameInvite.receiver_user_id == receive_u.id,
                                                  GameInvite.accepted == False).all()
            if len(oldreqs) > 0 or sessions.getUserById(receive_u.id).match is not None:
                print "Will reject invite; receiver already has a pending invite from this user or receiver is already in a match!"
                d["reason"] = "User cannot receive invite; already invited or already in a party."
            else:
                # if users.user_is_friends_with( db, user, uid ):
                # TODO: we do it like this as long as everyone is friends with everyone
                f_user = sessions.getUserById( receive_u.id )
                if f_user.loggedIn:
                    gi = GameInvite(uid, user.id)
                    db.add(gi)
                    db.commit()
                    # clear all pending match requests as we are going to accept a new one
                    clear_matchreqs_for_user(db, user)
                    d["result"] = 1
                    d["token"] = gi.id
                else:
                    d["reason"] = "User is not online!"
    except Exception as e:
        print "Exception in friend_invite_send: " + e.message

    return json.dumps(d)


@app.route("/friend_invite_cancel", method="POST")
@sessions.start
@metrics.collect
def friend_invite_cancel(session, user, db):
    if user is None:
        return error_dict
    d = {"result": 0}

    try:
        request_dict = json.loads(request.forms["request_data"])
        print "Game invite cancel with %s" % (str(request_dict),)
        token = int(request_dict["token"])

        print "Game invite cancel from %s, token %d" % (user.username, token)
        invite = db.query(GameInvite).filter(GameInvite.id == token, GameInvite.sender_user_id == user.id,
                                             GameInvite.accepted == False).first()   # cant un-accept already accepted reqs
        if invite is not None:
            print "Invite found, deleting it..."
            db.delete(invite)
            db.commit()
            d["result"] = 1
        else:
            d["reason"] = "No such invite, already cancelled or rejected by receiver?"

    except Exception as e:
        print "Exception in friend_invite_cancel " + e.message

    return json.dumps(d)


@app.route("/friend_invite_reply", method="POST")
@sessions.start
@metrics.collect
def friend_invite_res(session, user, db):
    if user is None:
        return error_dict
    d = {"result": 0}

    try:
        request_dict = json.loads(request.forms["request_data"])
        print "Game invite reply with %s" % (str(request_dict),)
        token = int(request_dict["token"])
        cmd = request_dict["cmd"]

        print "Game invite reply from %s: %s with token %d" % (user.username, cmd, token)

        invite = db.query(GameInvite).filter(GameInvite.id == token, GameInvite.receiver_user_id == user.id,
                                             GameInvite.game_created == False).first()
        if invite is not None and cmd in ("accept", "reject"):
            if cmd == "accept":
                # clear all pending match requests as we are going to accept a new one
                clear_matchreqs_for_user(db, user)

                print "Invite accepted"
                invite.accepted = True

                recv_u = db.query(User).filter(User.id == invite.receiver_user_id).first()
                send_u = db.query(User).filter(User.id == invite.sender_user_id).first()

                recv_user = sessions.getUserById(recv_u.id)
                send_user = sessions.getUserById(send_u.id)

                #send_user.refreshFromDb( db )
                #recv_user.refreshFromDb( db )
                send_user.match.playerJoin(recv_user)
                d["result"] = 1

            else:
                print "Deleting invite"
                db.delete(invite)
                d["result"] = 1
            db.commit()
        else:
            d["reason"] = "Invite has been cancelled"

    except Exception as e:
        print "Exception in friend_invite_reply " + e.message

    return json.dumps(d)

@app.route( "/match/find_new/<action>", method="POST" )
@sessions.start
@metrics.collect
def match_find_new( session, user, db, action ):
    if user is None:
        return error_dict

    try:
        d = { "result":0 }

        if action == "start":
            if user.match is not None and user.match.canStartMatchmaking():
                user.match.startMatchmaking( matchmakingEngine )
                d["result"] = 1
        elif action == "end":
            if user.match is not None and user.match.matchmakingGroup is not None:
                user.match.endMatchmaking( matchmakingEngine )
                d["result"] = 1
        elif action == "state":
            d["result"] = 0
            d["ready"] = True if user.match is not None and user.match.matchType == MatchEntry.MATCH_TYPE_MATCHMAKING_DONE else False
            if user.match is not None and user.match.matchmakingGroup is not None:
                group = user.match.matchmakingGroup
                if (datetime.now() - matchmakingEngine.lastPassTimestamp).seconds > 2:
                    mm_pass_results = matchmakingEngine.doPass()
                    if len(mm_pass_results) > 0:
                        # create new matches; make sure old matches are closed and removed
                        for mm_res in mm_pass_results:
                            # any mm_res here is no longer in the matchmaking queue!

                            t1_players = []
                            t2_players = []
                            for pg in mm_res.teams[0]:
                                t1_players += pg.players
                            for pg in mm_res.teams[1]:
                                t2_players += pg.players

                            for p in t1_players + t2_players:
                                clear_matchreqs_for_user( db, p )
                                # nasty, but to make sure...
                                if p.match:
                                    p.leftMatch( p.match )
                                p.matchmakingGroup = None

                            match = MatchEntry.MatchEntry( "matchmaking_done", t1_players[0] )
                            match.resize( matchmakingEngine.teamSize )
                            i = 0
                            for p in t1_players:
                                match.playerJoin( p, 1, i )
                            i = 0
                            for p in t2_players:
                                match.playerJoin( p, 2, i )

                            match.setTimer( 30 )
                            activeMatches[match.token] = match

                d["eta"] = matchmakingEngine.getAverageResultTime()
                d["queue_length"] = len(matchmakingEngine.queue)
                d["last_result_size"] = matchmakingEngine.gameSize - group.lastPassEmptySlots if group.lastPassEmptySlots != -1 else 0
                d["target_size"] = matchmakingEngine.gameSize
                # NOTE these are actually seconds since
                d["start_timestamp"] = (datetime.now() - group.creationTime).seconds
                d["last_pass_timestamp"] = (datetime.now() - group.lastPassTime).seconds
                d["result"] = 1

    except AssertionError as a:
        print "Assertion error in match_find_new: " + str(a)
        _, _, tb = sys.exc_info()
        traceback.print_tb(tb) # Fixed format
    except Exception as e:
        print "Exception in match_find_new: " + str(e)

    return json.dumps(d)



match_queue = []
@app.route("/match/find/<action>", method="POST")
@sessions.start
@metrics.collect
def match_find(session, user, db, action):
    if user is None:
        return error_dict

    print "Match find for user %s with action %s" % (user.username, action)

    try:
        d = { "result":0 }
        if action == "start":
            if user not in match_queue and user.match is None:
                clear_matchreqs_for_user( db, user )
                match_queue.append( user )
                print "User %s added to match queue; queue is: %s" % (user.username, str(match_queue) )

                if len(match_queue) >= 2:
                    p1 = match_queue.pop()
                    p2 = match_queue.pop()
                    if p1.match is None and p2.match is None:
                        match = MatchEntry.MatchEntry("1v1", p1)
                        match.playerJoin(p1)
                        match.playerJoin(p2)
                        print "Created match %s; %s vs %s" % (match.token, p1.username, p2.username)
                        activeMatches[match.token] = match
            d["result"] = 1
        elif action == "end":
            if user in match_queue:
                match_queue.remove(user)
            d["result"] = 1
    except AssertionError as a:
        print "Assertion error in match_find: " + str(a)
        _, _, tb = sys.exc_info()
        traceback.print_tb(tb) # Fixed format
    except Exception as e:
        print "Exception in match_find: " + str(e)

    return json.dumps(d)


@app.route("/match/ranked/<command>", method="POST")
@sessions.start
@metrics.collect
def match_ranked( session, user, db, command):
    if user is None:
        return error_dict

    d = {"result":0 }
    try:
        request_dict = json.loads( request.forms["request_data"])

        if command == "find":
            if user.match is None and user not in discoveryEngine.matchmakingQueue:
                clear_matchreqs_for_user( db, user )
                discoveryEngine.startMatchmaking( user )
                members = string.join( discoveryEngine.memberNames(), ',' )
                print "%s added to matchmaking queue; length=%d; members=%s" % (user.username, len(discoveryEngine.matchmakingQueue),members)
                m = discoveryEngine.matchmakingPass1v1()
                if m is not None:
                    assert ( not activeMatches.has_key(m.token) )
                    activeMatches[m.token] = m

                    print "Discovery discovered match %s" % (m.token, )
                d["result"] = 1
        elif command == "end":
            discoveryEngine.endMatchmaking( user )
            members = string.join( discoveryEngine.memberNames(), ',' )
            print "%s removed from matchmaking queue; length=%d; members=%s" % (user.username, len(discoveryEngine.matchmakingQueue),members)
            d["result"] = 1

    except AssertionError as a:
        print "Assertion error in match_ranked: " + str(a)
        _, _, tb = sys.exc_info()
        traceback.print_tb(tb) # Fixed format
    except Exception as e:
        print "Exception in match_ranked: " + str(e)
        _, _, tb = sys.exc_info()
        traceback.print_tb(tb) # Fixed format

    return json.dumps(d)

@app.route("/match/create", method="POST")
@sessions.start
@metrics.collect
def match_create(session, user, db):
    if user is None:
        return error_dict
    d = {"result": 0}

    try:
        request_dict = json.loads(request.forms["request_data"])
        #print "match_create: %s with dict %s" % (user.username, str(request_dict))

        map_pref = request_dict["map_preference"] if request_dict.has_key("map_preference") else ALLOWED_MAPS[random.randint( 0, RANDOM_MAP_LAST_INDEX ) ]
        match_type = request_dict["type"]
        game_mode = request_dict["game_mode"] if request_dict.has_key( "game_mode") else match_type
        tutorial = request_dict["tutorial"] if request_dict.has_key("tutorial") else False

        if user.match is None:
            clear_matchreqs_for_user( db, user )
            match = MatchEntry.MatchEntry(game_mode, user)
            match.isTutorial = tutorial

            #print match.token
            match.playerJoin(user)

            assert ( not activeMatches.has_key(match.token) )
            activeMatches[match.token] = match

            d["result"] = 1
            d["token"] = match.token

            if tutorial:
                print "Match is tutorial; autostarting..."
                for p in match.players.keys():
                    match.players[p].matchItemsAndProcsDict = tutorial_item_with_procs()  #user_items_with_procs( db, match.players[p] )
                match.create(db)
                create_match_new( db, match.mapPreference, match.token, user.match, all_db_items, all_db_gems, isTutorial=True )


    except AssertionError as a:
        print "Assertion error in match_create: " + str(a)
        _, _, tb = sys.exc_info()
        traceback.print_tb(tb) # Fixed format
    except Exception as e:
        print "Exception in match_create: " + str(e)
        _, _, tb = sys.exc_info()
        traceback.print_tb(tb) # Fixed format

    #print "match_create: " + json.dumps(d)
    return json.dumps(d)


@app.route("/match/join", method="POST")
@sessions.start
@metrics.collect
def match_join(session, user, db):
    if user is None:
        return error_dict
    d = {"result": 0}

    try:
        request_dict = json.loads(request.forms["request_data"])
        print "match_join: %s with dict %s" % (user.username, str(request_dict))

        # no joining other matches when in matchmaking match
        if user.match is not None and (user.match.typeString() == "matchmaking" or user.match.typeString() == "matchmaking_done"):
            return json.dumps(d)

        token = request_dict["token"]
        if user.match is not None:
            user.match.playerLeave( user )

        assert ( activeMatches.has_key(token) )

        match = activeMatches[token]

        if match.typeString() == "matchmaking":
            match.playerJoin(user, 1, -1 )

        elif match.matchType != "ranked":
            team = -1 if not request_dict.has_key( "team" ) else request_dict["team"]
            index = -1 if not request_dict.has_key( "index" ) else request_dict["index"]

            match.playerJoin(user, team, index)
            clear_matchreqs_for_user( db, user )

            d["result"] = 1

    except Exception as e:
        print "Exception in match_join: " + str(e)
        _, _, tb = sys.exc_info()
        traceback.print_tb(tb) # Fixed format

    return json.dumps(d)


@app.route("/match/leave", method="POST")
@sessions.start
@metrics.collect
def match_leave(session, user, db):
    if user is None:
        return error_dict
    d = {"result": 0}

    if user.match is not None and user.match.token in activeMatches.keys():
        try:
            request_dict = json.loads(request.forms["request_data"])

            assert ( user.match is not None )
            token = user.match.token

            assert ( token in activeMatches.keys() )
            match = activeMatches[token]
            match.playerLeave(user)

            if match.creator == None and len(match.players.keys()) == 0:
                del activeMatches[token]


            d["result"] = 1
        except Exception as e:
            print "Exception in match_leave: " + e.message

    return json.dumps(d)


@app.route("/match/state", method="POST")
@sessions.start
@metrics.collect
def match_state(session, user, db):
    if user is None:
        return error_dict
    d = {"result": 0}

    try:
        request_dict = json.loads(request.forms["request_data"])
        #print "match_state: %s with dict %s" % (user.username, str(request_dict))

        if user.match is not None:
            token = user.match.token

            assert ( token in activeMatches.keys() )
            match = activeMatches[token]

            #user.refreshFromDb( db )

            d["result"] = 1
            d["token"] = match.token
            d["state"] = match.state
            d["type"] = match.typeString()
            d["game_mode"] = match.typeString()
            d["game_type"] = match.typeString()
            d["host_username"] = match.creator.screenname
            d["max_players_per_team"] = match.playersPerTeam
            d["matchmaking_active"] = True if match.matchmakingGroup is not None else False
            d["map"] = match.mapPreference

            timer = -1
            if match.startTimer is not None:
                if match.startTimer > datetime.now():
                    timer = (match.startTimer - datetime.now()).seconds
                else:
                    timer = 0
            d["timer"] = timer

            d["players"] = []
            for team in range(1,3):
                i = 0
                for i in range( 0, len( match.teams[team])):
                    p = match.teams[team][i]
                    if p is None:
                        continue

                    if isinstance( p, UserState.UserState ):
                        p_dict = { "index":i, "team":team, "username": p.screenname, "type":"human", "is_ready":p.readyToPlay,
                                   "control_type":"master" if i == 0 else "hero_only", "rank_string": users.elo_to_rank(p.dbStats.rating), "level": p.dbStats.xp_level,
                                   "selected_hero":p.selectedHero }
                        d["players"].append(p_dict)
                    else:
                        p_dict = { "index":i, "team":team, "username":"AI", "type":"ai", "ai_difficulty":p.difficulty, "selected_hero":p.selectedHero,
                                   "is_ready":True, "control_type":"master" if i == 0 else "hero_only", "rank_string":"A", "level":1 }
                        d["players"].append(p_dict)
                    i += 1

            if match.typeString() == "matchmaking_done" and timer == 0 and match.state < MatchEntry.MATCH_STATE_CREATED:
                with match.lock:
                    print "TIMER ZERO on match %s: AUTOSTARTING" % (match.token,)
                    all_players = []
                    for p in match.players.keys():
                        #match.players[p].refreshFromDb( db )
                        match.players[p].matchItemsAndProcsDict = user_items_with_procs( db, match.players[p] )
                        all_players.append(match.players[p])
                    match.create(db)
                    #create_match_with_users(db, match.token, all_players, all_db_items, all_db_gems, difficulty)
                    # create_1v1_match_with_users( db, match.token, all_db_items, all_db_gems, all_players[0].dbUser, all_players[1].dbUser )
                    create_match_new( db, match.mapPreference, match.token, user.match, all_db_items, all_db_gems )
        else:
            d["type"] = "ranked" if discoveryEngine.isUserMatchmaking(user) else "none"
    except AssertionError as a:
        print "Assertion error in match_state: " + str(a)
        _, _, tb = sys.exc_info()
        traceback.print_tb(tb) # Fixed format
    except Exception as e:
        print "Exception in match_state: " + str(type(e)) + str(e) + " = " + e.message
    # print "match_state for %s will return %s" % (user.username, str(d))
    return json.dumps(d)


@app.route( "/match/slot/<command>", method="POST")
@sessions.start
@metrics.collect
def match_slot( session, user, db, command ):
    if user is None:
        return error_dict
    d = {"result": 0}

    try:
        request_dict = json.loads(request.forms["request_data"])
        if user.match is not None:
            if command == "kick":
                if user.match.creator is user:
                    team = int( request_dict["team"] )
                    slot = int( request_dict["index"] )
                    user.match.kickSlot( team, slot )
                    print "Kicked slot %d of team %d on match %s" % (slot, team, user.match.token)
                    d["result"] = 1
            if command == "swap":
                # no swapping in matchmade lobbies
                if user.match.matchTypeString() in ("matchmaking", "matchmaking_done"):
                    return json.dumps(d)

                from_team = int( request_dict["from_team"] )
                from_slot = int( request_dict["from_index"] )
                to_team = int( request_dict["to_team"] )
                to_slot = int( request_dict["to_index"] )

                src = user.match.teams[from_team][from_slot]
                tgt = user.match.teams[to_team][to_slot]

                if user.match.creator is user or ( (src is None and tgt is user) or (src is user and tgt is None) ):
                    user.match.swap( from_team, from_slot, to_team, to_slot )
                    print "Swapped slot %d on team %d with slot %d on team %d on match %s" % (from_team, from_slot, to_team, to_slot, user.match.token)
                    d["result"] = 1
    except Exception as e:
        print "Exception in match_slot: " + e.message

    return json.dumps(d)

@app.route( "/match/resize", method="POST" )
@sessions.start
@metrics.collect
def match_resize( session, user, db ):
    if user is None:
        return error_dict
    d = {"result": 0}

    try:
        request_dict = json.loads(request.forms["request_data"])
        newsize = request_dict["new_size"]
        if user.match is not None and user.match.creator is user:
            user.match.repack( False )
            user.match.resize( newsize )
            #print "%s resized match %s to %d users" % (user.username, user.match.token, newsize)

    except Exception as e:
        print "Exception in match_resize: " + e.message
    return json.dumps(d)



@app.route( "/match/ai/<command>", method="POST" )
@sessions.start
@metrics.collect
def match_ai( session, user, db, command ):
    if user is None:
        return error_dict
    d = {"result": 0}

    try:
        request_dict = json.loads(request.forms["request_data"])
        if user.match is not None and user.match.creator is user:
            if command == "add":
                difficulty = request_dict["ai_difficulty"]
                hero = int( request_dict["selected_hero"] )
                team = int( request_dict["team"] )
                index = int( request_dict["index"] )
                user.match.addAI( team, index, hero, difficulty )
                print "Added new AI with difficulty %s hero %d to index %d" % (difficulty,hero, index)
                d["result"] = 1
            elif command == "set":
                team = int( request_dict["team"] )
                slot = int( request_dict["index"] )
                difficulty = request_dict["ai_difficulty"]
                hero = int( request_dict["selected_hero"] )
                if isinstance( user.match.teams[team][slot], MatchEntry.MatchAIPlayer ):
                    user.match.setAI( team, slot, hero, difficulty )
                    print "Set AI on team %d slot %d: hero=%d difficulty=%s" % (team, slot, hero, difficulty)
                    d["result"] = 1
                else:
                    print "Slot %d on team %d in match %s is not an AI player!" % (slot, team, user.match.token)

    except Exception as e:
        print "Exception in match_ai: " + e.message
    return json.dumps(d)


@app.route( "/match/invite", method="POST" )
@sessions.start
@metrics.collect
def match_invite( session, user, db ):
    if user is None or user.match is None:
        return error_dict
    d = {"result": 0}

    try:
        request_dict = json.loads(request.forms["request_data"])
        print "match_invite from %s: %s" % (user.username, str(request_dict))

        user_id = request_dict[ "user_id"]
        index = request_dict["index"]
        team = request_dict["team"]

        target_u = sessions.getUserById( user_id )
        if isinstance( target_u, UserState.UserState ) and user.match is not None:
            if user.match.typeString() != "matchmaking" and user.match.typeString() != "matchmaking_done":
                inv = target_u.inviteToMatch( user, user.match.token, team, index )
                user.sentMatchInvites.append( inv )
                d["result"] = 1
                print "User %s invited %s to match %s" % (user.username, target_u.username, user.match.token)

    except Exception as e:
        print "Exception in match_invite: " + e.message

    return json.dumps(d)

@app.route( "/invites/<command>", method="POST" )
@sessions.start
@metrics.collect
def invites_decline( session, user, db, command ):
    if user is None:
        return error_dict
    d = {"result": 0}

    try:
        request_dict = json.loads(request.forms["request_data"])
        invite_token = int( request_dict[ "invite_token"] )

        if command == "accept":
            user.acceptMatchInvite( invite_token )
            d["result"] = 1
        elif command == "decline":
            user.declineMatchInvite( invite_token )
            d["result"] = 1

    except AssertionError as a:
        print "Assertion error in invites_decline: " + str(a)
        _, _, tb = sys.exc_info()
        traceback.print_tb(tb) # Fixed format
    except Exception as e:
        print "Exception in invites_decline: " + str(type(e)) + str(e) + " = " + e.message
    return json.dumps(d)


@app.route("/match/control", method="POST")
@sessions.start
@metrics.collect
def match_control(session, user, db):
    if user is None or user.match is None:
        return error_dict
    d = {"result": 0}

    try:
        request_dict = json.loads(request.forms["request_data"])
        #print "match_control: %s with dict %s" % (user.username, str(request_dict))

        assert ( user.match is not None )
        token = user.match.token

        assert ( token in activeMatches.keys() )
        match = activeMatches[token]

        selected_hero = request_dict["selected_hero"]
        ready_state = request_dict["ready"]
        start_match = request_dict["start"]
        game_mode = request_dict["game_mode"] if request_dict.has_key( "game_mode") and len(request_dict["game_mode"]) > 0 else "1v1"
        difficulty = request_dict["difficulty"] if request_dict.has_key( "difficulty" ) else "medium"
        requested_map = request_dict["map"] if request_dict.has_key( "map" ) else "Random"

        if match.state in (MatchEntry.MATCH_STATE_PLAYERS_IN, MatchEntry.MATCH_STATE_OPEN):
            user.selectHero(selected_hero)
            user.setReadyState(ready_state)
            if user == match.creator and match.typeString() != "matchmaking_done":
                match.setGameType(game_mode)

            if user == match.creator and match.typeString() != "ranked" and len(requested_map) > 0 and (requested_map in ALLOWED_MAPS or requested_map == "Random"):
                if requested_map == "Random":
                    match.setMap( ALLOWED_MAPS[random.randint(0, RANDOM_MAP_LAST_INDEX)] )
                else:
                    match.setMap(requested_map)

        d["result"] = 1

        if start_match == True and (match.canStart() or match.isTutorial):
            with match.lock:
                print "%s wants to start match; created by %s, canStart=%s" % (
                    user.username, match.creator.username, match.canStart())
                if (match.creator is not None) and match.canStart():
                    print "User %s starts match: map=%s" % (user.username, match.mapPreference )
                    all_players = []
                    for p in match.players.keys():
                        #match.players[p].refreshFromDb( db )
                        match.players[p].matchItemsAndProcsDict = user_items_with_procs( db, match.players[p] )
                        all_players.append(match.players[p])
                    match.create(db)
                    #create_match_with_users(db, match.token, all_players, all_db_items, all_db_gems, difficulty)
                    # create_1v1_match_with_users( db, match.token, all_db_items, all_db_gems, all_players[0].dbUser, all_players[1].dbUser )
                    create_match_new( db, match.mapPreference, match.token, user.match, all_db_items, all_db_gems )
                else:
                    print "%s cannot start match, not creator or not ready" % (user.username, )
                    d["result"] = 0
                    if not match.canStart():
                        d["reason"] = "Cannot start match: All players are not ready!"
                    else:
                        d["reason"] = "Cannot start match: not match creator!"

    except AssertionError as a:
        print "Assertion error in match_control: " + str(a)
        _, _, tb = sys.exc_info()
        traceback.print_tb(tb) # Fixed format
    except Exception as e:
        print "Exception in match_control: " + str(type(e)) + str(e) + " = " + e.message
        _, _, tb = sys.exc_info()
        traceback.print_tb(tb) # Fixed format

    #print "match_control returns %s" % (str(d),)
    return json.dumps(d)


@app.route('/discover', method='POST')
@sessions.start
@metrics.collect
def match_discovery(session, user, db):
    # match status:
    # 0 - just created
    # 1 - communicated to the game server, but no reply yet
    # 2 - game server has acknowledged that the game is now created and is ready for players
    # 3 - at least one user has joined the game
    # 4 - all users have joined the game and the game is waiting to start
    # 5 - game has started
    # 6 - game has ended and the game server has reported about it
    # 7 - game has ended, relevant statistics have been written to the db and the game server has removed it
    #     (the game is considered closed after this)

    # match request status:
    # 0 - search just created, will start search on next pass
    # 1 - at least one search pass has been done, but no suitable match yet
    # 2 - match has been found and found_match_id has been updated
    # 3 - match has been found and joined by the player (this request is now closed)
    # 4 - match was found but was rejected by the player (this request is now closed)
    if user is None:
        return error_dict

    print "Match DISCOVER request from %s; removing previous requests..." % (user.username,)

    reqs = db.query(MatchRequest).filter(MatchRequest.user_id == user.id, MatchRequest.status == 0).delete()

    request_dict = json.loads(request.forms["request_data"])
    mr = create_matchrequest(db, user, "Concept1custom")

    ct = ""
    mt = ""

    if request_dict.has_key("matchtype") and request_dict.has_key("controltype"):
        ct = request_dict["controltype"]
        mt = request_dict["matchtype"]
        if mt not in ('1v1', '2v2') or ct not in ('master', 'heroonly', 'hero'):
            return error_dict

        if ct == "heroonly":
            ct = "hero"

        mr.controltype = ct
        mr.gametype = mt
    else:
        ct = "master"
        mt = "1v1"

    mr.matchtype = mt
    mr.controltype = ct
    db.commit()

    matchmaking_pass(db, all_db_items, all_db_gems, user_equip_sheet_dict)
    d = {"result": 1, "map": mr.map_preference}
    return json.dumps(d)


@app.route('/discover_cancel', method='POST')
@sessions.start
@metrics.collect
def discover_cancel(session, user, db):
    if user is None:
        return error_dict

    print "Discovery CANCEL from %s; removing match requests" % (user.username,)
    clear_matchreqs_for_user(db, user)


@app.route("/beta_match_feedback", method="POST")
@sessions.start
@metrics.collect
def beta_match_feedback(session, user, db):
    if user is None:
        return error_dict

    request_dict = json.loads(request.forms["request_data"])

    try:
        token = request_dict["token"]
        rating = request_dict["rating"]
        feedback = request_dict["feedback"]
        mr = matchresult_for_user(db, user, token)
        if mr is not None:
            fb = BetaFeedback(token, user.id)
            fb.rating = int(rating)
            fb.feedback = feedback
            db.add(fb)
            db.commit()
            print "Wrote feedback from user %d on match %s" % (user.id, token)
    except Exception:
        print "Exception while getting feedback from user %d" % (user.id,)
        return error_dict

    return json.dumps({"result": 1})

@app.route("/interal_frontend_shutdown/<backend_name>", method="GET")
@metrics.collect
def internal_backend_shutdown(db, backend_name):
    print "Backend %s reports completed shutdown." % (backend_name,)
    pass


@app.route('/internal_match_stat_update/<token>/<update_type>', method="POST")
@metrics.collect
def internal_match_stat_update( db, token, update_type ):
   
    print "Internal match stat update for match %s: %s" % (token, update_type)
    upd_dict = json.loads(request.forms["request_data"])
    print" Update dict is: %s " % (str(upd_dict),)

    match = db.query(Match).filter_by(token=token).one()
    if match is not None:

        if update_type == "basic":
            bi = db.query(MatchBasicInfo).filter_by( match_id=match.id ).one()
            if bi is not None:
                bi.duration = int(upd_dict["duration"])
                bi.winning_team = int(upd_dict["winning_team"])
                bi.tickets_team1 = int(upd_dict["tickets_team1"])
                bi.tickets_team2 = int(upd_dict["tickets_team2"])
                db.commit()
            print "Basic match info updated for match %s" % (token,)
        if update_type == "player":
            players = upd_dict["players"]
            for player_dict in players:
                pi = db.query( MatchPlayerInfo).filter_by( match_id=match.id, player_match_index = player_dict["player_match_index"] ).one()
                if pi is not None:
                    print "Match player info update for player index %d (%s)" % (player_dict["player_match_index"], player_dict["player_name"] )
                    keys = ( "level", "total_experience", "kills", "creep_kills", "deaths", "captures", "gold_collected", "total_damage_out", "total_damage_in", "potions_collected" )
                    pd = player_dict
                    pi.level = pd["level"]
                    pi.total_experience = pd["total_experience"]
                    pi.kills = pd["kills"]
                    pi.creep_kills = pd["creep_kills"]
                    pi.deaths = pd["deaths"]
                    pi.captures = pd["captures"]
                    pi.gold_collected = pd["gold_collected"]
                    pi.total_damage_out = pd["total_damage_out"]
                    pi.total_damage_in = pd["total_damage_in"]
                    pi.potions_collected = 0
            db.commit()
        if update_type == "player_events":
            pass
        if update_type == "team_events":
            pass
    else:
        print "Internal stat update could not find match %s" % (token,)

@app.route('/internal_match_surrender/<token>/<player_id>', method="GET")
@metrics.collect
def internal_match_surrender(db, token, player_id):
    try:
        player_id = int(player_id)
        print "Internal match SURRENDER from match %s for player id %d" % (token, player_id)
        # match = db.query(Match).filter_by( token=token ).one()
        res = db.query(MatchResult).filter_by( match_token=token, user_id=player_id ).one()
        stats = db.query(UserStats).filter_by( user_id=player_id ).one()

        oldxp = stats.xp_current
        oldlevel = stats.xp_level
        oldrating = stats.rating
        oldladder = stats.ladder_value
        oldsoftmoney = stats.soft_money
        oldhardmoney = stats.hard_money

        res.result = "surrender"
        res.old_hard_money = oldhardmoney
        res.new_hard_money = oldhardmoney
        res.old_soft_money = oldsoftmoney
        res.new_soft_money = oldsoftmoney
        res.old_ladder = oldladder
        res.new_ladder = oldladder
        res.old_level = oldlevel
        res.new_level = oldlevel
        res.old_rating = oldrating
        res.new_rating = oldrating
        res.old_xp = oldxp
        res.new_xp = oldxp

        db.commit()
    except Exception as e:
        print "Exception while trying to accept surrender: %s" % (e.message,)


@app.route('/internal_match_update/<token>/<state>', method="GET")
@metrics.collect
def internal_match_update(db, token, state):
    print "Internal match update of %s to state %s" % (token, state)
    d = {"result": 1}

    match = db.query(Match).filter_by(token=token).one()
    print "Internal match update for %s; match=%s" % (token, str(match))
    if match is not None:
        if state == "terminated":
            #
            match.status = MATCH_STATUS_ENDED
            res = matchresults_for_token(db, token)
            for r in res:
                user = db.query(User).filter_by(id=r.user_id).first()
                stats = users.user_stats_for_user(db, user)
                r.result = "unfinished"
                r.old_xp = r.new_xp = stats.xp_current
                r.old_level = r.new_level = stats.xp_level
                r.old_rating = r.new_rating = stats.rating
                r.end_time = datetime.now()
            db.commit()
            if activeMatches.has_key(match.token):
                activeMatches[match.token].close()
                del( activeMatches[match.token] )

        if state == "created":
            match.status = MATCH_STATUS_CREATED
            db.commit()

        if state == "join":
            join_user = request.query.user
            if len(join_user) == 0:
                pass
            match.status = 3
            db.commit()
            pass

        if state == "waitstart":
            match.status = 4
            db.commit()
            pass

        if state == "started":
            if activeMatches.has_key(match.token):
                activeMatches[match.token].start()
            match.status = MATCH_STATUS_STARTED
            #match.start_time = datetime.now()
            db.commit()

        if state == "ended":
            print "Will end match; winners="+str(request.query.winners)
            match.status = MATCH_STATUS_ENDED

            was_tutorial = False

            if activeMatches.has_key(match.token):
                was_tutorial = activeMatches[match.token].isTutorial
                activeMatches[match.token].close()

            wlist = None
            if len(request.query.winners) > 0:
                print "Match %s winners: %s" % (match.token, request.query.winners )
                wlist = request.query.winners.split(",")
            else:
                print "Match %s has no winners (empty winner list)" % (match.token,)
                wlist = []

            match_stats = json.loads(request.query.stats)

            print "Reported match stats: %s" % (str(match_stats),)

            winner_names = []
            loser_names = []
            reqs = matchresults_for_token(db, token)

            old_rating_dict = {}
            if len(reqs) == 0:
                for r in reqs:
                    r.result = "draw"
                    db.commit()
            else:
                for r in reqs:
                    if r.result != "surrender":
                        user = db.query(User).filter_by(id=r.user_id).first()
                        stats = users.user_stats_for_user(db, user)
                        if str(r.user_id) in wlist:
                            r.result = "won"
                            old_rating_dict["winner"] = (r.user_id, stats.rating)
                        else:
                            r.result = "lost"
                            old_rating_dict["loser"] = (r.user_id, stats.rating)
                        print "Marking game result for user id %d: %s" % (r.user_id, r.result)
                db.commit()

            for r in reqs:
                if r.result == "surrender":  # user has already surrendered
                    print "Ignoring stat update for player id %d; already surrendered" % (r.user_id,)
                    continue

                user = db.query(User).filter_by(id=r.user_id).first()
                stats = users.user_stats_for_user(db, user)
                oldxp = stats.xp_current
                oldlevel = stats.xp_level
                oldrating = stats.rating
                oldladder = stats.ladder_value
                oldsoftmoney = stats.soft_money
                oldhardmoney = stats.hard_money

                mt = activeMatches[match.token].matchType

                # get active user boosters and apply them
                boosters = db.query( UserBooster ).filter( UserBooster.id==r.user_id, UserBooster.expiry_timestamp > datetime.now() )
                experience_multiplier = 1.0
                token_multiplier = 1.0
                for b in boosters:
                    if b.booster_type == "experience" and b.multiplier > experience_multiplier:
                        experience_multiplier = b.multiplier
                    if b.booster_type == "token" and b.multiplier > token_multiplier:
                        token_multiplier = b.multiplier


                if experience_multiplier > 1.0:
                    print "User has active experience booster with boost multiplier %4.2f" % (experience_multiplier, )

                if token_multiplier > 1.0:
                    print "User has active token booster with boost multiplier %4.2f" % (token_multiplier, )

                # (exp_gain, money_gain, rnd_max), (exp_gain_win, money_gain_win, rnd_max_win)
                rewards_by_matchtype = (
                    ( (0, 0, 0), (0, 0, 0) ), # TYPE_NONE

                    ( (75, 100, 50), (250, 250, 100) ), # TYPE_PVP_1V1

                    ( (250, 200, 75), (400, 350, 125) ), # TYPE_PVP_2V2
                    ( (90, 50, 15), (100, 100, 25) ), # TYPE_SINGLE

                    ( (250, 100, 50), (500, 250, 100) ), # TYPE_2P_COOP
                    ( (250, 100, 50), (500, 250, 100) ), # TYPE_HEROES_ONLY_2V2
                    ( (250, 100, 50), (500, 250, 100) ),  # TYPE_DEBUG
                )

                mt = 1  # for now
                gained, money_gain, rnd_max = rewards_by_matchtype[mt][0]

                if r.result == "won":
                    gained, money_gain, rnd_max = rewards_by_matchtype[mt][1]

                # TODO: need proper ladder value math
                # no ladder change if AIs in play
                have_ais = match_had_ai_players( db, match.id )
                if was_tutorial:
                    have_ais = False   # ignore ai flag if this was the player's first tutorial

                match_str = "Played match"
                if have_ais:
                    gained /= 4
                    money_gain /= 4
                    rnd_max /= 4
                    match_str = "Played match (with AI)"

                ladder_change = 0.0
                tstr = activeMatches[match.token].typeString()
                if not have_ais and (tstr == "matchmaking" or tstr == "matchmaking_done"):
                    if r.result == "won":
                        if oldladder >= 10.0:
                            ladder_change = -0.5
                        else:
                            ladder_change = -0.25
                    else:
                        if oldladder >= 10.0:
                            ladder_change = 0.25
                        else:
                            ladder_change = 0.5
                    users.user_modify_ladder_value( db, user, ladder_change, token, "%s ladder change" % (match_str,))
                    print "User %s ladder value changed by %4.2f" % (user.username, ladder_change)
                else:
                    print "No ladder change for user %s: match had AI players or not ranked" % (user.username, )

                booster_exp = int( (gained * experience_multiplier) - gained )
                levelup = users.user_grant_experience(db, user, gained, token, "%s base experience gain" % (match_str,))
                if booster_exp > 0:
                    levelup = users.user_grant_experience( db, user, booster_exp, token, "Active booster extra experience" )


                rnd = random.randint(0, rnd_max)
                users.user_grant_soft_money(db, user, money_gain+rnd, token, "%s soft money gain + random adder of %d" % (match_str,rnd))
                #if levelup:
                #    reward_tokens = 400  # hardcoded for now
                #    users.user_grant_soft_money( db, user, reward_tokens, token, "%s level up token reward" % (match_str,) )

                booster_tokens = int( (rnd * token_multiplier ) - rnd )
                if booster_tokens > 0:
                    users.user_grant_soft_money( db, user, booster_tokens, token, "Active booster extra tokens" )

                if not have_ais and len(wlist) == 1 and old_rating_dict.has_key("winner") and old_rating_dict.has_key(
                        "loser"):   # rating changes only in 1v1
                    newranks = elo.newranks(old_rating_dict["winner"][1], old_rating_dict["loser"][1], 1.0, 0.0, 32.0,
                                            32.0)
                    if r.result == "won" and old_rating_dict["winner"][0] == r.user_id:
                        print "Adjusting ELO for match winner; user %d, old=%d new=%d " % (
                            r.user_id, stats.rating, newranks[0])
                        elodiff = int(newranks[0]) - stats.rating
                        users.user_modify_rating(db, user, elodiff, token, "Winner ELO rank change")
                        winner_names.append(user.username)
                    if r.result == "lost" and old_rating_dict["loser"][0] == r.user_id:
                        print "Adjusting ELO for match loser; user %d, old=%d new=%d " % (
                            r.user_id, stats.rating, newranks[1])
                        elodiff = int(newranks[1]) - stats.rating
                        users.user_modify_rating(db, user, elodiff, token, "Loser ELO rank change")
                        if int(newranks[1]) < 1400:
                            print "User would have ELO rating of <1400; granting %d rank points to equalize player" % (
                                1400 - int(newranks[1]))
                            users.user_modify_rating(db, user, 1400 - int(newranks[1]), token,
                                                     "Loser ELO rank reassign to 1400")
                        loser_names.append(user.username)

                stats = users.user_stats_for_user(db, user)

                r.end_time = datetime.now()
                r.old_xp = oldxp
                r.new_xp = stats.xp_current
                r.old_level = oldlevel
                r.new_level = stats.xp_level
                r.old_rating = oldrating
                r.new_rating = stats.rating
                r.old_ladder = oldladder
                r.new_ladder = stats.ladder_value
                r.old_soft_money = oldsoftmoney
                r.new_soft_money = stats.soft_money
                r.old_hard_money = oldhardmoney
                r.new_hard_money = stats.hard_money
                db.commit()

                possible_achs = users.eligible_postmatch_achievements(db, user, match_stats)
                for a in possible_achs:
                    m = users.hard_money_for_achievement(a)
                    user_ach = users.user_get_achievement_state(db, user, a)
                    if user_ach is None:
                        user_ach = Achievement(user.id, a, token)
                        db.add(user_ach)
                        users.user_grant_hard_money(db, user, m, token, "Achievement completition: %s" % (a,))
                        print "User %s completed achievement %s; granted %d units of hard currency" % (
                            user.username, a, m)
                db.commit()

        if state == "removed":
            match.status = 7
            db.commit()
            pass

    return json.dumps(d)


@app.route('/ping', method='POST')
@sessions.start
@metrics.collect
def ping(session, user, db):
    if user is None:
	if session is None:
            print "PING rejected for empty session (db error?)"
        print "PING rejected for sessid %s" % (session.session_id,)
        return error_dict

    d = {"result": 1}
    d["discovery_state"] = 0

    # update our own status
    if user.match is not None:
        user.match.touch()

    #match_requests = db.query(MatchRequest).filter(MatchRequest.user_id == user.id, MatchRequest.status == 3,
    #                                               MatchRequest.found_match_id > 0).all()
    user.touch()
    status = "Idle"
    #for mr in match_requests:
    #    m = match_for_id(db, mr.found_match_id)
    #    if m.status == MATCH_STATUS_STARTED:
    #        status = "In Battle"
    #        break

    if user.match is not None:
        if user.match.state <= MatchEntry.MATCH_STATE_PLAYERS_READY:
            status = "Idle"
        elif user.match.state == MatchEntry.MATCH_STATE_STARTED:
            status = "In Battle"
            if user.match.isTutorial:
                status = "In Tutorial"

    user.status = status
    mq = messageCenter.getUserQueue(user.username)

    if mq is not None:
        mq.touch()

    req = matchrequest_for_user(db, user)
    if req is not None and req.status == 2 and req.user_id == user.id:
        d["discovery_state"] = req.status
        if req.found_match_id > 0:
            match = db.query(Match).filter_by(id=req.found_match_id).one()
            if match is not None:
                d["server_host"] = BACKEND_SERVERS[match.server_id][0]
                d["server_port"] = BACKEND_SERVERS[match.server_id][1]
                d["server_match_token"] = match.token
            req.status = 3
            db.commit()

    # check if we are in a match that is state in_progress...
    friend_list = []
    #friend_invs = db.query(FriendRequest).filter(FriendRequest.receiver_user_id == user.id,
    #                                             FriendRequest.accepted == False).all()
    #for inv in friend_invs:
    #    u = db.query(User).filter(User.id == inv.sender_user_id).first()
    #    friend_list.append({"token": inv.id, "from_user": u.username})

    #game_invs = db.query(GameInvite).filter(GameInvite.receiver_user_id == user.id, GameInvite.accepted == False).all()
    #for gi in game_invs:
    #    u = db.query(User).filter(User.id == gi.sender_user_id).first()
    #    game_list.append({"token": gi.id, "from_user": u.username, "matchtype": "1v1"})
    game_list = []
    for mi in user.matchInvites:
        if mi.originator is not None and mi.originator.match is not None:
            game_list.append( { "token":mi.inviteToken, "match_token": mi.matchToken, "from_user":mi.originator.screenname, "matchtype":mi.originator.match.matchType,
                                "creation_time_delta":(datetime.now() - mi.creationTime).seconds, "from_user_level":mi.originator.dbStats.xp_level, "ladder":mi.originator.dbStats.ladder,
                                "team":mi.targetTeam, "index":mi.targetSlot, "steam_id":mi.originator.steamId } )

    #d["friend_requests"] = friend_list
    if len(game_list) > 0:
        d["match_invites"] = game_list

    # get count of users waiting for match in matchmaking
    #unresolved = db.query(MatchRequest).filter(MatchRequest.status < 2, MatchRequest.gametype == '1v1',
    #                                           MatchRequest.controltype == 'master').all()
    d["matchmaking_count"] = 0 #len(unresolved)
    d["current_match_token"] = user.match.token if user.match is not None else ""

    #print "PING from %s: %s" % (user.username, str(d) )
    d["sys_next_downtime"] = adminControl.getSecondsToDowntime()
    d["sys_message"] = adminControl.currentMessage
    d["sys_message_priority"] = adminControl.messagePriority
    d["sys_message_number"] = adminControl.messageNumber

    return json.dumps(d)


@app.route('/match_summary', method='POST')
@sessions.start
@metrics.collect
def match_summary( session, user, db ):
    if user is None:
        return error_dict

    d = {"result":0}
    request_dict = json.loads(request.forms["request_data"])

    if request_dict.has_key( "match" ):
        token = request_dict["match"]

        match = db.query(Match).filter_by(token=token).one()
        if match is not None:
            d["result"] = 1
            bi = db.query( MatchBasicInfo ).filter_by( match_id = match.id ).one()
            if bi is not None:
                basic_info = {
                    "type":bi.type_string,
                    "is_finished":True,
                    "map":match.map,
                    "tickets":bi.tickets,
                    "tickets_team1":bi.tickets_team1,
                    "tickets_team2":bi.tickets_team2,
                    "duration":bi.duration,
                    "winning_team":bi.winning_team
                }

            pis = db.query( MatchPlayerInfo ).filter_by( match_id = match.id ).all()
            player_info = []
            if pis is not None:
                for pi in pis:
                    pd = { "name":pi.player_name, "team":pi.team, "items":[], "gems":[],
                           "human":pi.human, "hero":pi.hero, "role":pi.role, "level":pi.level, "total_experience":pi.total_experience, "kills":pi.kills,
                           "creep_kills":pi.creep_kills, "deaths":pi.deaths, "captures":pi.captures, "gold_collected":pi.gold_collected,
                           "total_damage_out":pi.total_damage_out, "total_damage_in":pi.total_damage_in,"potions_collected":pi.potions_collected
                           }
                    player_info.append( pd )

        team_events = [
    #        { "time":0, "team":1, "event":"ticket_limit", "position":(0.0, 0.0, 0.0), "extra_data_1":"400", "extra_data_2":""},
    #        { "time":0, "team":2, "event":"ticket_limit", "position":(0.0, 0.0, 0.0), "extra_data_1":"400", "extra_data_2":""}
        ]

        player_events = [
    #       { "time":0, "player":"flumba", "event":"spawned", "position":(0.0, 0.0, 0.0), "extra_data_1":"", "extra_data_2":""},
    #        { "time":0, "player":"A BAD PLAYER", "event":"spawned", "position":(0.0, 0.0, 0.0), "extra_data_1":"", "extra_data_2":""}
        ]

        d[ "result"] = 1
        d[ "basic_info" ] = basic_info
        d[ "player_info" ] = player_info
        d[ "team_events" ] = team_events
        d[ "player_events" ] = player_events

    return json.dumps( d )


@app.route('/result', method="POST")
@sessions.start
@metrics.collect
def get_result(session, user, db):
    if user is None:
        return error_dict

    req = None
    res = None
    d = {"result": 0}

    req = matchrequest_for_user(db, user, 3)
    if req is not None:
        match = match_for_id(db, req.found_match_id)
        res = matchresult_for_user(db, user, match.token)
        if res is not None and res.result != 'in_progress':
            bi = db.query( MatchBasicInfo ).filter( MatchBasicInfo.match_id == match.id ).one()

            exp_evts = db.query(UserStatEvent).filter(UserStatEvent.user_id == user.id,
                                                      UserStatEvent.match_token == match.token,
                                                      UserStatEvent.field_name == "xp_current",
                                                      UserStatEvent.change_type == "inc").all()
            exp_evt_d = {}
            for evt in exp_evts:
                d[evt.change_type] = evt.change_amount

            exp_level_evts = db.query(UserStatEvent).filter(UserStatEvent.user_id == user.id,
                                                      UserStatEvent.match_token == match.token,
                                                      UserStatEvent.field_name == "xp_next",
                                                      UserStatEvent.change_type == "assign").order_by( UserStatEvent.change_amount ).all()
            exp_level_evt_l = []
            for evt in exp_level_evts:
                exp_level_evt_l.append( evt.old_value )  # use the change amount as they are assign events

            have_ais = match_had_ai_players( db, req.found_match_id )

            d["result"] = 1
            d["match_type"] = "custom" if bi.type_string == "custom" else "ranked"
            d["match_result"] = res.result
            d["old_xp"] = res.old_xp
            d["new_xp"] = res.new_xp
            d["old_level"] = res.old_level
            d["new_level"] = res.new_level
            d["old_rating"] = res.old_rating
            d["new_rating"] = res.new_rating
            d["old_rating_str"] = users.elo_to_rank(res.old_rating)
            d["new_rating_str"] = users.elo_to_rank(res.new_rating)
            d["old_ladder"] = res.old_ladder
            d["new_ladder"] = res.new_ladder
            d["xp_limit_old"] = users.level_limit_for_exp(res.old_xp)
            d["xp_limit_new"] = users.level_limit_for_exp(res.new_xp)
            d["old_tokens"] = res.old_soft_money
            d["new_tokens"] = res.new_soft_money
            d["old_diamonds"] = res.old_hard_money
            d["new_diamonds"] = res.new_hard_money

            d["xp_limit_previous"] = users.xp_required_for_level( res.old_level-1 )
            d["xp_limit_next"] = users.xp_required_for_level( res.new_level )

            d["xp_events"] = exp_evt_d
            d["xp_limits_reached"] = exp_level_evt_l
            d["xp_bonuses"] = {}

            db.delete(req)
            db.commit()

    print "get result, req="+repr(req)+" res="+repr(res)+"  => " + json.dumps(d)
    return json.dumps(d)


@app.route("/mqueue", method="POST")
@sessions.start
@metrics.collect
def mqueue_status(session, user, db):
    if user is None:
        return error_dict

    # print "User %s reading message queue" % (user.username, )
    d = {"result": 0}
    mq = None
    try:
        chanlist = []
        mq = messageCenter.getUserQueue(user.username)
        if mq is not None:
            for c in mq.channels:
                ch = messageCenter.getChannel(c)
                d = {"channelname": ch.channelname, "channeltype": ch.channeltype,
                     "activity": (datetime.now() - ch.lastMessage).seconds, "usercount": len(ch.userQueues)}
                chanlist.append(d)
    except Exception as e:
        print "Exception while reading message queue: %s" % (e.message,)

    if mq is not None:
        d = {"result": 1, "pending": mq.size(), "channels": chanlist}

    #print "will return %s" % (str(d),)
    return json.dumps(d)


@app.route("/mqueue/<command>", method="POST")
@sessions.start
@metrics.collect
def mqueue_command(session, user, db, command):
    if user is None:
        return error_dict

    d = {"result": 0}
    request_dict = json.loads(request.forms["request_data"])

    try:
        if command == "read":
            mq = messageCenter.getUserQueue(user.username)
            count = request_dict["count"]
            mlist = []
            while (count == -1 or count > 0) and not mq.empty():
                msg = mq.getMessage()
                if msg is not None:
                    md = {"sender": msg.sender, "text": msg.text, "channel": msg.channel.channelname, "id": msg.sender_uid,
                          "type": msg.messageType, "timestamp": time.mktime(msg.timestamp.timetuple())}
                    mlist.append(md)
                    if count > 0:
                        count -= 1
                else:
                    break
            d["result"] = 1
            d["messages"] = mlist
        elif command == "write":
            text = request_dict["text"]
            channel = request_dict["channel"]
            res = messageCenter.postToChannel(user.screenname, user.id, channel, text)
            d["result"] = 1 if res else 0
        elif command == "chanusers":
            channel = request_dict["channel"]
            ch = messageCenter.getChannel(channel)
            ulist = []
            for uq in ch.users.values():
                ud = {"username": uq.screenname, "steam_id":uq.steamId, "channel": channel, "activity": (datetime.now() - uq.lastActivity),
                      "is_admin": uq.admin}
                ulist.append(ud)
            d["result"] = 1
            d["users"] = ulist

    except Exception as e:
        print "Exception while %s tried to %s message queue: %s" % (user.username, command, e.message)

    #print "Message queue command %s from %s; returns %s" % (command, user.username, str(d) )
    return json.dumps(d)


@app.route("/shop_list", method="POST")
@sessions.start
@metrics.collect
def shop_list(session, user, db):
    if user is None:
        return error_dict

    d = { "result":0 }
    # list all shop items; use currency as the currency for real-money items

    print "User %s requested shop item list" % (user.username,)
    try:
        request_dict = json.loads(request.forms["request_data"])
        currency = request_dict["currency"]
        items = db.query( ShopSKU ).all()
        item_list = []
        for i in items:
            i_dict = {}
            i_dict["sku"] = i.sku_internal_identifier
            i_dict["name"] = i.name
            i_dict["description"] = i.description
            i_dict["category"] = i.category
            i_dict["soft_cost"] = i.soft_currency_cost
            i_dict["hard_cost"] = i.hard_currency_cost
            i_dict["rm_currency"] = currency
            i_dict["rm_cost"] = price_for_sku_id( db, i.id, currency )
            item_list.append( i_dict )

        d["result"] = 1
        d["items"] = item_list

    except AssertionError as a:
        print "Assertion error in shop_list: " + str(a)
        _, _, tb = sys.exc_info()
        traceback.print_tb(tb) # Fixed format
    except Exception as e:
        print "Exception in shop_list: " + str(type(e)) + str(e) + " = " + e.message
        _, _, tb = sys.exc_info()
        traceback.print_tb(tb) # Fixed format

    return json.dumps(d)


@app.route("/shop_buy", method="POST")
@sessions.start
@metrics.collect
def shop_buy(session, user, db):
    if user is None:
        return error_dict

    d = {"result": 0}
    try:
        request_dict = json.loads(request.forms["request_data"])
        sku = request_dict["item_sku"]

        print "%s wants to buy SKU %s" % (user.username, sku)

        db_sku = db.query( ShopSKU ).filter( ShopSKU.sku_internal_identifier == sku ).first()
        # check money
        us = users.user_stats_for_user( db, user )
        canbuy = False
        hard_deduct = 0
        soft_deduct = 0
        if db_sku and (db_sku.soft_currency_cost != -1 or db_sku.hard_currency_cost != 1):  # no rmt purchases through this endpoint
            if db_sku.soft_currency_cost != -1:
                if db_sku.soft_currency_cost <= us.soft_money:
                    soft_deduct = db_sku.soft_currency_cost
                    canbuy = True
                else:
                    canbuy = False

            if db_sku.hard_currency_cost != -1:
                if db_sku.hard_currency_cost <= us.hard_money:
                    hard_deduct = db_sku.hard_currency_cost
                    canbuy = True
                else:
                    canbuy = False

        if canbuy:
            if hard_deduct != 0:
                users.user_deduct_hard_money( db, user, hard_deduct, "User purchase of shop item %s" % (db_sku.sku_internal_identifier,), "" )

            if soft_deduct != 0:
                users.user_deduct_soft_money( db, user, soft_deduct, "User purchase of shop item %s" % (db_sku.sku_internal_identifier,), "" )

            db.commit()

            sku_to_itemcount = {
                "TEST-001": 4,  "TEST-002": 4,   "TEST-003": 4,    "TEST-004": 4
            }

            # grant items
            items = []
            bought_items = []

            for i in range(0, sku_to_itemcount[db_sku.sku_internal_identifier]):
                bought_items.append( inventory.grant_random_item_to_user( db, user, "item", list( all_db_item_ids ), True ))

            for item in bought_items:
                items.append( full_information_dict_for_inventory_item_or_gem( "item", item ) )

            user.refreshFromDb( db )
            d["result"] = 1
            d["items"] = items
            d["hard_money"] = user.dbStats.hard_money
            d["soft_money"] = user.dbStats.soft_money
        else:
            d["result"] = 0
            d["reason"] = "nomoney"
            d["items"] = []
            d["hard_money"] = user.dbStats.hard_money
            d["soft_money"] = user.dbStats.soft_money

    except AssertionError as a:
        print "Assertion error in shop_buy: " + str(a)
        _, _, tb = sys.exc_info()
        traceback.print_tb(tb) # Fixed format
    except Exception as e:
        print "Exception in shop_buy: " + str(type(e)) + str(e) + " = " + e.message
        _, _, tb = sys.exc_info()
        traceback.print_tb(tb) # Fixed format

    return json.dumps(d)


@app.route("/shop_buy_OLD", method="POST")
@sessions.start
@metrics.collect
def shop_buy_old(session, user, db):
    if user is None:
        return error_dict

    d = {"result": 1}
    try:
        request_dict = json.loads(request.forms["request_data"])
        want_item_id = int(request_dict["item_id"])
        print "User %s to purchase item %d" % (user.username, want_item_id)
        stats = users.user_stats_for_user(db, user)
        want_item_dict = None
        for i in all_db_shop_items:
            if i["item_id"] == want_item_id:
                want_item_dict = i
                break

        if want_item_dict is None:
            d = {"result": 0, "message": "Invalid shop item identifier %d" % (want_item_id,)}
            return json.dumps(d)

        if stats.soft_money < want_item_dict["price"]:
            d = {"result": 0, "message": "Not enough money to buy this item!"}
            return json.dumps(d)

        # purchase ok, make it
        users.user_deduct_soft_money(db, user, want_item_dict["price"], "Soft money item purchase")
        # users.user_grant_shop_item( db, user, want_item_dict["item_id"], "Soft money item purchase" )

        # hardcoded :(
        if want_item_dict["item_id"] == 1:
            # bag of gems
            grantlist = []
            for x in xrange(0, 3):
                i_id = inventory.grant_random_item_to_user(db, user, "gem", list(all_db_gem_ids))
                i_entry = find_dict_with_id(all_db_gems, "gem_id", i_id)

                if i_id != -1:
                    print "Granted gem with id %d" % (i_id, )
                    grantlist.append(
                        {"itemid": i_id, "type": "gem", "tier": i_entry["tier"], "itemname": i_entry["name"],
                         "stack": 1, "increases": increases_dict_for_item_or_gem_new("gem", i_id)})
            d["gained_items"] = grantlist
            d["item_type"] = "gem"
        elif want_item_dict["item_id"] == 2:
            # stack of items
            grantlist = []
            for x in xrange(0, 3):
                i_id = inventory.grant_random_item_to_user(db, user, "item", list(all_db_item_ids))
                i_entry = find_dict_with_id(all_db_items, "item_id", i_id)
                if i_id != -1:
                    print "Granted item with id %d" % (i_id, )
                    grantlist.append(
                        {"itemid": i_id, "type": "gem", "tier": i_entry["tier"], "itemname": i_entry["name"],
                         "stack": 1, "increases": increases_dict_for_item_or_gem_new("item", i_id)})
            d["gained_items"] = grantlist
            d["item_type"] = "item"

    except Exception as e:
        print "Exception in buying: %s" % (repr(e),)
        return error_dict

    return json.dumps(d)


def increases_dict_for_item_or_gem(item_or_gem, item_id):
    db_list = all_db_items if item_or_gem == "item" else all_db_gems
    entry = db_list[item_id]
    incr_dict = {}
    for k in entry["increases"].keys():
        incr_dict[k] = entry["increases"][k]

    return incr_dict


def increases_dict_for_item_or_gem_new(item_or_gem, item_id):
    db_list = all_db_items if item_or_gem == "item" else all_db_gems
    entry = find_dict_with_id(db_list, item_or_gem + "_id", item_id)
    incr_dict = {}
    for k in entry["increases"].keys():
        incr_dict[k] = entry["increases"][k]
    return incr_dict


def dict_for_item_or_gem( item_or_gem, item_id ):
    assert( item_or_gem in ( "item", "gem" ) )

    db_list = all_db_items if item_or_gem == "item" else all_db_gems
    i = db_list[ item_id ]
    return dict( i.items() + increases_dict_for_item_or_gem_new( item_or_gem, item_id ).items() )


@app.route("/iteminfo", method="POST")
@sessions.start
@metrics.collect
def get_item_info(session, user, db):
    if user is None:
        return error_dict
    request_dict = json.loads(request.forms["request_data"])
    if not request_dict.has_key("type") or not request_dict.has_key("id") or not request_dict["type"] in (
        "item", "gem"):
        return error_dict

    d = error_dict
    try:
        i = int(request_dict["id"])
        req_type = request_dict["type"]

        db_list = all_db_items if req_type == "item" else all_db_gems

        if i < 0 or i >= len(db_list):
            d = {"result": 0}
        else:
            d = dict_for_item_or_gem( req_type, i )
            d["result"] = 1
    except:
        print "Exception in iteminfo; erroneous args?"
        return error_dict
    return json.dumps(d)


def find_dict_with_id(item_list, key_name, id):
    for i in item_list:
        if i.has_key(key_name) and i[key_name] == id:
            return i

def full_information_dict_for_inventory_item_or_gem( item_or_gem, i ):
    db_list = all_db_items if item_or_gem == "item" else all_db_gems
    item_data = find_dict_with_id(db_list, item_or_gem + "_id", i.item_id)
    cost = item_data["cost"] if item_data.has_key("cost") else 0
    desc = item_data["description"] if item_data.has_key("description") else ""
    suit = i.suit #item_data["suit"] if item_data.has_key("suit") else ""
    rarity = item_data["rarity"] if item_data.has_key("rarity") else 0
    illustration = item_data["illustration"] if item_data.has_key( "illustration" ) else "crest"
    proc_chance = item_data["proc_chance"] if item_data.has_key("proc_chance") else 0.0
    proc_multiplier = 0.0
    if suit == "Wood" or suit == "Water":
        proc_chance = 1.0
        proc_multiplier = ( 0.05 * float(item_data["tier"])) if suit == "Wood" else (0.10 * float(item_data["tier"]))

    return {"itemid": i.id, "type": item_or_gem, "itemname": item_data["name"],
                  "tier": item_data["tier"], "stack": 1, "sheet_id": -1, "description":desc, "suit":suit, "proc_chance":proc_chance,
                  "proc_multiplier":proc_multiplier,
                  "slot_id": i.slot, "increases": increases_dict_for_item_or_gem_new(item_or_gem, i.item_id),
                  "cost": cost, "illustration":illustration, "rarity":rarity,
                  "level_req_hero": item_data["level"], "level_req_player": 1, "type_id":i.item_id, "is_new":i.is_new }


def full_information_dict_for_item_or_gem_with_id( item_or_gem, i_id, i_suit ):
    db_list = all_db_items if item_or_gem == "item" else all_db_gems
    item_data = find_dict_with_id(db_list, item_or_gem + "_id", i_id )
    cost = item_data["cost"] if item_data.has_key("cost") else 0
    desc = item_data["description"] if item_data.has_key("description") else ""
    suit = i_suit

    rarity = item_data["rarity"] if item_data.has_key("rarity") else 0
    illustration = item_data["illustration"] if item_data.has_key( "illustration" ) else "crest"
    proc_chance = item_data["proc_chance"] if item_data.has_key("proc_chance") else 0.0
    proc_multiplier = 0.0
    if suit == "Wood" or suit == "Water":
        proc_chance = 1.0
        proc_multiplier = ( 0.05 * float(item_data["tier"])) if suit == "Wood" else (0.10 * float(item_data["tier"]))

    return {"itemid": i_id, "type": item_or_gem, "itemname": item_data["name"],
                  "tier": item_data["tier"], "stack": 1, "sheet_id": -1, "description":desc, "suit":suit, "proc_chance":proc_chance,
                  "proc_multiplier":proc_multiplier,
                  "slot_id": 1, "increases": increases_dict_for_item_or_gem_new(item_or_gem, i_id),
                  "cost": cost, "illustration":illustration, "rarity":rarity,
                  "level_req_hero": item_data["level"], "level_req_player": 1, "type_id":i_id, "is_new":False }


def user_items_with_procs( db, user ):
    d = {}
    d["item"] = []
    d["procs"] = []
    equip_i = inventory.get_user_equipped_items( db, user, "item" )
    for i in equip_i:
        d["item"].append( full_information_dict_for_inventory_item_or_gem( "item", i ) )

    procs = inventory.procs_from_current_inventory( db, user, all_db_items )
    l = []
    for p in procs.keys():
        for i in procs[p]:
            l.append( [p, i[0], i[1], i[2],i[3] ])
    d["procs"] = l
    return d

def tutorial_item_with_procs():
    d = {}
    d["item"] = []
    d["procs"] = []

    d["item"].append( full_information_dict_for_item_or_gem_with_id( "item", 30, "Fire" ) )
    d["procs"] = []

    return d





@app.route("/inventory", method="POST")
@sessions.start
@metrics.collect
def get_inventory(session, user, db):
    if user is None:
        return error_dict
    request_dict = json.loads(request.forms["request_data"])
    if not request_dict.has_key("type") or not request_dict["type"] in ("item", "gem"):
        return error_dict

    l = []
    names = []
    inv_items = inventory.get_user_items_of_category(db, user, request_dict["type"])
    for i in inv_items:
        l.append( full_information_dict_for_inventory_item_or_gem( request_dict["type"], i ))
        names.append( full_information_dict_for_inventory_item_or_gem( request_dict["type"], i)["itemname"] )

    d = {"items": l, "sheet_count": MAX_INVENTORY_SHEETS, "procs":inventory.procs_from_current_inventory( db, user, all_db_items )}
    return json.dumps(d)


@app.route("/inventory_seen", method="POST")
@sessions.start
@metrics.collect
def inventory_seen(session, user, db):
    if user is None:
        return error_dict

    d = {"result":0}
    try:
        request_dict = json.loads(request.forms["request_data"])
        inventory_id = request_dict["id"]

        item = inventory.get_user_item_with_inventory_id( db, user, inventory_id )
        if item is not None:
            item.is_new = False
            db.commit()
            print "Marked item %d SEEN by user %s" % (item.id, user.username)
            d["result"] = 1
    except AssertionError as a:
        print "Assertion error in inventory_seen: " + str(a)
        _, _, tb = sys.exc_info()
        traceback.print_tb(tb) # Fixed format
    except Exception as e:
        print "Exception in inventory_seen: " + str(type(e)) + str(e) + " = " + e.message
        _, _, tb = sys.exc_info()
        traceback.print_tb(tb) # Fixed format

    return json.dumps(d)


@app.route("/inventory_sell", method="POST")
@sessions.start
@metrics.collect
def inventory_sell(session, user, db):
    if user is None:
        return error_dict

    d = {"result":0}
    try:
        request_dict = json.loads(request.forms["request_data"])
        inventory_id = request_dict["id"]

        item = inventory.get_user_item_with_inventory_id( db, user, inventory_id )
        if item is not None:
            # TODO: grant something back to the user
            print "DELETE inventory item with id %d on user %s by request" % (item.id, user.username)
            db.delete( item )
            db.commit()
            d["result"] = 1
    except AssertionError as a:
        print "Assertion error in inventory_sell: " + str(a)
        _, _, tb = sys.exc_info()
        traceback.print_tb(tb) # Fixed format
    except Exception as e:
        print "Exception in inventory_sell: " + str(type(e)) + str(e) + " = " + e.message
        _, _, tb = sys.exc_info()
        traceback.print_tb(tb) # Fixed format


@app.route("/inventory_swap", method="POST")
@sessions.start
@metrics.collect
def inventory_swap(session, user, db):
    if user is None:
        return error_dict

    d = {"result": 0}
    request_dict = json.loads(request.forms["request_data"])
    if not request_dict.has_key("type") or not request_dict["type"] in ("item", "gem"):
        return error_dict

    try:
        sheet_id = request_dict[ "sheet_id" ]
        src_slot = request_dict[ "source_slot" ]
        tgt_slot = request_dict[ "target_slot" ]
        itemtype = request_dict["type"]

        print "%s wants to swap %s slots %d and %d" % (user.username, itemtype, src_slot, tgt_slot)

        assert( itemtype in ( "gem", "item" ) )

        src_item = inventory.get_user_item_in_slot(db, user, request_dict["type"], src_slot)
        tgt_item = inventory.get_user_item_in_slot(db, user, request_dict["type"], tgt_slot)

        if src_item != None and tgt_item == None:
            # obviously no item in this slot so just equip it
            inventory.equip_item_for_user( db, user, itemtype, src_item.id, tgt_slot )
            d["result"] = 1
            print "Users %s swaps %s in slot %d to empty slot %d" % (user.username, itemtype, src_slot, tgt_slot)

        if src_item != None and tgt_item != None and src_item.slot != tgt_item.slot:
            inventory.equip_item_for_user( db, user, itemtype, src_item.id, tgt_slot )
            inventory.equip_item_for_user( db, user, itemtype, tgt_item.id, src_slot )
            d["result"] = 1
            print "User %s swaps %s slots %d and %d" % (user.username, itemtype, src_slot, tgt_slot)
    except AssertionError as a:
        print "Assertion error in inventory_swap: " + str(a)
        _, _, tb = sys.exc_info()
        traceback.print_tb(tb) # Fixed format
    except Exception as e:
        print "Exception in inventory_swap: " + str(type(e)) + str(e) + " = " + e.message

    return json.dumps(d)


@app.route("/inventory_equip", method="POST")
@sessions.start
@metrics.collect
def inventory_equip(session, user, db):
    if user is None:
        return error_dict

    request_dict = json.loads(request.forms["request_data"])
    if not request_dict.has_key("type") or not request_dict["type"] in ("item", "gem"):
        return error_dict

    #print request_dict

    db_list = all_db_items if request_dict["type"] == "item" else all_db_gems

    equip_list = []
    if request_dict["type"] == "item":
        equip_list = [-1] * 4
    elif request_dict["type"] == "gem":
        equip_list = [-1] * 4

    item_id = request_dict["id"]
    slot_id = -1
    if request_dict.has_key("slot_id"):
        slot_id = request_dict["slot_id"]

    if slot_id == -1:
        inv = inventory.get_user_items_of_category(db, user, request_dict["type"])
        used_slots = []
        for inv_i in inv:
            if inv_i.slot != -1:
                used_slots.append(inv_i.slot)
        if len(used_slots) == 0:
            slot_id = 0
        else:
            for x in xrange(0, len(equip_list)):
                if x not in used_slots:
                    slot_id = x
                    break

    equipped = inventory.get_user_equipped_items(db, user, request_dict["type"])
    for i in equipped:
        if i.slot < len(equip_list):
            equip_list[i.slot] = i.id

    if item_id != -1 and not inventory.user_has_exact_item(db, user, request_dict["type"], item_id):
        print "%s tried to equip %d to slot %d but he does not have it!" % (user.username, item_id, slot_id)
        return json.dumps({"result": 0, "text": "You do not possess that %s you cheater!" % (request_dict["type"],)})

    if slot_id < -1 or slot_id > len(equip_list) - 1:
        print "%s tried to equip %d to slot %d but the slot is invalid" % (user.username, item_id, slot_id)
        return json.dumps({"result": 0, "text": "Invalid slot!"})

    if slot_id != -1 and item_id in equip_list and item_id != -1:
        print "%s tried to equip %d but it is already equipped in slot %d" % (user.username, item_id, equip_list.index( item_id ))
        return json.dumps( {"result":0, "text": "That item is already equipped. Unequip it first." } )

    if item_id != -1:
        olditem = inventory.get_user_item_in_slot(db, user, request_dict["type"], slot_id)
        if olditem is not None:
            print "Replacing old %s %d in slot %d with item %d" % (
                request_dict["type"], olditem.item_id, slot_id, item_id )
            olditem.slot = -1

        inventory.equip_item_for_user(db, user, request_dict["type"], item_id, slot_id)
    else:
        item = inventory.get_user_item_in_slot(db, user, request_dict["type"], slot_id)
        if item is not None:
            item.slot = -1

    db.commit()

    equipped = inventory.get_user_equipped_items(db, user, request_dict["type"])
    for i in equipped:
        equip_list[i.slot] = i.id

    print "%s equips item id %d into slot %d" % (user.username, item_id, slot_id)
    d = {"result": 1, "new_sheet": equip_list, "procs":inventory.procs_from_current_inventory( db, user, all_db_items )}

    #print "Created procs: %s" % (str( inventory.procs_from_current_inventory( db, user, all_db_items ) ))

    return json.dumps(d)


@app.route("/inventory_list_sheet", method="POST")
@sessions.start
@metrics.collect
def get_inventory_sheet(session, user, db):
    if user is None:
        return error_dict

    request_dict = json.loads(request.forms["request_data"])
    if not request_dict.has_key("type") or not request_dict["type"] in ("item", "gem"):
        return error_dict

    sheet_id = request_dict["sheet_id"]
    # support just a single sheet for now
    sheet_id = 0

    if not request_dict.has_key("sheet_id") or not request_dict.has_key("type") or not request_dict["type"] in ("item", "gem"):
        return error_dict

    equipped = inventory.get_user_equipped_items(db, user, request_dict["type"])
    l = []
    for i in equipped:
        tmp_d =  full_information_dict_for_inventory_item_or_gem( request_dict["type"], i).copy()
        tmp_d["sheet_id"] = sheet_id
        l.append( tmp_d )

    d = {"result": 1, "sheet_id": request_dict["sheet_id"], "type": request_dict["type"], "items": l}

    #print repr(d)
    return json.dumps(d)


@app.route('/debug_single_join', method="POST")
@sessions.start
def debug_single_join(session, user, db):
    if user is None:
        return error_dict

    d = {"result": 0}
    request_dict = json.loads(request.forms["request_data"])
    mapname = request_dict["mapname"]
    if user.account_type == 9:   # super-special debug account
        d = {}
        if user_equip_sheet_dict.has_key(user.username):
            eq_sheet = {user.username: inventory.equipsheet_with_names_for_user(db, user, all_db_items, all_db_gems)}
        match = create_match(db, 0, mapname, 1, 4, 2, eq_sheet, {user.username: user.id})
        d["result"] = 1
        d["server_host"] = BACKEND_SERVERS[0][0]
        d["server_port"] = BACKEND_SERVERS[0][1]
        d["server_match_token"] = match.token

        mr = MatchRequest(user.id)
        mr.map_preference = "Concept1custom"
        mr.skill_hint = 1500
        mr.status = 2
        mr.found_match_id = match.id

        result = MatchResult(user.id, match.token, 'in_progress')
        db.add(mr)
        db.add(result)
        db.commit()

    return json.dumps(d)


@app.route("/debug/<command>", method="GET")
def debug_command( command ):
    if not DEBUG_ENDPOINTS:
        return error_dict

    if command == "dumpmatches":
        print "Dumping matches..."
        d = {}
        for k, v in activeMatches.items():
            m = v
            d[k] = {}
            d[k]["type"] = m.matchType
            d[k]["state"] = m.state
            d[k]["playerCount"] = len( m.players )
            d[k]["players"] = []
            for name, p_inst in m.players.items():
                d[k]["players"].append( (p_inst.username, p_inst.selectedHero, p_inst.readyToPlay))

        return json.dumps( d, sort_keys=True, indent=4 )

    if command == "dumpplayers":
        print "Dumping players..."
        d = {}
        for uid, user in sessions.getUsersDictItems():
            if isinstance( user, UserState.UserState ):
                d[uid] = { "username": user.username, "screenname" : user.screenname }
                d[uid]["loggedIn"] = user.loggedIn
                d[uid]["inviteCount"] = user.inviteCount
                d[uid]["readyToPlay"] = user.readyToPlay
                d[uid]["status"] = user.status
                d[uid]["lastActivitySeconds"] = (datetime.now() - user.lastActivity).seconds
                d[uid]["match"] = None if user.match is None else user.match.token
        return json.dumps( d, sort_keys=True, indent=4 )

    return error_dict


@app.route( "/sys/<command>", method="GET" )
def syscommand( command ):
    retmsg = "No such command"
    auth = request.query.auth
    if auth == "420treehouse420":
        if command == "clearmsg":
            adminControl.setSysMessage( "" )
            retmsg = "Message cleared"
        elif command == "resetdt":
            adminControl.unsetDowntime()
            retmsg = "Downtime counter unset"
        elif command == "setmsg":
            try:
                msg = request.query.msg
                adminControl.setSysMessage( msg )
                retmsg = "New message set"
            except Exception as e:
                retmsg =  "Could not set message: " + e.message
        elif command == "setdt":
            try:
                offset = request.query.secs
                adminControl.setNextDowntimeByOffset( int( offset ) )
                retmsg = "New downtime offset set to " + str(adminControl.nextDowntime)
            except Exception as e:
                retmsg = "Could not set downtime: " + e.message
    else: retmsg = ""

    return retmsg


@app.route( "/update_metrics", method="GET" )
def update_metrics():
    usercount = 0
    for uid, user in sessions.getUsersDictItems():
        if isinstance( user, UserState.UserState ):
            if user.loggedIn:
                usercount += 1

    periodics = { "period_requests":"requests", "period_error_requests":"error_requests" }

    cwc = boto.connect_cloudwatch( AWS_ACCESS_KEY_ID, AWS_SECRET_ACCESS_KEY )
    cwc.put_metric_data( CW_METRIC_NAMESPACE, "active_users", usercount )
    # print "Updated CloudWatch metric usercount to %d" % (usercount, )
    for k, v in periodics.items():
        value = metrics.get(k)
        cwc.put_metric_data( CW_METRIC_NAMESPACE, v, value)
        metrics.reset( k )
        #print "Updated CloudWatch metric %s: %d" % (v, value)
    cwc.close()

    return json.dumps( {"result":1} )




if __name__ == "__main__":
    run(app=app, reloader=False, host=BIND_ADDRESS, port=BIND_PORT, server="gevent")
    #make_server( '', 7070, app).serve_forever()
