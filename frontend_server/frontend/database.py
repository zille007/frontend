from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy import Column, Sequence, Integer, Float, String, Boolean, ForeignKey, TIMESTAMP, Enum
import datetime
from os import urandom
from binascii import hexlify
from hashlib import sha1

Base = declarative_base()

class GameServer(Base):
    __tablename__ = 'servers'

    id = Column( Integer, Sequence( "gameserver_id_seq" ), primary_key=True, autoincrement=True )
    host = Column( String(64) )
    port = Column( String(10) )
    fe_username = Column( String(64) )
    fe_password = Column( String(64) )

    def __init__(self, host, port, username, password ):
        self.host = host
        self.port = port
        self.fe_username = username
        self.fe_password = password

    def __repr__(self):
        return "<GameServer %s:%s>" % (self.host, self.port)


class UserSession(Base):
    __tablename__ = 'sessions'

    session_id = Column( String(64), primary_key=True, autoincrement=True )
    user_id = Column( Integer )
    created = Column( TIMESTAMP( timezone=True ) )

    def __init__(self, user_id, session_id, created = None ):
        self.session_id = session_id
        self.user_id = user_id
        self.created = created
        if created is None:
            self.created = datetime.datetime.now()

    def __repr__(self):
        return "<Session for user id %d created on %s>" % (self.user_id, str(self.created) )


class User(Base):
    """
    ALTER TABLE users ADD COLUMN steam_id varchar(32);
    """
    __tablename__ = 'users'

    id = Column( Integer, primary_key=True, autoincrement=True )
    username = Column( String(64) )
    screenname = Column( String(64) )
    password_hash = Column( String )
    clantag = Column( String(10) )
    allow_login = Column( Boolean )
    account_type = Column( Integer )
    rating = Column( Integer )    # this lives here for now until we move it to a proper player statistics table
    email = Column( String(128) )
    is_online = Column( Boolean )
    steam_id = Column( String(32) )

    def __init__( self, username ):
        self.username = username
        self.is_online = False

    def __repr__(self):
        return "<User %s/%s>" % (self.username, self.screenname)


class UserInventoryItem(Base):
    """
    CHANGED 140207: ALTER TABLE user_inventory ADD COLUMN suit varchar(10) NOT NULL;
    CHANGED 140207: ALTER TABLE user_inventory ADD COLUMN is_new boolean NOT NULL default TRUE;
    """
    __tablename__ = "user_inventory"

    id = Column( Integer, primary_key=True, autoincrement=True )
    user_id = Column( Integer, primary_key=True )
    item_category = Column( String(16), primary_key=True )
    item_id = Column( Integer )
    slot = Column( Integer )
    item_name = Column( String(64) )
    suit = Column( String(10), nullable=False )
    is_new = Column( Boolean, nullable=False )

    def __init__( self, user_id, item_category, item_id, suit, item_name = "", slot=-1 ):
        self.user_id = user_id
        self.item_category = item_category
        self.item_id = item_id
        self.item_name = ""
        self.slot = slot
        self.suit = suit
        self.is_new = True


class UserPossession(Base):
    """
CREATE SEQUENCE user_possessions_seq;

CREATE TABLE user_possessions(
    id integer not null unique default nextval('user_possessions_seq'::regclass),
    user_id integer not null,
    p_type varchar(16) not null,
    p_item varchar(32) not null,

    grant_information varchar(32),

    primary key( id, user_id ),
    foreign key( user_id ) references users(id)
);
    """
    __tablename__ = "user_possessions"

    id = Column( Integer, primary_key=True, autoincrement=True )
    user_id = Column( Integer, primary_key=True )
    p_type = Column( String(16), nullable=False, primary_key=True )
    p_item = Column( String(32) )
    grant_information = Column( String(32) )

    def __init__(self, user_id, p_type, p_item, grant_info = ""  ):
        self.user_id = user_id
        self.p_type = p_type
        self.p_item = p_item
        self.grant_information = grant_info

