class User(object):
    def __init__(self, userid, username, password_hash="", screenname="", clantag = "" ):
        self.userid = userid
        self.username = username
        self.password_hash = password_hash
        self.screenname = screenname
        self.clantag = clantag
        self.logged_in = False


# some bullshit test data
_users = {
    "soiha":    User( 1, "soiha", "14758f1afd44c09b7992073ccf00b43d", "Soiha", "TH" ),
    "msaari":   User( 2, "msaari", "b27ad45069042e8aae100d45227d00ec", "Ilmivalta", "TH" ),
    "jmattila": User( 3, "jmattila", "8223395ba39ab4192b000aa708e27494", "flumba", "TH"),
    "vkirpu":   User( 4, "vkirpu", "906b01c63e8541b8cb3b90998adc80ab", "Vitali", "TH" ),
    "lauri":    User( 5, "lauri", "8a449c3fc8004bbf70dbe3d758b94acb", "Hevonen", "TH" ),
    "simo":     User( 6, "simo", "fb6cfa5ab5207ac2be7d7a3e8200954d", "Simo", "TH" ),
    "miika":    User( 7, "miika", "23f0d4882e90418309e876542d18d296", "Miika", "TH" )
}
