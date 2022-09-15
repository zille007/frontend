from webtest import TestApp
import frontend
import json


def test_functional_matchmake_1v1():
    pass

def test_functional_match_results():
    pass

def test_functional_inventory():
    pass

def test_functional_shop_list():
    app = TestApp( frontend.app )

    d = { 'username':'soiha', 'password':'foobar' }
    app.post( "/login", { "request_data":json.dumps(d) } )

    assert app.post( "/shop_list", {} ).status == "200 OK"

    app.post( "/logout", {} )
    app.reset()

def test_functional_shop_buy():
    app = TestApp( frontend.app )

    d = { 'username':'soiha', 'password':'foobar' }
    app.post( "/login", { "request_data":json.dumps(d) } )

    res =  app.post( "/shop_buy", { "request_data":json.dumps( { "item_id":1 } ) } )
    result = json.loads( res.body )
    print result


    app.post( "/logout", {} )
    app.reset()

def test_functional_login_logout():
    app = TestApp( frontend.app )

    d = { 'username':'soiha', 'password':'foobar' }
    app.post( "/login", { "request_data":json.dumps(d) } )

    assert app.post( "/ping", {} ).status == "200 OK"

    app.post( "/logout", {} )

    res = app.post( "/ping", {} )
    result = json.loads( res.body )

    assert result["result"] == 0

    app.reset()

def test_functional_beta_confirm():
    app = TestApp( frontend.app )

    res = app.get( "/beta_confirm", { "key":"ABCDEF", "confirm":"sajkdhad" } )
    print res.body
    pass

def test_functional_beta_signup():
    app = TestApp( frontend.app )

    res = app.post( "/beta_signup", { "beta_key":"ABCDEF", "requested_name":"soiha_beta", "password":"fuppa", "email":"kalle.soiha@treehouse.fi" })
    print res.body
    pass

def test_functional_friend_list():
    app = TestApp( frontend.app )

    d = { 'username':'soiha', 'password':'foobar' }
    app.post( "/login", { "request_data":json.dumps(d) } )

    res = app.post( "/friend_list", { "request_data":json.dumps( {} ) } )
    print res.body

    app.post( "/logout", {} )
    app.reset()

def test_functional_create_user():
    app = TestApp( frontend.app )
    d = { 'username':"supertest", 'password':"foobarfoobar", 'screenname':"supertest", 'email':"super@test.test" }

    res = app.post( "/newuser", { "request_data":json.dumps(d)})
    print res.body

    app.reset()

def test_functional_create_match():
    app = TestApp( frontend.app )
    d = { 'username':'soiha', 'password':'foobar', "clientversion":"0.3.0.2", "clientplatform":"Functional Testing" }
    res = app.post( "/login", { "request_data":json.dumps(d) } )
    print res.body

    d = { "map_preference":"Snowy Mountain Pass", "type":"1v1" }
    res = app.post( "/match/create", { "request_data":json.dumps(d)})
    print res.body
    app.reset()

def test_functional_join_match():
    app = TestApp( frontend.app )
    d = { 'username':'soiha', 'password':'foobar', "clientversion":"0.3.0.2", "clientplatform":"Functional Testing" }
    res = app.post( "/login", { "request_data":json.dumps(d) } )


def test_functional_match_find():
    app = TestApp( frontend.app )
    d = { 'username':'soiha', 'password':'foobar', 'clientversion':'0.3.0.4', 'clientplatform':'Functional Testing' }
    res = app.post( "/login", { "request_data":json.dumps(d) } )
    print res.body

    d = { }
    res = app.post( "/match/find/start", {"request_data":json.dumps(d) } )
    print "match_find: " + res.body
    res = app.post( "/match/find/start", {"request_data":json.dumps(d) } )
    print "match_find: " + res.body

def test_functional_match_control():
    app = TestApp( frontend.app )
    d = { 'username':'soiha', 'password':'foobar', "clientversion":"0.3.0.8", "clientplatform":"Functional Testing" }
    d2 = { 'username':'soiha2', 'password':'soiha2', "clientversion":"0.3.0.8", "clientplatform":"Functional Testing" }

    res = app.post( "/login", { "request_data":json.dumps(d) } )
    #res = app.post( "/login", { "request_data":json.dumps(d2) } )

    res = app.post( "/profile", { "request_data":json.dumps(None) } )
    res = app.post( "/match/create", { "request_data":json.dumps( { "map_preference":"Snowy Mountain Pass", "type":"1v1" } ) } )
    res = app.post( "/match/state", {"request_data":json.dumps(None)})

    print res

    pass


if __name__ == '__main__':
    #test_functional_shop_list()
    #test_functional_shop_buy()
    #test_functional_login_logout()
    #test_functional_beta_signup()
    #test_functional_beta_confirm()
    #test_functional_friend_list()
    #test_functional_create_user()
    #test_functional_create_match()
    #test_functional_match_find()

    test_functional_match_control()