class UserBooster(Base):
    """
CREATE SEQUENCE user_boosters_seq;

CREATE TABLE user_boosters(
    id integer not null unique default nextval('user_boosters_seq'::regclass),
    user_id integer not null,

    booster_type varchar(16) not null,
    multiplier float not null,

    grant_timestamp timestamp with time zone,
    expiry_timestamp timestamp with time zone,

    grant_information varchar(64),

    primary key( id, user_id, booster_type ),
    foreign key( user_id ) references users(id)


);
"""
    __tablename__ = "user_boosters"

    id = Column( Integer, primary_key=True, autoincrement=True )
    user_id = Column( Integer, primary_key=True )

    booster_type = Column( String(16), nullable=False, primary_key=True )
    multiplier = Column( Float, nullable=False )

    grant_timestamp = Column( TIMESTAMP( timezone=True ) )
    expiry_timestamp = Column( TIMESTAMP( timezone=True ) )

    grant_information = Column( String(64) )

    def __init__(self, user_id, booster_type, booster_multiplier, expiry_timestamp, grant_info = "" ):
        self.user_id = user_id
        self.booster_type = booster_type
        self.multiplier = booster_multiplier

        self.grant_timestamp = datetime.datetime.now()
        self.expiry_timestamp = expiry_timestamp
        self.grant_information = grant_info
        pass


class UserStats(Base):
    """
    CHANGED 140129: ALTER TABLE user_stats ADD COLUMN ladder_value float NOT NULL default 13.0;
    CHANGED 140213: UPDATE user_stats SET xp_level=1, xp_current=0, xp_next=212, hard_money=0, soft_money=0, rating=1500; /* reset */
    """
    __tablename__ = "user_stats"

    id = Column( Integer, primary_key=True, autoincrement=True )
    user_id = Column( Integer )

    xp_level = Column( Integer )
    xp_current = Column( Integer )
    xp_next = Column( Integer )
    xp_rested = Column( Integer )
    rating = Column( Integer )
    ladder_value = Column( Float )

    soft_money = Column( Integer )
    hard_money = Column( Integer )

    def __init__(self, userid):
        self.user_id = userid
        self.xp_level = 1
        self.xp_current = 0
        self.xp_next = 212
        self.xp_rested = 0
        self.rating = 1500
        self.hard_money = 0
        self.soft_money = 1500
        self.ladder_value = 13.0


class UserStatEvent(Base):
    """
    CHANGED 140129: ALTER TABLE user_stat_events ADD COLUMN old_value integer NOT NULL DEFAULT -1;
    """

    __tablename__ = "user_stat_events"

    id = Column( Integer, primary_key=True, autoincrement=True )
    user_id = Column( Integer, primary_key=True )

    created = Column( TIMESTAMP( timezone=True ) )

    field_name = Column( String(32), nullable=False )
    old_value = Column( Integer, nullable=False, default=-1)
    change_type = Column( String(32), nullable=False )
    change_amount = Column( Integer, nullable=False )

    match_token = Column( String(64) )
    inapp_transaction_id = Column( String(128) )

    description = Column( String )

    def __repr__(self):
        return "<UserStatEvent for user id %d: %s %s %d>" % (self.user_id, self.field_name, self.change_type, self.change_amount)

    def __init__(self, user_id, field_name, change_type, amount, old_value = -1 ):
        self.user_id = user_id
        self.created = datetime.datetime.now()
        self.field_name = field_name
        self.change_type = change_type
        self.change_amount = amount
        self.old_value = old_value


#class FriendRequest(Base):
#    def __init__(self):
#        pass


#class FriendAssociation(Base):
#    def __init__(self):
#       pass


class Match(Base):
    __tablename__ = 'match'

    id = Column( Integer, Sequence( "match_id_seq" ), primary_key=True, autoincrement=True )
    token = Column( String(64) )
    map = Column( String(64) )
    server_id = Column( Integer )
    status = Column( Integer )
    result = Column( Integer )
    creation_time = Column( TIMESTAMP( timezone = True ) )
    match_type = Column( Integer )
    start_time = Column( TIMESTAMP( timezone = True ) )
    end_time = Column( TIMESTAMP( timezone = True ) )

    def __init__(self, map, match_type ):
        mid = urandom(32)
        mid_str = ":".join("{0:x}".format(ord(c)) for c in mid)
        self.token = sha1(u'%s%s' % (mid_str, map)).hexdigest()
        self.map = map
        self.server_id = 0
        self.status = 0
        self.result = 0
        self.creation_time = datetime.datetime.now()
        self.match_type = 1
        self.start_time = datetime.datetime( 1970, 1, 1 )
        self.end_time = datetime.datetime( 1970, 1, 1 )

    def __repr__(self):
        return "<Match %s in state %d>" % (self.token, self.status)

