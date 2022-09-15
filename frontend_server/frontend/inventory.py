import random
from database import User, UserInventoryItem

def find_item_with_id( id, all_items):
    for i in all_items:
        if i["item_id"] == id:
            return i

def equipsheet_with_names( items, gems, equip_sheet_dict ):
    d = {}
    for k in equip_sheet_dict.keys():
        l = []
        db = None
        if k == "gem":
            db = gems
        if k == "item":
            db = items
        for i in equip_sheet_dict[k]:
            if i != -1:
                l.append( db[i]["name"] )
        d[k] = l
    return d

def equipsheet_with_names_for_user( db, user, items, gems ):
    equip_i = get_user_equipped_items( db, user, "item" )
    equip_g = get_user_equipped_items( db, user, "gem" )

    d = {}
    d["item"] = []
    d["gem"] = []
    for i in equip_i:
        for tmp_item in items:
            if tmp_item["item_id"] == i.item_id:
                d["item"].append( tmp_item["name"] )
    for g in equip_g:
        for tmp_gem in gems:
            if tmp_gem["gem_id"] == g.item_id:
                d["gem"].append( tmp_gem["name"] )

    procs = procs_from_current_inventory( db, user, items )
    l = []
    for p in procs.keys():
        l.append( [p, procs[p][0], procs[p][1], procs[p][2], procs[p][3] ])
    d["procs"] = l

    return d

def user_has_item_of_type( db, user, item_category, item_id ):
    item = db.query( UserInventoryItem ).filter( UserInventoryItem.user_id == user.id, UserInventoryItem.item_category == item_category, UserInventoryItem.item_id == item_id ).first()
    if item is None:
        return False
    return True

def user_has_exact_item( db, user, item_category, exact_id ):
    item = db.query( UserInventoryItem ).filter( UserInventoryItem.user_id == user.id, UserInventoryItem.item_category == item_category, UserInventoryItem.id == exact_id ).first()
    if item is None:
        return False
    return True

def user_has_item_with_itemid( db, user, item_id ):
    item = db.query( UserInventoryItem ).filter( UserInventoryItem.user_id == user.id, UserInventoryItem.item_category == "item", UserInventoryItem.item_id == item_id ).first()
    if item is None:
        return False
    return True


def get_user_first_free_slot( db, user, item_category ):
    pass

def get_user_item_in_slot( db, user, item_category, slot_id ):
    if slot_id == -1:
        return None

    item = db.query( UserInventoryItem ).filter( UserInventoryItem.user_id == user.id,
                                                 UserInventoryItem.item_category == item_category,
                                                 UserInventoryItem.slot == slot_id ).first()
    return item

def equip_item_for_user( db, user, item_category, item_id, slot_id ):
    # check if the user has the item
    item = db.query( UserInventoryItem ).filter( UserInventoryItem.user_id == user.id,
                                                 UserInventoryItem.item_category == item_category,
                                                 UserInventoryItem.id == item_id ).first()
    if item is None:
        return False

    item.slot = slot_id
    db.commit()

    return True

def get_user_equipped_items( db, user, item_category ):
    items = db.query( UserInventoryItem ).filter( UserInventoryItem.user_id == user.id,
                                                  UserInventoryItem.item_category == item_category,
                                                  UserInventoryItem.slot != -1 ).order_by( UserInventoryItem.slot )
    return items

def get_user_items_of_category( db, user, item_category ):
    items = db.query( UserInventoryItem ).filter( UserInventoryItem.user_id == user.id, UserInventoryItem.item_category == item_category ).all()
    return items

def get_user_inventory( db, user ):
    items = db.query( UserInventoryItem ).filter( UserInventoryItem.user_id == user.id ).all()
    return items

def get_user_item_with_inventory_id( db, user, inventory_id ):
    item = db.query( UserInventoryItem ).filter( UserInventoryItem.user_id == user.id, UserInventoryItem.id == inventory_id ).first()
    return item

def grant_random_item_to_user( db, user, item_category, all_legal_ids, allow_inventory_duplicates=False ):
    nongrant_ids = ( 61, )   # currently just the celestial duck card

    inv = get_user_inventory( db, user )
    legals = list(all_legal_ids)

    for i in nongrant_ids:
        if i in legals:
            legals.remove( i )

    if not allow_inventory_duplicates:
        for i in inv:
            if i.item_category == item_category and i.item_id in legals:
                legals.remove( i.item_id )

    item = None
    if len(legals) > 0:
        suits = ( "Fire", "Water", "Wood", "Wind", "Iron" )
        ri = random.choice( legals )
        item = UserInventoryItem( user.id, item_category, ri, random.choice(suits), "", -1 )
        print "User %s is granted %s with item id %d" % (user.username, item_category, ri)
        db.add( item )
        db.commit()

    return item

def random_item_with_baseid_to_user( db, user, base_id ):
    suits = ( "Fire", "Water", "Wood", "Wind", "Iron" )
    suit = random.choice(suits)

    item = UserInventoryItem( user.id, "item", base_id, suit, "", -1 )
    return item



def procs_from_current_inventory( db, user, all_items ):
    # single suit proc results:
    # iron; on damage; temporary armor boost
    # fire; on attack; damage multiplier on following attack

    # wind: movement speed bonus on ability use
    # water: healing gain on capture (1.0 chance, proc chance determines gain)
    # wood: mana on last hit (1.0 chance, proc chance determines gain)

    suit_to_proc = {
        "Iron":"On damage",
        "Fire":"On attack",
        "Water":"On capture",
        "Wood":"On last hit",
        "Wind":"On ability",
    }

    suit_to_event = {
        "Iron":"Armor boost",
        "Fire":"Damage token",
        "Water":"Recover mana",
        "Wood":"Recover health",
        "Wind":"Speed boost"
    }

    #suit_to_data = {
    #    "Iron": (10, 3),
    #    "Fire": 2,
    #    "Wood":0.25,
    #    "Water":None,
    #    "Wind":0.5
    #}

    suit_to_data = {
        "Iron": (10, 3),
        "Fire": 2.0,
        "Wood": 0.0,   # calculated
        "Water": 0.0,  # calculated
        "Wind": 1.50
    }


    d = {}  # key by proc event
    inv = get_user_equipped_items( db, user, "item" )
    for inv_item in inv:
        item = find_item_with_id( inv_item.item_id, all_items )
        suit = inv_item.suit
        level = item["level"]
        if suit not in suit_to_proc.keys():
            print "Item id %d (%s) has invalid suit %s!" % (item["id"], item["name"], item["suit"] )
            continue
        # level_req, proc_chance, event, data
        proc = suit_to_proc[suit]
        if suit_to_event[suit] is not None:
            fx = [ 0, 0, 0, 0 ] #if not d.has_key( proc ) else d[proc]
            fx[0] = level if level > fx[0] else fx[0]
            fx[2] = suit_to_event[suit]
            if suit == "Wood" or suit == "Water":
                fx[1] = 1.0
                fx[3] += ( 0.05 * float(level)) if suit == "Wood" else (0.05 * float(level))
            else:
                fx[1] += item["proc_chance"]
                fx[3] = suit_to_data[suit]
            if not d.has_key( proc ):
                d[proc] = [fx]
            else:
                d[proc].append(fx)

    return d