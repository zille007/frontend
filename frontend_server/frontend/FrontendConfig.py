BIND_PORT = 7071
BIND_ADDRESS = "0.0.0.0"

MONGODB_HOST = "10.0.0.1"
MONGODB_PORT = 27017

DB_USERNAME = "tdta"
DB_PASSWORD = "foobar42"
DB_HOST = "10.0.0.1"
DB_DATABASE = "tdta"

NEW_USER_RATING = 1500

BACKEND_SERVERS = (
( "127.0.0.1", 32073, "th_frontend", "e5e6af02519f110093d76dcc1f55b25d" ),
( "127.0.0.1", 32073, "th_frontend", "e5e6af02519f110093d76dcc1f55b25d" ),
( "127.0.0.1", 32073, "th_frontend", "e5e6af02519f110093d76dcc1f55b25d" ),
)

BACKEND_SERVER_CONFIG = {
    "europe":(
        ( "127.0.0.1", 32073, "th_frontend", "e5e6af02519f110093d76dcc1f55b25d", "euro1" ),
        ( "127.0.0.1", 32073, "th_frontend", "e5e6af02519f110093d76dcc1f55b25d", "euro2" )
    ),

    "us-east":(
        ( "127.0.0.1", 32073, "th_frontend", "e5e6af02519f110093d76dcc1f55b25d", "useast1" ),
        ( "127.0.0.1", 32073, "th_frontend", "e5e6af02519f110093d76dcc1f55b25d", "useast2" )
    )

}

# 2vs2
MATCHMAKING_GAME_SIZE = 4

ALLOWED_HEROES = ( "Bear", "Sniper", "Beaver", "Fyrestein", "Stone elemental", "Rogue", "Celestial bear", "Alchemist"  )
ALLOWED_MAPS = ( "Snowy Mountain Pass", "Haunted Mines", "(WIP) Single Lane Map" )
RANDOM_MAP_LAST_INDEX = 1

DEBUG_ENDPOINTS = True

SMTP_SERVER = "localhost"
SMTP_PORT = 26
SMTP_USERNAME = "AKIAJ2JHWVZ2PCGQ2GPQ"
SMTP_PASSWORD = "AgoWJv+hX4BzzM2lCF6y9coW2hB7XvVww5gC7vVmVheHth-"
FRONTEND_SERVER_HOSTNAME = "54.246.250.211:7070"

ALLOW_CLIENT_VERSIONS = ( "1.0.8", "0.3.0.4" )

MOTD_FILE_PATH = "./motds"
MOTD_FILE = "motd.txt"

PIDFILE = "/tmp/dethroned-frontend.pid"

CLIENT_PING_DELAY = 5.0
CLIENT_MESSAGE_DELAY = 10.5
CLIENT_FRIEND_STATUS_DELAY = 9.0

STEAM_APP_ID = "269390"
STEAM_WEBAPI_KEY = "3855F8A249D3D8E7B03265D77716F2F2"
STEAM_WEBAPI_MICROTXN_URL = "https://api.steampowered.com/ISteamMicroTxnSandbox"

AWS_ACCESS_KEY_ID = "AKIAI4JLYYWPZVCFI2AA"
AWS_SECRET_ACCESS_KEY = "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"
CW_METRIC_NAMESPACE = "dethroned.frontend"