class MatchBasicInfo(Base):
    """
CREATE SEQUENCE match_basic_infos_seq;

CREATE TABLE match_basic_infos(
    id integer not null unique default nextval('match_basic_infos_seq'::regclass),
    match_id integer not null,
    type_string varchar(16) not null,
    tickets integer not null,
    duration integer not null,
    winning_team integer,
    tickets_team1 integer,
    tickets_team2 integer,

    primary key (id),
    foreign key (match_id) references match(id) on delete restrict
);
    """
    id = Column( Integer, primary_key=True, autoincrement=True )
    match_id = Column( Integer, ForeignKey( "match.id" ), nullable=False, primary_key=True )
    type_string = Column( String(16), nullable=False )
    tickets = Column( Integer, nullable=False )
    duration = Column( Integer, nullable=False )
    winning_team = Column( Integer )
    tickets_team1 = Column( Integer )
    tickets_team2 = Column( Integer )

    __tablename__ = 'match_basic_infos'
    def __init__(self, match_id, type_string, tickets, duration ):
        self.match_id = match_id
        self.type_string = type_string
        self.tickets = tickets
        self.tickets_team1 = tickets
        self.tickets_team2 = tickets
        self.duration = duration
        self.winning_team = -1

class MatchPlayerInfo(Base):
    """
CREATE SEQUENCE match_player_infos_seq;

CREATE TABLE match_player_infos(
    id integer not null unique default nextval('match_player_infos_seq'::regclass),
    match_id integer not null,
    player_id integer,
    player_match_index integer,
    player_name varchar(64) not null,
    rank float,
    human boolean,
    team integer,
    hero integer,
    role varchar(16),
    level integer,
    total_experience integer,
    kills integer,
    creep_kills integer,
    deaths integer,
    captures integer,
    gold_collected integer,
    total_damage_out integer,
    total_damage_in integer,
    potions_collected integer,

    primary key (match_id, id),
    foreign key(match_id) references match(id) on delete restrict
);
    """
    id = Column( Integer, primary_key=True, autoincrement=True )
    match_id = Column( Integer, ForeignKey( "match.id" ), nullable=False, primary_key=True )
    player_id = Column( Integer )
    player_match_index = Column( Integer )
    player_name = Column( String(64), nullable=False )
    rank = Column( Float )
    human = Column( Boolean )
    team = Column( Integer )
    hero = Column( Integer )
    role = Column( String(16) )
    level = Column( Integer )
    total_experience = Column( Integer )
    kills = Column( Integer )
    creep_kills = Column( Integer )
    deaths = Column( Integer )
    captures = Column( Integer )
    gold_collected = Column( Integer )
    total_damage_out = Column( Integer )
    total_damage_in = Column( Integer )
    potions_collected = Column( Integer )

    __tablename__ = 'match_player_infos'
    def __init__(self, match_id, player_id, player_name, team, rank):
        self.match_id = match_id
        self.player_id = player_id
        self.player_name = player_name
        self.team = team
        self.rank = rank
        self.level = 1
        self.total_experience = 0
        self.kills = 0
        self.creep_kills = 0
        self.deaths = 0
        self.captures = 0
        self.gold_collected = 0
        self.total_damage_out = 0
        self.total_damage_in = 0
        self.potions_collected = 0


class MatchTeamEvent(Base):
    """
CREATE SEQUENCE match_team_events_seq;

CREATE TABLE match_team_events(
    id integer not null unique default nextval('match_team_events_seq'::regclass),
    match_id integer not null,
    time integer not null,
    team integer not null,
    event varchar(32) not null,
    position_x float,
    position_y float,
    position_z float,
    extra_data_1 varchar(64),
    extra_data_2 varchar(64),

    primary key( match_id, id ),
    foreign key(match_id) references match(id) on delete restrict

);
    """
    id = Column( Integer, primary_key=True, autoincrement=True )
    match_id = Column( Integer, ForeignKey( "match.id" ), primary_key=True )
    time = Column( Integer )
    team = Column( Integer )
    event = Column( String(32) )
    position_x = Column( Float )
    position_y = Column( Float )
    position_z = Column( Float )
    extra_data_1 = Column( String(64) )
    extra_data_2 = Column( String(64) )

    __tablename__ = 'match_team_events'
    def __init__(self, match_id, time, team, event, extra_data_1 = None, extra_data_2 = None, position = None):
        self.match_id = match_id
        self.time = time
        self.team = team
        self.event = event
        if extra_data_1 is not None:
            self.extra_data_1 = extra_data_1
        if extra_data_2 is not None:
            self.extra_data_2 = extra_data_2
        if self.position is not None:
            self.position_x, self.position_y, self.position_z = position


class MatchPlayerEvent(Base):
    """
CREATE SEQUENCE match_player_events_seq;

CREATE TABLE match_player_events(
    id integer not null unique default nextval('match_player_events_seq'::regclass),
    match_id integer not null,
    time integer not null,
    player_name varchar(64) not null,
    event varchar(32) not null,
    position_x float,
    position_y float,
    position_z float,
    extra_data_1 varchar(64),
    extra_data_2 varchar(64),

    primary key (match_id, id),
    foreign key (match_id) references match(id) on delete restrict
);
    """
    id = Column( Integer, primary_key=True, autoincrement=True )
    match_id = Column( Integer, ForeignKey( "match.id" ), primary_key=True )
    time = Column( Integer )
    player_name = Column( String(64) )
    event = Column( String(32) )
    position_x = Column( Float )
    position_y = Column( Float )
    position_z = Column( Float )
    extra_data_1 = Column( String(64) )
    extra_data_2 = Column( String(64) )

    __tablename__ = 'match_player_events'
    def __init__(self, match_id, time, player_name, event, extra_data_1 = None, extra_data_2 = None, position = None ):
        self.match_id = match_id
        self.time = time
        self.player_name = player_name
        self.event = event
        if extra_data_1 is not None:
            self.extra_data_1 = extra_data_1
        if extra_data_2 is not None:
            self.extra_data_2 = extra_data_2
        if self.position is not None:
            self.position_x, self.position_y, self.position_z = position


class MatchRequest(Base):
    __tablename__ = 'match_request'

    id = Column( Integer, primary_key=True, autoincrement=True )
    user_id = Column( Integer )
    gametype = Column( String(10), nullable=True )  # Column( Enum( '1v1', '2v2', name="matchrequest_gametype_enum" ) )
    controltype = Column(String(10), nullable=True ) # Column( Enum('master', 'hero'), name="matchrequest_controltype_enum" )
    map_preference = Column( String(64) )
    found_match_id = Column( Integer )
    status = Column( Integer )
    skill_hint = Column( Integer )
    start_time = Column( TIMESTAMP( timezone = True ) )

    def __init__(self, user_id ):
        self.user_id = user_id
        self.status = 0
        self.skill_hint = 0
        self.start_time = datetime.datetime.now()

    def __repr__(self):
        return "<Match request for user %d>" % (self.user_id,)


class MatchResult(Base):
    """
    CHANGED 140129: ALTER TABLE match_result ADD COLUMN old_ladder float;
                    ALTER TABLE match_result ADD COLUMN new_ladder float;
                    ALTER TABLE match_result ADD COLUMN old_soft_money integer;
                    ALTER TABLE match_result ADD COLUMN new_soft_money integer;
                    ALTER TABLE match_result ADD COLUMN old_hard_money integer;
                    ALTER TABLE match_result ADD COLUMN new_hard_money integer;

    """

    __tablename__ = 'match_result'

    id = Column( Integer, primary_key = True, autoincrement=True )
    user_id = Column( Integer, primary_key=True, nullable=False )
    match_token = Column( String(64), nullable=False )
    result = Column( String(20), nullable=True ) # Column( Enum( 'won', 'lost', 'draw', 'in_progress', 'unfinished', name="matchresult_result_enum" ), nullable=False )

    old_xp = Column( Integer )
    new_xp = Column( Integer )
    old_level = Column( Integer )
    new_level = Column( Integer )
    old_rating = Column( Integer )
    new_rating = Column( Integer )
    old_ladder = Column( Float )
    new_ladder = Column( Float )
    old_soft_money = Column( Integer )
    new_soft_money = Column( Integer )
    old_hard_money = Column( Integer )
    new_hard_money = Column( Integer )

    end_time = Column( TIMESTAMP( timezone = True ) )

    def __repr__(self):
        return "<MatchResult on match %s for userid %d: %s>" % (self.match_token, self.user_id, self.result)

    def __init__(self, user_id, match_token, result ):
        self.user_id = user_id
        self.match_token = match_token
        self.result = result


class BetaFeedback(Base):
    __tablename__ = 'beta_feedback'

    match_id = Column( String(64), primary_key = True, nullable=False )
    user_id = Column( Integer, primary_key=True, nullable=False )
    rating = Column( Integer, default=0, nullable=False )
    feedback = Column( String(1024), default='', nullable=False )

    def __repr__(self):
        return "<Match feedback for match %s>" % (self.match_id,)

    def __init__(self, match_id, user_id ):
        self.match_id = match_id
        self.user_id = user_id
        self.rating = 0
        self.feedback = ''


class BetaInvite(Base):
    __tablename__ = 'beta_invites'

    beta_key = Column( String(64), primary_key=True, nullable=False )
    email_address = Column( String(128), nullable=False )
    requested_username = Column( String(64), nullable=False )
    consumed = Column( Boolean, default=False)
    email_confirmed = Column( Boolean, default=False )
    created_timestamp = Column( TIMESTAMP( timezone=True ) )
    consumed_timestamp = Column( TIMESTAMP( timezone = True ) )
    email_sent = Column( Boolean, default=False )
    email_confirm_key = Column( String(64), nullable=True )
    requested_password = Column( String(64), nullable=False, default='' )

    def __init__(self, beta_key):
        self.beta_key = beta_key
        self.email_address = ''
        self.requested_username = ''
        self.consumed = False
        self.email_confirmed = False
        self.created_timestamp = datetime.datetime.now()
        self.email_sent = False
        self.requested_password = ''



class FriendAssociation(Base):
    __tablename__ = "user_friend_assoc"

    id = Column( Integer, autoincrement=True, primary_key=True )
    user_id = Column( Integer, primary_key=True )
    friend_id = Column( Integer )

    def __init__(self, user_id, friend_id):
        self.user_id = user_id
        self.friend_id = friend_id

class FriendRequest(Base):
    __tablename__ = "friend_requests"

    id = Column( Integer, autoincrement=True, primary_key=True )
    receiver_user_id = Column( Integer, primary_key=True )
    sender_user_id = Column( Integer, primary_key=True )
    accepted = Column( Boolean, default=False )

    def __init__(self, user_id, friend_id):
        self.receiver_user_id = friend_id
        self.sender_user_id = user_id
        self.accepted = False


class GameInvite(Base):
    __tablename__ = "friend_game_invites"

    id = Column( Integer, autoincrement=True, primary_key=True )
    receiver_user_id = Column( Integer, primary_key=True )
    sender_user_id = Column( Integer )
    map_preference = Column( String(64) )
    accepted = Column( Boolean, default=False )
    game_created = Column( Boolean, default=False )
    match_token = Column( String(64) )

    def __init__(self, receiver_id, sender_id ):
        self.receiver_user_id = receiver_id
        self.sender_user_id = sender_id
        self.map_preference = ''
        self.accepted = False
        self.game_created = False
        self.match_token = ''


class Achievement(Base):
    """
CREATE SEQUENCE achievements_id_seq;

CREATE TABLE achievements(
    id integer not null unique default nextval('achievements_id_seq'::regclass),
    user_id integer not null,
    achievement_name varchar(32),
    completed timestamp with time zone,
    completion_count integer default 0,
    last_complete_token varchar(64),

    primary key ( id, user_id ),
    foreign key ( user_id ) references users(id) on delete cascade
);
    """
    __tablename__ = "achievements"

    id = Column( Integer, autoincrement=True, primary_key=True )
    user_id = Column( Integer, primary_key=True )
    achievement_name = Column( String(32) )
    completed = Column( TIMESTAMP( timezone=True ) )
    completion_count = Column( Integer, default=0 )
    last_complete_token = Column( String(64) )

    def __init__(self, user_id, achievement, token=""):
        self.user_id = user_id
        self.achievement_name = achievement
        self.completed = datetime.datetime.utcnow()
        self.completion_count = 0
        self.last_complete_token = token


class LogEntry(Base):
    """
CREATE SEQUENCE logentries_id_seq;

CREATE TABLE logentries(

    id integer not null unique default nextval('logentries_id_seq'::regclass),
    user_id integer not null,

    entry_timestamp timestamp with time zone,
    entry_type varchar(32),
    extra_data varchar(256),

    primary key (id, user_id),
    foreign key ( user_id ) references users(id) on delete cascade

);
    """
    __tablename__ = "logentries"

    id = Column( Integer, autoincrement=True, primary_key=True )
    user_id = Column( Integer, ForeignKey( "users.id" ), primary_key=True, nullable=False  )
    entry_timestamp = Column( TIMESTAMP( timezone=True ) )
    entry_type = Column( String(32) )
    extra_data = Column( String(256) )

    def __init__(self, user_id, entry_type, extra_data="" ):
        self.user_id = user_id
        self.entry_timestamp = datetime.datetime.now()
        self.entry_type = entry_type
        self.extra_data = extra_data


class ShopSKU(Base):
    """
CREATE SEQUENCE shop_item_skus_id_seq START WITH 1000;

CREATE TABLE shop_item_skus(
    id integer not null unique default nextval('shop_item_skus_id_seq'::regclass),

    sku_internal_identifier varchar(32) not null unique,
    name varchar(128) not null,
    description varchar(256) not null,
    category varchar(32),

    purchaseable boolean not null,

    soft_currency_cost integer,
    hard_currency_cost integer,

    steam_sellable boolean,

    primary key(id)
);

INSERT INTO shop_item_skus
  (id, sku_internal_identifier, name, description, category, purchaseable, soft_currency_cost, hard_currency_cost, steam_sellable)
VALUES
  (2001, 'CHARACTER-BEAVER', 'Beaver', 'Beaver hero character', 'character', TRUE, -1, -1, TRUE );

INSERT INTO shop_item_skus
  (id, sku_internal_identifier, name, description, category, purchaseable, soft_currency_cost, hard_currency_cost, steam_sellable)
VALUES
  (2002, 'CHARACTER-FYRE', 'Fyre Engineer', 'Fyre Engineer hero character', 'character', TRUE, -1, -1, TRUE );

INSERT INTO shop_item_skus
  (id, sku_internal_identifier, name, description, category, purchaseable, soft_currency_cost, hard_currency_cost, steam_sellable)
VALUES
  (2003, 'CHARACTER-ALCHEMIST', 'Alchemist', 'Alchemist hero character', 'character', TRUE, -1, -1, TRUE );

INSERT INTO shop_item_skus
  (id, sku_internal_identifier, name, description, category, purchaseable, soft_currency_cost, hard_currency_cost, steam_sellable)
VALUES
  (2004, 'CHARACTER-STONE', 'Stone elemental', 'Stone elemental hero character', 'character', TRUE, -1, -1, TRUE );

INSERT INTO shop_item_skus
  (id, sku_internal_identifier, name, description, category, purchaseable, soft_currency_cost, hard_currency_cost, steam_sellable)
VALUES
  (2005, 'CHARACTER-ROGUE', 'Rogue', 'Rogue hero character', 'character', TRUE, -1, -1, TRUE );


INSERT INTO shop_sku_prices (sku_id, currency, unit_price) VALUES ( 2001, 'EUR', 100 );
INSERT INTO shop_sku_prices (sku_id, currency, unit_price) VALUES ( 2002, 'EUR', 100 );
INSERT INTO shop_sku_prices (sku_id, currency, unit_price) VALUES ( 2003, 'EUR', 100 );
INSERT INTO shop_sku_prices (sku_id, currency, unit_price) VALUES ( 2004, 'EUR', 100 );
INSERT INTO shop_sku_prices (sku_id, currency, unit_price) VALUES ( 2005, 'EUR', 100 );
    """
    __tablename__ = "shop_item_skus"

    id = Column( Integer, autoincrement=True, primary_key=True )
    sku_internal_identifier = Column( String(32), nullable=False, primary_key=True )
    name = Column( String(128), nullable=False )
    description = Column( String(256), nullable=False )
    category = Column( String(32) )

    purchaseable = Column( Boolean, nullable=False, default=False )

    soft_currency_cost = Column( Integer )
    hard_currency_cost = Column( Integer )

    steam_sellable = Column( Boolean, default=False )

    def __init__(self, sku_internal_identifier, name, description, purchaseable = False):
        self.sku_internal_identifier = sku_internal_identifier
        self.name = name
        self.description = description
        self.purchaseable = purchaseable


class ShopSKUPrice(Base):
    """
CREATE SEQUENCE shop_sku_prices_id_seq;

CREATE TABLE shop_sku_prices(
    id integer not null unique default nextval('shop_sku_prices_id_seq'::regclass),

    sku_id integer not null,
    currency varchar(5) not null,
    unit_price integer,

    primary key (id, sku_id),
    foreign key (sku_id) references shop_item_skus(id) on delete cascade
);
    """

    __tablename__ = "shop_sku_prices"
    id = Column( Integer, autoincrement=True, primary_key=True )
    sku_id = Column( Integer, ForeignKey("shop_item_skus.id"), nullable=False, primary_key=True )
    currency = Column( String(5), nullable=False )
    unit_price = Column( Integer, nullable=False )

    def __init__(self, sku_id, currency, unit_price):
        self.sku_id = sku_id
        self.currency = currency
        self.unit_price = unit_price


class ShopTransaction(Base):
    """
CREATE SEQUENCE shoptransactions_id_seq START WITH 100000;

CREATE TABLE shoptransactions(
    id integer not null unique default nextval('shoptransactions_id_seq'::regclass),
    user_id integer not null,

    merchant_txn_id varchar(64), /* the remote merchant's transaction id */

    purchase_method varchar(16) not null,  /* "ingame", "steam", "apple", "google", but currently always "steam" */
    tx_state varchar(32) not null, /* "open", "wait_payment", "confirmed", "failed", "rejected" */
    items_delivered boolean not null,

    total_price integer not null, /* in 1/100th of the currency unit */
    currency varchar(5) not null,

    start_timestamp timestamp with time zone,
    confirm_timestamp timestamp with time zone,
    delivered_timestamp timestamp with time zone,

    primary key (id, user_id),
    foreign key ( user_id ) references users(id) on delete restrict
);
    """
    __tablename__ = "shoptransactions"
    id = Column( Integer, autoincrement=True, primary_key=True )
    user_id = Column( Integer, ForeignKey( "users.id" ), nullable=False, primary_key=True )
    merchant_txn_id = Column( String(64) )

    purchase_method = Column( String(16), nullable=False )
    tx_state = Column( String(32), nullable=False )
    items_delivered = Column( Boolean, nullable=False, default=False )

    total_price = Column( Integer, nullable=False )
    currency = Column( String(5), nullable=False )

    start_timestamp = Column( TIMESTAMP(timezone=True) )
    confirm_timestamp = Column( TIMESTAMP(timezone=True) )
    delivered_timestamp = Column( TIMESTAMP(timezone=True) )

    def __init__(self, user_id, purchase_method, price, currency ):
        self.user_id = user_id
        self.purchase_method = purchase_method
        self.total_price = price
        self.currency = currency

        self.tx_state = "open"
        self.items_delivered = False

        self.start_timestamp = datetime.datetime.now()


class ShopTransactionItem(Base):
    """
CREATE SEQUENCE shoptransaction_items_id_seq;

CREATE TABLE shoptransaction_items(
    id integer not null unique default nextval('shoptransaction_items_id_seq'::regclass),
    tx_id integer not null,

    item_sku_id integer not null,
    quantity integer not null,
    unit_price integer not null,
    total_price integer not null,

    currency varchar(5) not null,

    primary key (id, tx_id),
    foreign key (tx_id) references shoptransactions(id) on delete cascade,
    foreign key (item_sku_id) references shop_item_skus(id) on delete restrict
);
    """

    __tablename__ = "shoptransaction_items"

    id = Column( Integer, autoincrement=True, primary_key=True )
    tx_id = Column( Integer, ForeignKey( "shoptransactions.id"), nullable=False, primary_key=True )

    item_sku_id = Column( Integer, ForeignKey( "shop_item_skus.id" ), nullable=False )
    quantity = Column( Integer, nullable=False )
    unit_price = Column( Integer, nullable=False )
    total_price = Column( Integer, nullable=False )

    currency = Column( String(5), nullable=False )

    def __init__(self, tx_id, item_id, quantity, currency, unit_price):
        self.tx_id = tx_id
        self.item_sku_id = item_id
        self.quantity = quantity
        self.currency = currency
        self.unit_price = unit_price
        self.total_price = quantity * unit_price
