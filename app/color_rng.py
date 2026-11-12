# =============================================================================
#  COLOR UNDER PRESSURE: RNG  —  Man Studio
#  Roll characters from every STORY, every TAPE ... and the devs.
#  Linked to Color Under Pressure: same account, same coins (Firebase).
#  Fonts: Bungee + Russo One (SIL Open Font License 1.1), embedded below.
# =============================================================================
import os, sys, json, math, random, time, threading, hashlib, base64, io, re, datetime
import urllib.request, urllib.error
os.environ.setdefault("PYGAME_HIDE_SUPPORT_PROMPT", "1")
import pygame

VERSION   = "1.1.0"
RNG_OPEN  = "2026-10-10"           # the game opens on this date (DEV accounts can play before)
W, H      = 1280, 720
FPS       = 60
FREE_COOLDOWN = 2.0                # seconds between free rolls
BONUS_EVERY   = 10                 # every 10th roll = x2 luck

# ---------------------------------------------------------------------------
#  paths / save
# ---------------------------------------------------------------------------
def _data_dir():
    base = os.environ.get("LOCALAPPDATA") or os.path.expanduser("~")
    d = os.path.join(base, "ManStudio", "ColorRNG")
    try: os.makedirs(d, exist_ok=True)
    except Exception: d = os.path.dirname(os.path.abspath(sys.argv[0]))
    return d
SAVE_FILE = os.path.join(_data_dir(), "rng_save.json")

def _fresh():
    return {"found": {}, "first": {}, "rolls": 0, "badges": [], "companion": None, "spent": 0,
            "music": 0.6, "sfx": 0.8, "login": None, "best": None, "auto": False,
            "stats": {}, "lang": "EN", "fullscreen": False, "tut_done": False,
            "inv_got": {}, "inv_used": {}, "codes": [], "shiny": {}, "daily": None, "streak": 0, "history": [],
            "sold": {}, "earned": 0}
STAT_KEYS = ("lucky_rolls", "bonus_rolls", "auto_rolls", "play_time", "since_legendary", "longest_dry",
             "luckiest", "coins_spent", "best_luck", "days", "coins_earned", "sold_total")
def load_local():
    try:
        with open(SAVE_FILE, encoding="utf-8") as f: d = json.load(f)
        out = _fresh(); out.update(d); return out
    except Exception: return _fresh()
def save_local():
    try:
        tmp = SAVE_FILE + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f: json.dump(S, f)
        os.replace(tmp, SAVE_FILE)
    except Exception as e: print("save:", e)
S = load_local()
for _d in ("inv_got", "inv_used"):                       # v1.4.1 saved MEGA BOOST as "mega" (= x100)
    if "mega" in S.get(_d, {}): S[_d]["mega100"] = S[_d].get("mega100", 0) + S[_d].pop("mega")
DEVICE_KEYS = ("music", "sfx", "login", "auto", "lang", "fullscreen", "tut_done", "demo_rolls")
DEMO_ROLLS = 5          # not signed in = a short demo: 5 rolls, then sign in to keep playing

def today(): return datetime.date.today().isoformat()

# ---- WINTER UPDATE switches -------------------------------------------------
# Turn both to True when the winter update goes live (7/11/2026).
WINTER_ENABLED    = True       # the shop, the snow, the winter music, the event line
NEW_CHARS_ENABLED = True       # the 9 new characters (5 winter + MANGER, LIA, MR_BURGER, SOS)
NEW_CHAR_KEYS = ("penguin", "snowman", "reindeer", "gingerbread", "frozen",
                 "manger", "lia", "burger", "sos")
WINTER_FROM = "2026-11-07"      # the winter characters can be rolled only inside this window
WINTER_TO   = "2026-11-21"
def winter_now():
    """The winter event. The Man Studio account can see it early; other DEV accounts cannot."""
    if not WINTER_ENABLED: return False
    if WINTER_FROM <= today() <= WINTER_TO: return True
    try: return is_owner() and today() < WINTER_FROM
    except Exception: return False

# ---------------------------------------------------------------------------
#  Firebase (same project + same accounts as Color Under Pressure)
# ---------------------------------------------------------------------------
FIREBASE_API_KEY = "AIzaSyCNrpFuDyn3HKCwWpV-RfGKKAnLO_omA2U"
FIREBASE_DB      = "https://colorunderpressure-default-rtdb.firebaseio.com"
FB_EMAIL_DOMAIN  = "players.colorunderpressure.game"
DEV_ACCOUNTS = {"man_studio":   "f7942e69f789d34227c31fcde2995d9c5ca385e79332b33e495ba0315d4bcfed",
                "lunavr_tester": "17098ee0bb7924ce4201f25865e624415ec5905eafc94aac4102458e477bd431"}
AUTH = {"user": None, "token": None, "refresh": None, "exp": 0, "loading": False, "error": None,
        "dev_ok": False, "anon": None, "coins": None, "applied": 0, "coins_t": 0}
NET  = {"dirty": False, "last": 0.0, "feed": [], "feed_t": 0.0, "ticker": None, "ticker_t": 0.0}

def _auth_call(endpoint, payload, host="identitytoolkit"):
    if host == "securetoken": url = f"https://securetoken.googleapis.com/v1/token?key={FIREBASE_API_KEY}"
    else: url = f"https://identitytoolkit.googleapis.com/v1/accounts:{endpoint}?key={FIREBASE_API_KEY}"
    req = urllib.request.Request(url, data=json.dumps(payload).encode(), method="POST",
                                 headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=8) as r: return json.loads(r.read()), None
    except urllib.error.HTTPError as e:
        try: msg = json.loads(e.read()).get("error", {}).get("message", "ERROR")
        except Exception: msg = "ERROR"
        return None, str(msg).split(" ")[0]
    except Exception: return None, "OFFLINE"

def _acct_email(uid):
    local = uid if re.fullmatch(r"[a-z0-9_-]{1,40}", uid) else "u" + uid.encode("utf-8").hex()[:60]
    return f"{local}@{FB_EMAIL_DOMAIN}"
def _acct_password(pw): return "CUP-" + str(pw)
def _dev_fp(uid, pw): return hashlib.pbkdf2_hmac("sha256", str(pw).encode(), ("cup-dev|" + uid).encode(), 200000).hex()

def _token():
    if AUTH["user"]:
        if AUTH["refresh"] and time.time() > AUTH["exp"] - 300:
            d, err = _auth_call(None, {"grant_type": "refresh_token", "refresh_token": AUTH["refresh"]}, host="securetoken")
            if d: AUTH["token"] = d.get("id_token"); AUTH["exp"] = time.time() + int(d.get("expires_in", 3600))
        return AUTH["token"]
    return AUTH["anon"]

FBERR = object()     # "the request failed" (None = the place is empty)
def fb(method, path, data=None, query=""):
    tok = _token()
    url = FIREBASE_DB + path + ".json?" + (f"auth={tok}&" if tok else "") + query
    body = json.dumps(data).encode() if data is not None else None
    req = urllib.request.Request(url, data=body, method=method, headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=8) as r:
            t = r.read(); return json.loads(t) if t.strip() else None
    except Exception as e:
        print("fb", method, path, e); return FBERR

def bg(fn, *a):
    threading.Thread(target=fn, args=a, daemon=True).start()

def anon_init():
    d, err = _auth_call("signUp", {"returnSecureToken": True})
    if d: AUTH["anon"] = d.get("idToken")
bg(anon_init)

def is_dev(): return bool(AUTH["user"] and AUTH["dev_ok"])
OWNER_ACCOUNT = "man_studio"          # only this DEV account sees events before they open
def _acct_key(u):
    """The account key, the same way sign_in builds it: "Man Studio" -> "man_studio"."""
    u = u or {}
    return str(u.get("key") or u.get("name", "")).strip().lower().replace(" ", "_")
def is_owner():
    return bool(is_dev() and _acct_key(AUTH["user"]) == OWNER_ACCOUNT)
def game_open(): return is_dev() or today() >= RNG_OPEN

def sign_in(name, password=None, silent=False):
    if AUTH["loading"]: return
    AUTH["loading"] = True; AUTH["error"] = None
    def fail(msg): AUTH["loading"] = False; AUTH["error"] = None if silent else msg
    def run():
        try:
            nm = name.strip(); key = nm.lower().replace(" ", "_")
            prev = S.get("login") or {}
            if password:
                d, err = _auth_call("signInWithPassword", {"email": _acct_email(key), "password": _acct_password(password),
                                                           "returnSecureToken": True})
                if not d:
                    if err == "OFFLINE": return fail("No connection")
                    if err in ("INVALID_LOGIN_CREDENTIALS", "INVALID_PASSWORD"): return fail("Wrong password")
                    if err == "EMAIL_NOT_FOUND": return fail("No account with this name. Make one in Color Under Pressure!")
                    return fail("Sign in failed")
                tok, rt, uid, exp = d["idToken"], d["refreshToken"], d["localId"], int(d.get("expiresIn", 3600))
            else:
                rt = prev.get("refresh")
                if not rt: return fail(None)
                d, err = _auth_call(None, {"grant_type": "refresh_token", "refresh_token": rt}, host="securetoken")
                if not d:
                    if err != "OFFLINE": S["login"] = None; save_local()
                    return fail(None)
                tok, rt, uid, exp = d["id_token"], d.get("refresh_token", rt), d["user_id"], int(d.get("expires_in", 3600))
            AUTH.update(token=tok, refresh=rt, exp=time.time() + exp, user={"uid": uid, "name": nm, "key": key})
            want = DEV_ACCOUNTS.get(key); AUTH["dev_ok"] = False
            fp = None
            if want:
                fp = _dev_fp(key, password) if password else prev.get("dev")
                AUTH["dev_ok"] = (fp == want)
            S["login"] = {"name": nm, "refresh": rt, "dev": fp if AUTH["dev_ok"] else None}
            cloud_pull(); refresh_coins()
            if AUTH["dev_ok"]:
                award("tester")
            save_local(); AUTH["loading"] = False
        except Exception as e:
            fail(str(e))
    bg(run)

def sign_out():
    if AUTH["user"]: cloud_push()
    AUTH.update(user=None, token=None, refresh=None, dev_ok=False, coins=None)
    keep = {k: S[k] for k in DEVICE_KEYS if k in S}
    S.clear(); S.update(_fresh()); S.update(keep); S["login"] = None; save_local()

def cloud_pull():
    """Merge the account's RNG progress with this computer's."""
    uid = AUTH["user"]["uid"]
    c = fb("GET", f"/users/{uid}/rng")
    if not isinstance(c, dict): c = {}
    for k, v in (c.get("found") or {}).items(): S["found"][k] = max(int(v), int(S["found"].get(k, 0)))
    for k, v in (c.get("first") or {}).items():
        if k not in S["first"] or v < S["first"][k]: S["first"][k] = v
    S["rolls"] = max(int(c.get("rolls", 0) or 0), S["rolls"])
    S["spent"] = max(int(c.get("spent", 0) or 0), S["spent"])
    S["earned"] = max(int(c.get("earned", 0) or 0), int(S.get("earned", 0) or 0))
    for k, v in (c.get("sold") or {}).items(): S["sold"][k] = max(int(v or 0), int(S["sold"].get(k, 0)))
    for key in ("inv_got", "inv_used"):
        for k, v in (c.get(key) or {}).items(): S[key][k] = max(int(v or 0), int(S[key].get(k, 0)))
    for k, v in (c.get("shiny") or {}).items(): S["shiny"][k] = max(int(v or 0), int(S["shiny"].get(k, 0)))
    if (c.get("daily") or "") > (S.get("daily") or ""): S["daily"] = c["daily"]; S["streak"] = int(c.get("streak", 0) or 0)
    for cd in c.get("codes") or []:
        if cd not in S["codes"]: S["codes"].append(cd)
    cs = c.get("stats") or {}
    st = S.setdefault("stats", {})
    for k, v in cs.items():
        if k == "days": st["days"] = sorted(set(st.get("days", [])) | set(v or []))[-400:]
        elif isinstance(v, (int, float)): st[k] = max(v, st.get(k, 0))
    for b in c.get("badges") or []:
        if b not in S["badges"]: S["badges"].append(b)
    if c.get("companion") and not S.get("companion"): S["companion"] = c["companion"]
    _clean_save()                      # the cloud save may name characters this build does not have
    NET["dirty"] = True; cloud_push()

def cloud_push():
    if not AUTH["user"]: return
    uid = AUTH["user"]["uid"]
    data = {k: S[k] for k in ("found", "first", "rolls", "badges", "companion", "spent", "stats", "inv_got", "inv_used", "codes",
                              "shiny", "daily", "streak", "sold", "earned")}
    data["name"] = AUTH["user"]["name"]; data["ver"] = VERSION; data["saved"] = int(time.time())
    if fb("PUT", f"/users/{uid}/rng", data) not in (None, FBERR): NET["dirty"] = False
    push_leader()

def best_rolled():
    """The rarest ROLLED character (secrets don't count: you find them, you don't roll them)."""
    ks = [k for k in S["found"] if k in CH and CH[k]["odds"]]
    return max(ks, key=lambda k: CH[k]["odds"]) if ks else None
def push_leader():
    """Leaderboard: /rng_leader/<uid>. DEV accounts can force rolls, so they are not on it."""
    if not AUTH["user"] or is_dev(): return
    b = best_rolled()
    row = {"name": AUTH["user"]["name"][:20], "best": CH[b]["odds"] if b else 0, "best_char": CH[b]["name"] if b else "",
           "uniq": sum(1 for k in CH if k in S["found"]), "rolls": int(S["rolls"]), "t": int(time.time())}
    fb("PUT", f"/rng_leader/{AUTH['user']['uid']}", row)
LB = {"rows": {}, "t": 0.0, "busy": False, "tab": "best"}
def pull_leader():
    LB["busy"] = True
    for key in ("best", "uniq", "rolls"):
        d = fb("GET", "/rng_leader", query=f"orderBy=%22{key}%22&limitToLast=10")
        if isinstance(d, dict):
            LB["rows"][key] = sorted(d.values(), key=lambda r: -(r.get(key) or 0))
        elif d is FBERR: LB["rows"].setdefault(key, None)
    LB["t"] = time.time(); LB["busy"] = False

def refresh_coins():
    """Coins live in Color Under Pressure's save. What RNG spent is written to /rng/spent;
    Color Under Pressure takes it off the next time it syncs."""
    if not AUTH["user"]: return
    uid = AUTH["user"]["uid"]
    c = fb("GET", f"/users/{uid}/gd/coins"); a = fb("GET", f"/users/{uid}/gd/rng_applied")
    if c is not FBERR and a is not FBERR:
        AUTH["coins"] = int(c or 0); AUTH["applied"] = int(a or 0); AUTH["coins_t"] = time.time()
def coins():
    """CUP coins - what RNG spent + what RNG earned (selling + new characters), minus what CUP already counted."""
    if AUTH["coins"] is None: return None
    net = S["spent"] - int(S.get("earned", 0) or 0)
    return max(0, AUTH["coins"] - (net - AUTH["applied"]))

NEW_CHAR_BONUS = 100            # every NEW character = +100 coins
AFK_LIMIT = 2 * 60 * 60         # AUTO ROLL + no mouse/keys for 2 hours = disconnected
def sell_price(c): return 0 if not c["odds"] else max(1, c["odds"] // 20)      # every character has its own price
def owned(k): return max(0, int(S["found"].get(k, 0)) - int(S["sold"].get(k, 0)))
def earn(n, why="sold"):
    S["earned"] = int(S.get("earned", 0) or 0) + int(n)
    st = S.setdefault("stats", {}); st["coins_earned"] = st.get("coins_earned", 0) + int(n)
    NET["dirty"] = True; save_local()

def net_tick():
    now = time.time()
    if AUTH["user"] and NET["dirty"] and now - NET["last"] > 15:
        NET["last"] = now; bg(cloud_push)
    if AUTH["user"] and now - AUTH["coins_t"] > 60:
        AUTH["coins_t"] = now; bg(refresh_coins)
    if now - NET["feed_t"] > 20 and (AUTH["user"] or AUTH["anon"]):
        NET["feed_t"] = now; bg(pull_feed)

def pull_feed():
    d = fb("GET", "/rng_feed", query='orderBy=%22%24key%22&limitToLast=8')
    if isinstance(d, dict):
        items = [d[k] for k in sorted(d)]
        new = [i for i in items if i not in NET["feed"]]
        if NET["feed"] and new:
            NET["ticker"] = new[-1]; NET["ticker_t"] = time.time()
        NET["feed"] = items

def post_feed(ch):
    if not AUTH["user"]: return
    item = {"name": AUTH["user"]["name"][:20], "char": ch["name"], "rar": ch["rar"],
            "odds": ch["odds"], "t": int(time.time())}
    bg(lambda: fb("POST", "/rng_feed", item))

# ---------------------------------------------------------------------------
#  pygame setup
# ---------------------------------------------------------------------------
pygame.mixer.pre_init(44100, -16, 2, 512)
pygame.init()
try: pygame.mixer.init()
except Exception: pass
pygame.display.set_caption("Color Under Pressure: RNG")
screen = pygame.display.set_mode((W, H), pygame.RESIZABLE)
def set_fullscreen(on):
    global screen
    S["fullscreen"] = bool(on)
    try:
        screen = pygame.display.set_mode((0, 0), pygame.FULLSCREEN) if on else pygame.display.set_mode((W, H), pygame.RESIZABLE)
    except Exception as e:
        print("fullscreen:", e); S["fullscreen"] = False; screen = pygame.display.set_mode((W, H), pygame.RESIZABLE)
    save_local()
canvas = pygame.Surface((W, H))
clock = pygame.time.Clock()

FONT_DATA = {"bungee": "AAEAAAARAQAABAAQR0RFRjiFNPEAAV4EAAADMEdQT1MF7LfLAAFhNAAAU0xHU1VClRflCgABtIAAAA6ST1MvMnkEhCoAAAGYAAAAYGNtYXBNc2oPAAASlAAACcBnYXNwAAAAEAABXfwAAAAIZ2x5ZnhHhvsAACSsAAEFdmhlYWQpS8KRAAABHAAAADZoaGVhCTcKCwAAAVQAAAAkaG10eLeEedcAAAH4AAAQnGxvY2Gl2eUMAAAcXAAACFBtYXhwBDYA5AAAAXgAAAAgbmFtZalahcMAASokAAAG/HBvc3TtfT2tAAExIAAALNxwcmVwaAaMhQAAHFQAAAAHdmhlYQXgE0YAAcMUAAAAJHZtdHj8dZ1UAAHDOAAADZwAAQAAAAIAALvILdJfDzz1AAMD6AAAAADifb9qAAAAAOJ9v3T9oPxsB5gGZAAAAAYAAgAAAAAAAAABAAAD/P7UAAAFif2g/Z8HmAPoAAAAAAAAAAAAAAAAAAAEJwABAAAEJwB9AAcAZQAEAAEAAAAAAAAAAAAAAAAAAwABAAQDIQGQAAUAAAKKAlgAAABLAooCWAAAAV4AMgEsAAAAAAAAAAAAAAAAoAAA/1AA8HsAAAAQAAAAAGRqciAAwAAg/1oD/P7UAAAGbwOfIAABkwAAAAAB9ALQAAAAIAADA+gAZADhAAAC2gA2AtoANgLaADYC2gA2AtoANgLaADYC2gA2AtoANgLaADYC2gA2AtUARQJ0ADoCdAA6AnQAOgJ0ADoCdAA6AnQAOgLqAEUC6gBFAo4ARQKOAEUCjgBFAo4ARQKOAEUCjgBFAo4ARQKOAEUCjgBFAo4ARQJqAEUCxAA6AsQAOgLEADoCxAA6AsQAOgL3AEUC9wBFAl0ANQJdADUCXQA1Al0ANQJdADUCXQA1Al0ANQJdADUCXQA1Al0ANQKwACkCsAApAuoARQLqAEUCtwBFArcARQK3AEUCtwBFA1EARQLxAEUC8QBFAvEARQLxAEUC8QBFAuEAOgLhADoC4QA6AuEAOgLhADoC4QA6AuEAOgLhADoC4QA6AqoARQLhADoC5wBFAucARQLnAEUC5wBFAooAMwKKADMCigAzAooAMwKKADMCigAzApAAHAKQABwCkAAcAuoAQALqAEAC6gBAAuoAQALqAEAC6gBAAuoAQALqAEAC6gBAAuoAQALqAEAC2gA2Az8APAM/ADwDPwA8Az8APAM/ADwC4QA8AsEALQLBAC0CwQAtAsEALQLBAC0ClAAuApQALgKUAC4ClAAuA+0ANgL0ABQC4QA6ArQARQL0ABQDCwAeAugARQK3AEUCwQAUAuoAQAP3ADoCkAAcAvcARQLgAEAC4ABAAuAAQALgAEAC4ABAAuAAQALgAEAC4ABAAuAAQALgAEACgwA6AoMAOgKDADoCgwA6AoMAOgKDADoCgwA6AoMAOgKDADoCgwA6AXMARgFz//YBc//4AXP/6AFz/88Bc//oAXP/6AFz/+ABcwAqAXMARgJnAEUCZwBFAmcARQJnAEUCZwBFAnEAFAQuAEAC6gBAAuoAQALqAEAC6gBAAuoAQAQuAEAELgBABC4AQAQuAEAELgBAAuEAPALCAC8CwgAvAsIALwLCAC8CwgAvA/UAQAIIACQCDQAnAtcAOgJZADACfwAoAn0AMQLFAD8ChwA3ArUAOgJzACYCxwAvArUALwLeAEYBpAAoAt4ARgRuAEYBrQAwAa0ALQGtADABrQAtAccAFAHHAC0C7gAjBAcAKgWJACoBZAA3AoYALQGAADcBgAA3ATMANwEzADcCrAAtAqwALQGAADcCrAAtAjMAPAIzAFADLAAyAywAPALOADYCzgAyAs4AMgGAADcBgAA3AYAANwGAADcEVgA3AagAUQGnAFECkAAtApAALQFbAAEBWwABAT0AAQFbAEEBWwBBA2MAPAL+ACUCeAAlAooANAKqACMBbAAtAbsALQFkADUCmgA1At4ARgLeAEYC3gBGAt4ARgLeAEcC3gBGAsoAUALKAFoCygBQAsoAWgLeAEYC3gBGAt4ARgLKACEC3gBGArQALwL3AEUCigAuAtoANgMJACQC0QA9AskAPQLlAB0DbgAtAtsARQHaAA8CigAzAnQAOgK3ABQDNQAiAr8ALAKIACgCPgAtAjAAOAOHABAB4wAtA2MAPANjADwB9AAoAfQAKAH0//cB9AAoAfQAKAH0ACEB9AAoAfQAKAH0ABAB9ACIAfQAIQH0AGUB9AB7AfQAhgH0AHQAAP+ZAAD/mQH0ACEB9AAoAfQAKAH0ACEB9AAoAfQAIQH0ACEB9AAoA+gArQPoANED6AC5A+gA0QPoAOsD6ADfA+gA4APoAOsD6ACyA+gAngPoAJQD6AC8A+gAlAPoAKgD6ACCA+gAmQPoAPUD6AD1A+gAtgPoALYD6ABfA+gAWQPoAHcD6ADqA+gAjgPoAOoD6ABJA+gASQPoAK4D6AChA+gAggPoAJkD6AD1A+gAdAPoAHMD6AD3A+gAxQPoAMID6AB3A+gA6gPoAI4D6ADpA+gAbwPoAGQD6AC7A+gAvQPoAAAB9AAAA+j/2APo/9gCIgAAAiL/2AU3AIAFNwCAAjAAMgIw/9gFAAAKBQAACgFeAEYBXv/YBQAAZAUAAGQBXgAhAV7/2AUAAEsFAABLAV4AZAFe/9gFAABkBQAAZAFeAEYBXv/YBQAAZAUAAGQCiv/7Aor/2APo/9gD6P/YA4QAFAOE/9gFAP+mBQD/pgKKAAgCiv/YA+j/DQPo/w0D6P+rA+j/qwU3/aAFNwCABQAAZAUAAEYFAABkBQAARgUAAGQFAABkBQAAZAUAAGQFAP/9BQAAZAUAAGQFAABkBQAAZAUAAGQFMgAHBTL//QUA/7MFAP+zBQD//wUA//wFAABkBQAAZAPoAAAD6ADHA+gAyQPoAMkD6ADJA+gAyQPoAMkD6ADHA+gAyQPoAMkD6ADJA+gAyQPoAMQD6ADEA+gAxAPoAMQD6ADEA+gAxAPoAMgD6ADIA+gAyQPoAMgD6ADIA+gAyAPoAMgD6ADIA+gAyAPoAMgD6ADIA+gAyAPoAMkD6ADDA+gAwwPoAMMD6ADDA+gAwwPoAMgD6ADIA+gA0QPoANED6ADRA+gA0QPoANED6ADRA+gA0QPoANED6ADRA+gA0QPoAMgD6ADIA+gAyQPoAMgD6ADJA+gAyAPoAMgD6ADJA+gAswPoAMgD6ADIA+gAyAPoAMgD6ADIA+gAxAPoAMQD6ADEA+gAxAPoAMQD6ADEA+gAxAPoAMQD6ADEA+gAyAPoAMQD6ADIA+gAyAPoAMgD6ADIA+gAyAPoAMgD6ADIA+gAyAPoAMgD6ADIA+gAyAPoAMgD6ADIA+gAyAPoAMgD6ADIA+gAyAPoAMgD6ADIA+gAyAPoAMgD6ADIA+gAyAPoAMgD6ADHA+gAsgPoALID6ACyA+gAsgPoALID6ADIA+gAxwPoAMcD6ADHA+gAxwPoAMcD6ADIA+gAyAPoAMgD6ADIA+gAqQPoAI0D6ADHA+gAyQPoAI0D6ACWA+gAyAPoAMgD6ACOA+gAyAPoALMD6ADIA+gAyAPoAMgD6ADHA+gAxwPoAMcD6ADHA+gAxwPoAMgD6ADHA+gAxwPoAMcD6ADEA+gAxAPoAMQD6ADEA+gAxAPoAMQD6ADEA+gAxAPoAMQD6ADEA+gBgAPoAMgD6AEiA+gBIgPoASID6AEKA+gBIgPoASID6AEbA+gBZAPoAYAD6ADJA+gAyAPoAMkD6ADJA+gAyQPoAI4D6ADJA+gAlwPoAMgD6ADIA+gAyAPoAMgD6ADIA+gAlwPoAJcD6ACXA+gAlwPoAJcD6ADAA+gAyAPoAMgD6ADIA+gAyAPoAMgD6ACzA+gBgQPoAMgD6ADIA+gAyAPoAMgD6ADIA+gAyAPoAMMD6ADIA+gAwwPoAMMD6AGOA+gBjQPoAY0D6AA8A+gAPAPoADwD6AA8A+gAPAPoADwD6AFrA+gBawPoAMsD6ADLA+gBawPoAMsD6AD5A+gA+QPoAP0D6AD3A+gBawPoAWsD6AAAA+gBcgPoANkD6AC/A+gAwAPoAGUD6AFyA+gA3wPoALID6AC4A+gAxAPoAXoD6ADEA+gBawPoAWsD6ADZA+gAyQPoAMkD6ADJA+gAxAPoAMgD6ADIA+gAwwPoAMgD6ADRA+gAyAPoAMgD6ADIA+gAyAPoAMQD6ADIA+gAyAPoAMgD6ADIA+gAsgPoAMcD6ADIA+gAxwPoAMQD6AGAA+gAyAPoAJcD6ADIAtoANgLaADYC2gA2AtoANgLaADYC2gA2AtoANgLaADYC2gA2AtoANgLVAEUCdAA6AnQAOgJ0ADoCdAA6AnQAOgJ0ADoC6gBFAuoARQKOAEUCjgBFAo4ARQKOAEUCjgBFAo4ARQKOAEUCjgBFAo4ARQKOAEUCagBFAsQAOgLEADoCxAA6AsQAOgLEADoC9wBFAvcARQJdADUCXQA1Al0ANQJdADUCXQA1Al0ANQJdADUCXQA1Al0ANQKwACkCsAApAuoARQLqAEUCtwBFArcARQK3AEUCtwBFA1EARQLxAEUC8QBFAvEARQLxAEUC8QBFAuEAOgLhADoC4QA6AuEAOgLhADoC4QA6AuEAOgLhADoC4QA6AqoARQLhADoC5wBFAucARQLnAEUC5wBFAooAMwKKADMCigAzAooAMwKKADMCigAzApAAHAKQABwCkAAcAuoAQALqAEAC6gBAAuoAQALqAEAC6gBAAuoAQALqAEAC6gBAAuoAQALqAEAC2gA2Az8APAM/ADwDPwA8Az8APAM/ADwC4QA8AsEALQLBAC0CwQAtAsEALQLBAC0ClAAuApQALgKUAC4ClAAuAvcARQPtADYC9AAUAuEAOgK0AEUC9AAUAwsAHgJdADUC6ABFArcARQLBABQC6gBAA/cAOgKQABwByQAwAeUAKAHkADEB/AArBIgAMASzADAEvQAxAssANQLaADYC2gA2AtoANgLaADYC2gA2AtoANgLaADYC2gA2AtoANgLaADYC2gA2AtoANgLaADYC6gBFAuoARQKOAEUCjgBFAo4ARQKOAEUCjgBFAo4ARQKOAEUCjgBFAsQAOgLEADoC9wBFAvcARQJdADUCXQA1Al0ANQK3AEUCtwBFArcARQNRAEUC8QBFAvEARQLxAEUC6wA6AuEAOgLhADoC4QA6AuEAOgLhADoC4QA6AuEAOgLhADoC6wA6AusAOgLrADoC6wA6AusAOgLnAEUC5wBFAucARQKKADMCigAzApAAHAKQABwCkAAcAvQAQALqAEAC6gBAAuoAQALqAEAC6gBAAuoAQALqAEAC9ABAAvQAQAL0AEAC9ABAAvQAQALBAC0CwQAtAsEALQLBAC0ClAAuAokAOgLqAEUC8QA4ArAAKQLqADoCywA1AssAMgLaADYC2gA2AtoANgLaADYC2gA2AtoANgLaADYC2gA2AtoANgLaADYC2gA2AtoANgLaADYC6gBFAuoARQKOAEUCjgBFAo4ARQKOAEUCjgBFAo4ARQKOAEUCjgBFAsQAOgLEADoC9wBFAvcARQJdADUCXQA1Al0ANQK3AEUCtwBFArcARQNRAEUC8QBFAvEARQLxAEUC6wA6AuEAOgLhADoC4QA6AuEAOgLhADoC4QA6AuEAOgLhADoC6wA6AusAOgLrADoC6wA6AusAOgLnAEUC5wBFAucARQKKADMCigAzApAAHAKQABwCkAAcApAAHAL0AEAC6gBAAuoAQALqAEAC6gBAAuoAQALqAEAC6gBAAvQAQAL0AEAC9ABAAvQAQAL0AEACwQAtAsEALQLBAC0CwQAtApQALgH0AIYB9ACGATgAIQE4ACEBZAA9AfQAKAH0ACgB9AAoAWQAPQAA/y4AAP8uAAD/LgAA/y8AAP8uAAD/JwAA/40AAP8ZAAD/jQAA/ycAAP8lAAD/LgAA/4QAAP+NAAD/GQAA/4wAAP9r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ABQCuAB2AxoAGgK+ABsCvwAcAsAAHQLBAB4CwgAhAsUAIgLGACMCxwAkAsgAJgLKAHcDGwAsAtAALQLRAC4C0gAvAtMAMAMcAHgDHQAyAtUANALXA3kANgLZADcC2gA4AtsAeQMeAHoDHwA8At8APQLgAD4C4QN6AHsDIABFAugARgLpAEcC6gB8AyEASwLuAEwC7wBNAvAATwLyAFAC8wBRAvQAUgL1AFUC+ABWAvkAfQMiAFwC/wBdAwAAXgMBAF8DAgBgAwMAYQMEAGQDBwBrAw8AbABvAxIAcAMTAHEDFANQA6QDZgO7AysDfwNGA5oDUQOlA2cDvANoA70DaQO+A2oDvwNrA8ADQgOWAFMC9gBVAvgBIQElASYBKAEiAR4BKQPmA+cDOAOMAzkDjQNDA5cDRAOYA0UDmQNJA50DSgOeA0sDnwNMA6ADTQOhA04DogNPA6MDXgOyA18DswNgA7QDYQO1A2IDtgNkA7gDZQO5AGUDCABmAwkAZwMKA3MDyAN3A8wDLAOAAy0DgQMuA4IDLwODAzADhAMxA4UDMgOGAzMDhwM0A4gDNQOJAzYDigM3A4sDOgOOAzsDjwM8A5ADPQORAz4DkgM/A5MDQAOUA0EDlQNHA5sDSAOcA1IDpgNTA6cDVAOoA1UDqQNWA6oDVwOrA1gDrANZA60DWgOuA1sDrwNcA7ADXQOxA2wDwQNtA8IDbgPDA28DxANwA8UDcQPGA3IDxwBtAxADdAPJA3UDygN2A8sBZAFjAWQBYwPwAMMAxAPxANAA0QDWANQA1QDXAN0A3gDzBCMEJAQYA/YBFQEHAPcA8gEMBAID/gQFBAEEAwP/BAQEAAGZAZoBnAGbAUMBRAFLAUwBTQFOANIA0wDvASoBRQFGAUcBSAFJAUoBZgFpAWoBhwGKAYkBkQGTAZUBlwGdAZ8BngGgAYsBjAGNAY4BgwGEAYUBhgGiAaMBpAGhAX8BgAGBAYIBpQGyAbMBtAG1AbYBuAHFAcYBxwHIAcoB1gHYAdoB2wHcAd8B4AHhAeIB5AHlAeYB5wHoAekB6gHrAe8B8AHxAfMB9AH1AfYB9wH5AfoCCAIJAgoCCwIOAg8CEAIRAoMChAKGAaYBsAGxAbcBuQHDAcQByQHLAdUB1wHZAd0B3gHjAewB7QHuAfIB+AH7AgYCBwIMAg0CEgGSAZQBlgGY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AW0AAP//ADb/RgKkAtACBgALAAD//wBFAAACqwLQAgYADAAA//8AOgAAAkgC0AIGAA0AAP//ADr/ggJIAtACBgAOAAD//wA6AAACSAPFAiYADQAAAAcD1wF3AAD//wA6AAACSAPRAiYADQAAAAcD2AFZAAD//wA6AAACSAO/AiYADQAAAAcD3AFkAAD//wA6AAACSAPUAiYADQAAAAcD4QFZAAD//wBFAAACsALQAgYAEwAA//8ARQAAArAD1AImABMAAAAHA+EBdQAA//8ARQAAAl0C0AIGABUAAP//AEUAAAJdA8UCJgAVAAAABwPWAUcAAP//AEUAAAJdA8UCJgAVAAAABwPXAWUAAP//AEUAAAJdA9ECJgAVAAAABwPYAVEAAP//AEUAAAJdA7MCJgAVAAAABwPdAVgAAP//AEUAAAJdA50CJgAVAAAABwPaAVEAAP//AEUAAAJdA9ECJgAVAAAABwPbAVsAAP//AEUAAAJdA78CJgAVAAAABwPcAUYAAP//AEX/RgJdAtACBgAdAAD//wBFAAACXQPUAiYAFQAAAAcD4QFYAAD//wBFAAACSwLQAgYAHwAA//8AOgAAAo8C0AIGACAAAP//ADoAAAKPA9ECJgAgAAAABwPYAX0AAP//ADoAAAKPA9ECJgAgAAAABwPbAXYAAP//ADoAAAKPA78CJgAgAAAABwPcAXcAAP//ADr+lgKPAtACJgAgAAAABgEpfAD//wBFAAACsgLQAgYAJQAA//8ARQAAArID0QImACUAAAAHA9gBewAA//8ANQAAAicC0AIGACcAAP//ADUAAAInA8UCJgAnAAAABwPWAS4AAP//ADUAAAInA8UCJgAnAAAABwPXAS4AAP//ADUAAAInA9ECJgAnAAAABwPYAS4AAP//ADUAAAInA7MCJgAnAAAABwPdASsAAP//ADUAAAInA7ICJgAnAAAABwPZAS0AAP//ADUAAAInA50CJgAnAAAABwPaAS4AAP//ADUAAAInA9ECJgAnAAAABwPbAS4AAP//ADX/RgInAtACBgAvAAD//wAp//ECcALQAgYAMQAA//8AKf/xAscD0QImADEAAAAHA9gB9gAA//8ARQAAAq4C0AIGADMAAP//AEX+lgKuAtACJgAzAAAABgEpewD//wBFAAACigLQAgYANQAA//8ARQAAAooDxQIm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AAEECQADADIBZAADAAEECQAEABwBlgADAAEECQAFABoBsgADAAEECQAGABwBzAADAAEECQAHAFIB6AADAAEECQAIACYCOgADAAEECQAJACYCOgADAAEECQALACYCYAADAAEECQAMACYCYAADAAEECQANASIChgADAAEECQAOADYDqAADAAEECQEAABYD3gADAAEECQEBAA4D9AADAAEECQECABgEAgADAAEECQEDABgEGgADAAEECQEEACYEMgADAAEECQEFABgEWAADAAEECQEGACYEcAADAAEECQEHADoElgADAAEECQEIABoE0AADAAEECQEJADAE6gADAAEECQEKACwFGlJvdW5kIGZvcm1zUm91bmQgRVNhbnMtc2VyaWYgSVNhbnMtc2VyaWYgTEFsdGVybmF0ZSBhbXBlcnNhbmRTbWFsbCBxdW90ZXNWZXJ0aWNhbCBhbHRlcm5hdGVzSm9obiBEb3duZXIncyBSZWNvbW1lbmRhdGlvbnNSb3RhdGVkIGZvcm1zSG9yaXpvbnRhbCBibG9jayBzcGFjaW5nVmVydGljYWwgYmxvY2sgc3BhY2luZwBDAG8AcAB5AHIAaQBnAGgAdAAgADIAMAAyADMAIABUAGgAZQAgAEIAdQBuAGcAZQBlACAAUAByAG8AagBlAGMAdAAgAEEAdQB0AGgAbwByAHMAIAAoAGgAdAB0AHAAcwA6AC8ALwBnAGkAdABoAHUAYgAuAGMAbwBtAC8AZABqAHIAcgBiAC8AQgB1AG4AZwBlAGUAKQBCAHUAbgBnAGUAZQBSAGUAZwB1AGwAYQByADIALgAwADAAMAA7AGQAagByACAAOwBCAHUAbgBnAGUAZQAtAFIAZQBnAHUAbABhAHIAQgB1AG4AZwBlAGUAIABSAGUAZwB1AGwAYQByAFYAZQByAHMAaQBvAG4AIAAyAC4AMAAwADAAQgB1AG4AZwBlAGUALQBSAGUAZwB1AGwAYQByAEIAdQBuAGcAZQBlACAAaQBzACAAYQAgAHQAcgBhAGQAZQBtAGEAcgBrACAAbwBmACAAVABoAGUAIABGAG8AbgB0ACAAQgB1AHIAZQBhAHUALgBEAGEAdgBpAGQAIABKAG8AbgBhAHQAaABhAG4AIABSAG8AcwBzAGgAdAB0AHAAcwA6AC8ALwB3AHcAdwAuAGQAagByAC4AYwBvAG0AVABoAGkAcwAgAEYAbwBuAHQAIABTAG8AZgB0AHcAYQByAGUAIABpAHMAIABsAGkAYwBlAG4AcwBlAGQAIAB1AG4AZABlAHIAIAB0AGgAZQAgAFMASQBMACAATwBwAGUAbgAgAEYAbwBuAHQAIABMAGkAYwBlAG4AcwBlACwAIABWAGUAcgBzAGkAbwBuACAAMQAuADEALgAgAFQAaABpAHMAIABsAGkAYwBlAG4AcwBlACAAaQBzACAAYQB2AGEAaQBsAGEAYgBsAGUAIAB3AGkAdABoACAAYQAgAEYAQQBRACAAYQB0ADoAIABoAHQAdABwAHMAOgAvAC8AbwBwAGUAbgBmAG8AbgB0AGwAaQBjAGUAbgBzAGUALgBvAHIAZwBoAHQAdABwAHMAOgAvAC8AbwBwAGUAbgBmAG8AbgB0AGwAaQBjAGUAbgBzAGUALgBvAHIAZwBSAG8AdQBuAGQAIABmAG8AcgBtAHMAUgBvAHUAbgBkACAARQBTAGEAbgBzAC0AcwBlAHIAaQBmACAASQBTAGEAbgBzAC0AcwBlAHIAaQBmACAATABBAGwAdABlAHIAbgBhAHQAZQAgAGEAbQBwAGUAcgBzAGEAbgBkAFMAbQBhAGwAbAAgAHEAdQBvAHQAZQBzAFYAZQByAHQAaQBjAGEAbAAgAGEAbAB0AGUAcgBuAGEAdABlAHMASgBvAGgAbgAgAEQAbwB3AG4AZQByACcAcwAgAFIAZQBjAG8AbQBtAGUAbgBkAGEAdABpAG8AbgBzAFIAbwB0AGEAdABlAGQAIABmAG8AcgBtAHMASABvAHIAaQB6AG8AbgB0AGEAbAAgAGIAbABvAGMAawAgAHMAcABhAGMAaQBuAGcAVgBlAHIAdABpAGMAYQBsACAAYgBsAG8AYwBrACAAcwBwAGEAYwBpAG4AZwACAAAAAAAA/7UAMgAAAAAAAAAAAAAAAAAAAAAAAAAABCcAAAADACQArQDJAMcArgBiAGMBAgEDAQQAJQAmAGQA/QEFAQYA/wAnAQcAKADLAGUAyADKAQgBCQEKAQsBDAApACoBDQD4AQ4BDwArARAALADPAMwAzQDOAREBEgETARQA+gAtARUALgEWAC8BFwEYARkAMAAxAGYBGgEbARwAMgDTANAA0QCvAGcBHQEeAR8AMwA0ADUBIAEhASIANgEjASQA+wDkASUANwEmAScAOADWANQA1QBoASgBKQEqASsBLAEtADkAOgEuAS8BMAExADsAPADrATIAuwEzAD0BNAE1AOYAkADpAJEA7QE2ATcBOAE5AOIBOgCwATsBPAE9AT4BPwFAAUEBQgFDAUQBRQFGAUcBSAFJAUoBSwFMAU0BTgFPAVABUQFSAVMBVAFVAVYBVwFYAVkBWgFbAVwBXQFeAV8BYAFhAWIBYwFkAWUBZgFnAWgBaQFqAWsBbAFtAW4BbwFwAXEBcgCdAJ4AEwAUABUAFgAXABgAGQAaABsAHABCABAAsgCzAAsADAA+AEAAXgBgAAYACADGAAoABQC2ALcBcwF0ALQAtQDEAMUAvgC/AKkAqgANAIIAwgARAA8AHQAeAKsABACjACIAogASAD8AvABfAOgAIwAJAXUAhgCIAMMAhwF2AXcADgDvAJMAuADwACAAHwAhAJQAlQCnAI8ApABBAGEAmACaAJkAqACfAJsAlwClAJIAuQCcAAcAhACFAL0AlgF4AKYAigCMAIMAiwF5AI0AQwDfANgA4QDbANkA2gCOANwA3QDeAOABegF7AXwBfQF+AX8BgAGBAYIBgwGEAYUBhgGHAYgBiQGKAYsBjAGNAY4BjwGQAZEBkgGTAZQBlQGWAZcBmAGZAZoBmwGcAZ0BngGfAaABoQGiAaMBpAGlAaYBpwGoAakBqgGrAawBrQGuAa8BsAGxAbIBswG0AbUBtgG3AbgBuQG6AbsBvAG9Ab4BvwHAAcEBwgHDAcQBxQHGAccByAHJAcoBywHMAc0BzgHPAdAB0QHSAdMB1AHVAdYB1wHYAdkB2gHbAdwB3QHeAd8B4AHhAeIB4wHkAeUB5gHnAegB6QHqAesB7AHtAe4B7wHwAfEB8gHzAfQB9QH2AfcB+AH5AfoB+wH8Af0B/gH/AgACAQICAgMCBAIFAgYCBwIIAgkCCgILAgwCDQIOAg8CEAIRAhICEwIUAhUCFgIXAhgCGQIaAhsCHAIdAh4CHwIgAiECIgIjAiQCJQImAicCKAIpAioCKwIsAi0CLgIvAjACMQIyAjMCNAI1AjYCNwI4AjkCOgI7AjwCPQI+Aj8CQAJBAkICQwJEAkUCRgJHAkgCSQJKAksCTAJNAk4CTwJQAlECUgJTAlQCVQJWAlcCWAJZAloCWwJcAl0CXgJfAmACYQJiAmMCZAJlAmYCZwJoAmkCagJrAmwCbQJuAm8CcAJxAnICcwJ0AnUCdgJ3AngCeQJ6AnsCfAJ9An4CfwKAAoECggKDAoQChQKGAocCiAKJAooCiwKMAo0CjgKPApACkQKSApMClAKVApYClwKYApkCmgKbApwCnQKeAp8CoAKhAqICowKkAqUCpgKnAqgCqQKqAqsCrAKtAq4CrwKwArECsgKzArQCtQK2ArcCuAK5AroCuwK8Ar0CvgK/AsACwQLCAsMCxALFAsYCxwLIAskCygLLAswCzQLOAs8C0ALRAtIC0wLUAtUC1gLXAtgC2QLaAtsC3ALdAt4C3wLgAuEC4gLjAuQC5QLmAucC6ALpAuoC6wLsAu0C7gLvAvAC8QLyAvMC9AL1AvYARABqAGkAawBtAGwAbgL3AvgC+QBFAEYAbwD+AvoC+wEAAEcC/ABIAHEAcAByAHMC/QL+Av8DAAMBAEkASgMCAPkDAwMEAEsDBQBMAHUAdAB2AHcDBgMHAwgDCQBNAwoATgMLAE8DDAMNAw4AUABRAHgDDwMQAxEAUgB6AHkAewB9AHwDEgMTAxQAUwBUAFUDFQMWAxcAVgMYAxkA/ADlAxoAVwMbAxwAWAB/AH4AgACBAx0DHgMfAyADIQMiAFkAWgMjAyQDJQMmAFsAXADsALoDJwMoAF0DKQMqAOcAiQCgAOoAoQDuAQEDKwDXAywDLQDjAy4AsQMvAPEA8gDzAzAA9AD1APYDMQMyAzMDNAM1AzYDNwM4AzkDOgM7AzwDPQM+Az8DQANBA0IDQwNEA0UDRgNHA0gDSQNKA0sDTANNA04DTwNQA1EDUgNTA1QDVQNWA1cDWANZA1oDWwNcA10DXgNfA2ADYQNiA2MDZANlA2YDZwNoA2kDagNrA2wDbQNuA28DcANxA3IDcwN0A3UDdgN3A3gDeQN6A3sDfAN9A34DfwOAA4EDggODA4QDhQOGA4cDiAOJA4oDiwOMA40DjgOPA5ADkQOSA5MDlAOVA5YDlwOYA5kDmgObA5wDnQOeA58DoAOhA6IDowOkA6UDpgOnA6gDqQOqA6sDrAOtA64DrwOwA7EDsgOzA7QDtQO2A7cDuAO5A7oDuwO8A70DvgO/A8ADwQPCA8MDxAPFA8YDxwPIA8kDygPLA8wDzQPOA88D0APRA9ID0wPUA9UD1gPXA9gD2QPaA9sD3APdA94D3wPgA+ED4gPjA+QD5QPmA+cD6APpA+oD6wPsA+0D7gPvA/AD8QPyA/MD9AP1A/YD9wP4A/kD+gP7A/wD/QP+A/8EAAQBBAIEAwQEBAUEBgQHBAgECQQKBAsEDAQNBA4EDwDAAMEEEAQRBBIEEwQUBBUEFgQXBBgEGQQaBBsEHAQdBB4EHwQgBCEEIgQjBCQEJQQmBCcEKAQpBCoEKwdBbWFjcm9uBkFicmV2ZQdBb2dvbmVrC0NjaXJjdW1mbGV4CkNkb3RhY2NlbnQGRGNhcm9uB0VtYWNyb24GRWJyZXZlCkVkb3RhY2NlbnQHRW9nb25lawZFY2Fyb24LR2NpcmN1bWZsZXgKR2RvdGFjY2VudAxHY29tbWFhY2NlbnQLSGNpcmN1bWZsZXgGSXRpbGRlB0ltYWNyb24GSWJyZXZlB0lvZ29uZWsLSmNpcmN1bWZsZXgMS2NvbW1hYWNjZW50BkxhY3V0ZQxMY29tbWFhY2NlbnQGTGNhcm9uBk5hY3V0ZQxOY29tbWFhY2NlbnQGTmNhcm9uB09tYWNyb24GT2JyZXZlDU9odW5nYXJ1bWxhdXQGUmFjdXRlDFJjb21tYWFjY2VudAZSY2Fyb24GU2FjdXRlC1NjaXJjdW1mbGV4DFNjb21tYWFjY2VudAxUY29tbWFhY2NlbnQGVGNhcm9uBlV0aWxkZQdVbWFjcm9uBlVicmV2ZQVVcmluZw1VaHVuZ2FydW1sYXV0B1VvZ29uZWsLV2NpcmN1bWZsZXgGV2dyYXZlBldhY3V0ZQlXZGllcmVzaXMLWWNpcmN1bWZsZXgGWWdyYXZlBlphY3V0ZQpaZG90YWNjZW50BkRjcm9hdARIYmFyAklKBExkb3QDRW5nBFRiYXIKR2VybWFuZGJscwZBLnNhbHQLQWdyYXZlLnNhbHQLQWFjdXRlLnNhbHQQQWNpcmN1bWZsZXguc2FsdAtBdGlsZGUuc2FsdA5BZGllcmVzaXMuc2FsdApBcmluZy5zYWx0DEFtYWNyb24uc2FsdAtBYnJldmUuc2FsdAxBb2dvbmVrLnNhbHQGRS5zYWx0C0VncmF2ZS5zYWx0C0VhY3V0ZS5zYWx0EEVjaXJjdW1mbGV4LnNhbHQORWRpZXJlc2lzLnNhbHQMRW1hY3Jvbi5zYWx0C0VicmV2ZS5zYWx0D0Vkb3RhY2NlbnQuc2FsdAxFb2dvbmVrLnNhbHQLRWNhcm9uLnNhbHQGSS5zYWx0C0lncmF2ZS5zYWx0C0lhY3V0ZS5zYWx0EEljaXJjdW1mbGV4LnNhbHQOSWRpZXJlc2lzLnNhbHQLSXRpbGRlLnNhbHQMSW1hY3Jvbi5zYWx0C0licmV2ZS5zYWx0DElvZ29uZWsuc2FsdA9JZG90YWNjZW50LnNhbHQGTC5zYWx0C0xhY3V0ZS5zYWx0EUxjb21tYWFjY2VudC5zYWx0C0xjYXJvbi5zYWx0CUxkb3Quc2FsdAtMc2xhc2guc2FsdAZNLnNhbHQGTi5zYWx0C050aWxkZS5zYWx0C05hY3V0ZS5zYWx0EU5jb21tYWFjY2VudC5zYWx0C05jYXJvbi5zYWx0Blcuc2FsdBBXY2lyY3VtZmxleC5zYWx0C1dncmF2ZS5zYWx0C1dhY3V0ZS5zYWx0DldkaWVyZXNpcy5zYWx0Blguc2FsdAZZLnNhbHQLWWFjdXRlLnNhbHQQWWNpcmN1bWZsZXguc2FsdA5ZZGllcmVzaXMuc2FsdAtZZ3JhdmUuc2FsdAdBRS5zYWx0DnF1b3RlbGVmdC5zYWx0D3F1b3RlcmlnaHQuc2FsdA5hbXBlcnNhbmQuc2FsdAZtaW51dGUGc2Vjb25kBEV1cm8HdW5pMjExNwtjb21tYWFjY2VudAdjYXJvbi4yCmFjdXRlLnZlcnQKZ3JhdmUudmVydA5icmV2ZWhvb2thYm92ZQ9jaXJjdW1mbGV4YWN1dGUTY2lyY3VtZmxleGhvb2thYm92ZQpicmV2ZWFjdXRlD2NpcmN1bWZsZXh0aWxkZQpicmV2ZWdyYXZlCmJyZXZldGlsZGUPY2lyY3VtZmxleGdyYXZlCWFycm93bGVmdAdhcnJvd3VwCmFycm93cmlnaHQJYXJyb3dkb3duC2Fycm93dXBsZWZ0DGFycm93dXByaWdodA5hcnJvd2Rvd25yaWdodA1hcnJvd2Rvd25sZWZ0B3VuaTIxQUEHdW5pMjFBQgd1bmkyMUIwB3VuaTIxQjEHdW5pMjFCMgd1bmkyMUIzB3VuaTI2MUEHdW5pMjYxQgdpbmRleHVwCWluZGV4ZG93bgtpbmRleHVwbGVmdAxpbmRleHVwcmlnaHQNaW5kZXhkb3dubGVmdA5pbmRleGRvd25yaWdodAd1bmkyNjFDB3VuaTI2MUQHdW5pMjYxRQd1bmkyNjFGFWluZGV4ZG93bmxlZnQub3V0bGluZRZpbmRleGRvd25yaWdodC5vdXRsaW5lE2luZGV4dXBsZWZ0Lm91dGxpbmUUaW5kZXh1cHJpZ2h0Lm91dGxpbmUMdW5pMjYxQS5zYWx0DHVuaTI2MUIuc2FsdA5pbmRleGRvd24uc2FsdBJpbmRleGRvd25sZWZ0LnNhbHQTaW5kZXhkb3ducmlnaHQuc2FsdAxpbmRleHVwLnNhbHQQaW5kZXh1cGxlZnQuc2FsdBFpbmRleHVwcmlnaHQuc2FsdAx1bmkyNjFDLnNhbHQMdW5pMjYxRC5zYWx0DHVuaTI2MUUuc2FsdAx1bmkyNjFGLnNhbHQaaW5kZXhkb3dubGVmdC5zYWx0X291dGxpbmUbaW5kZXhkb3ducmlnaHQuc2FsdF9vdXRsaW5lGGluZGV4dXBsZWZ0LnNhbHRfb3V0bGluZRlpbmRleHVwcmlnaHQuc2FsdF9vdXRsaW5lB2Vtc3BhY2UHZW5zcGFjZQVibG9jawdibG9jay52B3VuaTI1RDYHdW5pMjVENwl1bmkyNUQ2LnYJdW5pMjVENy52DHVuaTI1RDYuZGVjbwx1bmkyNUQ3LmRlY28OdW5pMjVENi52X2RlY28OdW5pMjVENy52X2RlY28NdW5pMjVENi5iZXZlbA11bmkyNUQ3LmJldmVsD3VuaTI1RDYudl9iZXZlbA91bmkyNUQ3LnZfYmV2ZWwNdW5pMjVENi5zcGlrZQ11bmkyNUQ3LnNwaWtlD3VuaTI1RDYudl9zcGlrZQ91bmkyNUQ3LnZfc3Bpa2UOdW5pMjVENi5zcXVhcmUOdW5pMjVENy5zcXVhcmUQdW5pMjVENi52X3NxdWFyZRB1bmkyNUQ3LnZfc3F1YXJlD3VuaTI1RDYucm91bmRlZA91bmkyNUQ3LnJvdW5kZWQRdW5pMjVENi52X3JvdW5kZWQRdW5pMjVENy52X3JvdW5kZWQVdW5pMkIxQi5zZW1pY2hldnJvbl9lFXVuaTJCMUIuc2VtaWNoZXZyb25fdxV1bmkyQjFCLnNlbWljaGV2cm9uX24VdW5pMkIxQi5zZW1pY2hldnJvbl9zDXVuaTI1RDYud2luZ3MNdW5pMjVENy53aW5ncw91bmkyNUQ2LnZfd2luZ3MPdW5pMjVENy52X3dpbmdzCXVuaTI3QTEudwd1bmkyN0ExCXVuaTI3QTEucwl1bmkyN0ExLm4NdW5pMjFBQi5hcnJvdw11bmkyMUFDLmFycm93D3VuaTIxQUIudl9hcnJvdw91bmkyMUFDLnZfYXJyb3cHdW5pMkIxQgd1bmkyQjI0DHVuaTJCMjQuc2FsdA51bmkyQjI0LnNhbHRfdg11bmkyNURELmN1cnZlD3VuaTI1REQuY3VydmVfdhN1bmkyQjFCLnRyYXBlem9pZF9lFXVuaTJCMUIudHJhcGV6b2lkX2VfdhN1bmkyQjFCLnRyYXBlem9pZF93FXVuaTJCMUIudHJhcGV6b2lkX3dfdgd1bmkyNURDB3VuaTI1REQHdW5pMjVERgd1bmkyNURFEWFycm93bGVmdC5jaGV2cm9uEmFycm93cmlnaHQuY2hldnJvbg9hcnJvd3VwLmNoZXZyb24RYXJyb3dkb3duLmNoZXZyb24RdW5pMkIxQi5jaGV2cm9uX3cRdW5pMkIxQi5jaGV2cm9uX2URdW5pMkIxQi5jaGV2cm9uX24RdW5pMkIxQi5jaGV2cm9uX3MHc3BhY2UudgNBLnYIQWdyYXZlLnYIQWFjdXRlLnYNQWNpcmN1bWZsZXgudghBdGlsZGUudgtBZGllcmVzaXMudgdBcmluZy52CUFtYWNyb24udghBYnJldmUudglBb2dvbmVrLnYDQi52A0MudgpDY2VkaWxsYS52CENhY3V0ZS52DUNjaXJjdW1mbGV4LnYMQ2RvdGFjY2VudC52CENjYXJvbi52A0QudghEY2Fyb24udgNFLnYIRWdyYXZlLnYIRWFjdXRlLnYNRWNpcmN1bWZsZXgudgtFZGllcmVzaXMudglFbWFjcm9uLnYIRWJyZXZlLnYMRWRvdGFjY2VudC52CUVvZ29uZWsudghFY2Fyb24udgNGLnYDRy52DUdjaXJjdW1mbGV4LnYIR2JyZXZlLnYMR2RvdGFjY2VudC52Dkdjb21tYWFjY2VudC52A0gudg1IY2lyY3VtZmxleC52A0kudghJZ3JhdmUudghJYWN1dGUudg1JY2lyY3VtZmxleC52C0lkaWVyZXNpcy52CEl0aWxkZS52CUltYWNyb24udghJYnJldmUudglJb2dvbmVrLnYMSWRvdGFjY2VudC52A0oudg1KY2lyY3VtZmxleC52A0sudg5LY29tbWFhY2NlbnQudgNMLnYITGFjdXRlLnYOTGNvbW1hYWNjZW50LnYITGNhcm9uLnYDTS52A04udghOdGlsZGUudghOYWN1dGUudg5OY29tbWFhY2NlbnQudghOY2Fyb24udgNPLnYIT2dyYXZlLnYIT2FjdXRlLnYNT2NpcmN1bWZsZXgudghPdGlsZGUudgtPZGllcmVzaXMudglPbWFjcm9uLnYIT2JyZXZlLnYPT2h1bmdhcnVtbGF1dC52A1AudgNRLnYDUi52CFJhY3V0ZS52DlJjb21tYWFjY2VudC52CFJjYXJvbi52A1MudghTYWN1dGUudg1TY2lyY3VtZmxleC52ClNjZWRpbGxhLnYIU2Nhcm9uLnYOU2NvbW1hYWNjZW50LnYDVC52DlRjb21tYWFjY2VudC52CFRjYXJvbi52A1UudghVZ3JhdmUudghVYWN1dGUudg1VY2lyY3VtZmxleC52C1VkaWVyZXNpcy52CFV0aWxkZS52CVVtYWNyb24udghVYnJldmUudgdVcmluZy52D1VodW5nYXJ1bWxhdXQudglVb2dvbmVrLnYDVi52A1cudg1XY2lyY3VtZmxleC52CFdncmF2ZS52CFdhY3V0ZS52C1dkaWVyZXNpcy52A1gudgNZLnYIWWFjdXRlLnYNWWNpcmN1bWZsZXgudgtZZGllcmVzaXMudghZZ3JhdmUudgNaLnYIWmFjdXRlLnYMWmRvdGFjY2VudC52CFpjYXJvbi52BEFFLnYFRXRoLnYIT3NsYXNoLnYHVGhvcm4udghEY3JvYXQudgZIYmFyLnYESUoudgZMZG90LnYITHNsYXNoLnYFRW5nLnYET0UudgZUYmFyLnYMR2VybWFuZGJscy52CEEuc2FsdF92DUFncmF2ZS5zYWx0X3YNQWFjdXRlLnNhbHRfdhJBY2lyY3VtZmxleC5zYWx0X3YNQXRpbGRlLnNhbHRfdhBBZGllcmVzaXMuc2FsdF92DEFyaW5nLnNhbHRfdg5BbWFjcm9uLnNhbHRfdg1BYnJldmUuc2FsdF92DkFvZ29uZWsuc2FsdF92CEUuc2FsdF92DUVncmF2ZS5zYWx0X3YNRWFjdXRlLnNhbHRfdhJFY2lyY3VtZmxleC5zYWx0X3YQRWRpZXJlc2lzLnNhbHRfdg5FbWFjcm9uLnNhbHRfdg1FYnJldmUuc2FsdF92EUVkb3RhY2NlbnQuc2FsdF92DkVvZ29uZWsuc2FsdF92DUVjYXJvbi5zYWx0X3YISS5zYWx0X3YKSV9JLnNhbHRfdg1JZ3JhdmUuc2FsdF92DUlhY3V0ZS5zYWx0X3YSSWNpcmN1bWZsZXguc2FsdF92EElkaWVyZXNpcy5zYWx0X3YNSXRpbGRlLnNhbHRfdg5JbWFjcm9uLnNhbHRfdg1JYnJldmUuc2FsdF92DklvZ29uZWsuc2FsdF92EUlkb3RhY2NlbnQuc2FsdF92CEwuc2FsdF92DUxhY3V0ZS5zYWx0X3YTTGNvbW1hYWNjZW50LnNhbHRfdg1MY2Fyb24uc2FsdF92C0xkb3Quc2FsdF92DUxzbGFzaC5zYWx0X3YKTC5zYWx0X3NfdghNLnNhbHRfdghOLnNhbHRfdg1OdGlsZGUuc2FsdF92DU5hY3V0ZS5zYWx0X3YTTmNvbW1hYWNjZW50LnNhbHRfdg1OY2Fyb24uc2FsdF92CFcuc2FsdF92EldjaXJjdW1mbGV4LnNhbHRfdg1XZ3JhdmUuc2FsdF92DVdhY3V0ZS5zYWx0X3YQV2RpZXJlc2lzLnNhbHRfdghYLnNhbHRfdghZLnNhbHRfdg1ZYWN1dGUuc2FsdF92ElljaXJjdW1mbGV4LnNhbHRfdhBZZGllcmVzaXMuc2FsdF92DVlncmF2ZS5zYWx0X3YJQUUuc2FsdF92DWNvbW1hYWNjZW50LnYGemVyby52BW9uZS52BXR3by52B3RocmVlLnYGZm91ci52BmZpdmUudgVzaXgudgdzZXZlbi52B2VpZ2h0LnYGbmluZS52CGh5cGhlbi52CGVuZGFzaC52CGVtZGFzaC52C3BhcmVubGVmdC52DHBhcmVucmlnaHQudg1icmFja2V0bGVmdC52DmJyYWNrZXRyaWdodC52C2JyYWNlbGVmdC52DGJyYWNlcmlnaHQudgtxdW90ZWxlZnQudgxxdW90ZXJpZ2h0LnYOcXVvdGVkYmxsZWZ0LnYPcXVvdGVkYmxyaWdodC52EHF1b3Rlc2luZ2xiYXNlLnYOcXVvdGVkYmxiYXNlLnYPZ3VpbHNpbmdsbGVmdC52EGd1aWxzaW5nbHJpZ2h0LnYPZ3VpbGxlbW90bGVmdC52EGd1aWxsZW1vdHJpZ2h0LnYIcGVyaW9kLnYHY29tbWEudgplbGxpcHNpcy52DGV4Y2xhbWRvd24udg5xdWVzdGlvbmRvd24udghkYWdnZXIudgtkYWdnZXJkYmwudg1wZXJ0aG91c2FuZC52CGV4Y2xhbS52CnF1b3RlZGJsLnYJcGVyY2VudC52C2FtcGVyc2FuZC52EGFtcGVyc2FuZC5zYWx0X3YNcXVvdGVzaW5nbGUudgphc3Rlcmlzay52B2NvbG9uLnYLc2VtaWNvbG9uLnYKcXVlc3Rpb24udhBxdW90ZWxlZnQuc2FsdF92EXF1b3RlcmlnaHQuc2FsdF92BUEuc192BUMuc192BUQuc192BUUuc192BUcuc192BUguc192BUkuc192BUouc192BUsuc192BUwuc192BU4uc192BU8uc192BVIuc192BVMuc192BVQuc192BVUuc192BVcuc192BVkuc192BVouc192CkEuc2FsdF9zX3YKRS5zYWx0X3NfdgpJLnNhbHRfc192Ck4uc2FsdF9zX3YKVy5zYWx0X3NfdgpZLnNhbHRfc192B2FtYWNyb24GYWJyZXZlB2FvZ29uZWsLY2NpcmN1bWZsZXgKY2RvdGFjY2VudAZkY2Fyb24HZW1hY3JvbgZlYnJldmUKZWRvdGFjY2VudAdlb2dvbmVrBmVjYXJvbgtnY2lyY3VtZmxleApnZG90YWNjZW50DGdjb21tYWFjY2VudAtoY2lyY3VtZmxleAZpdGlsZGUHaW1hY3JvbgZpYnJldmUHaW9nb25lawtqY2lyY3VtZmxleAxrY29tbWFhY2NlbnQGbGFjdXRlDGxjb21tYWFjY2VudAZsY2Fyb24GbmFjdXRlDG5jb21tYWFjY2VudAZuY2Fyb24Hb21hY3JvbgZvYnJldmUNb2h1bmdhcnVtbGF1dAZyYWN1dGUMcmNvbW1hYWNjZW50BnJjYXJvbgZzYWN1dGULc2NpcmN1bWZsZXgMc2NvbW1hYWNjZW50DHRjb21tYWFjY2VudAZ0Y2Fyb24GdXRpbGRlB3VtYWNyb24GdWJyZXZlBXVyaW5nDXVodW5nYXJ1bWxhdXQHdW9nb25lawt3Y2lyY3VtZmxleAZ3Z3JhdmUGd2FjdXRlCXdkaWVyZXNpcwt5Y2lyY3VtZmxleAZ5Z3JhdmUGemFjdXRlCnpkb3RhY2NlbnQEaGJhcgJpagRsZG90A2VuZwR0YmFyDGZvdXJzdXBlcmlvcgVTY2h3YQZBY2Fyb24JQWRvdGJlbG93CkFob29rYWJvdmUQQWNpcmN1bWZsZXhhY3V0ZRBBY2lyY3VtZmxleGdyYXZlFEFjaXJjdW1mbGV4aG9va2Fib3ZlEEFjaXJjdW1mbGV4dGlsZGUTQWNpcmN1bWZsZXhkb3RiZWxvdwtBYnJldmVhY3V0ZQtBYnJldmVncmF2ZQ9BYnJldmVob29rYWJvdmULQWJyZXZldGlsZGUOQWJyZXZlZG90YmVsb3cJRGRvdGJlbG93CkRsaW5lYmVsb3cJRWRvdGJlbG93CkVob29rYWJvdmUGRXRpbGRlEEVjaXJjdW1mbGV4YWN1dGUQRWNpcmN1bWZsZXhncmF2ZRRFY2lyY3VtZmxleGhvb2thYm92ZRBFY2lyY3VtZmxleHRpbGRlE0VjaXJjdW1mbGV4ZG90YmVsb3cGR2Nhcm9uB0dtYWNyb24JSGRvdGJlbG93C0hicmV2ZWJlbG93BkljYXJvbgpJaG9va2Fib3ZlCUlkb3RiZWxvdwlMZG90YmVsb3cPTGRvdGJlbG93bWFjcm9uCkxsaW5lYmVsb3cJTWRvdGJlbG93Ck5kb3RhY2NlbnQJTmRvdGJlbG93Ck5saW5lYmVsb3cFT2hvcm4GT2Nhcm9uCU9kb3RiZWxvdwpPaG9va2Fib3ZlEE9jaXJjdW1mbGV4YWN1dGUQT2NpcmN1bWZsZXhncmF2ZRRPY2lyY3VtZmxleGhvb2thYm92ZRBPY2lyY3VtZmxleHRpbGRlE09jaXJjdW1mbGV4ZG90YmVsb3cKT2hvcm5hY3V0ZQpPaG9ybmdyYXZlDk9ob3JuaG9va2Fib3ZlCk9ob3JudGlsZGUNT2hvcm5kb3RiZWxvdwlSZG90YmVsb3cPUmRvdGJlbG93bWFjcm9uClJsaW5lYmVsb3cKU2RvdGFjY2VudAlTZG90YmVsb3cIVGNlZGlsbGEJVGRvdGJlbG93ClRsaW5lYmVsb3cFVWhvcm4GVWNhcm9uD1VkaWVyZXNpc21hY3Jvbg5VZGllcmVzaXNhY3V0ZQ5VZGllcmVzaXNjYXJvbg5VZGllcmVzaXNncmF2ZQlVZG90YmVsb3cKVWhvb2thYm92ZQpVaG9ybmFjdXRlClVob3JuZ3JhdmUOVWhvcm5ob29rYWJvdmUKVWhvcm50aWxkZQ1VaG9ybmRvdGJlbG93Cllkb3RhY2NlbnQJWWRvdGJlbG93Cllob29rYWJvdmUGWXRpbGRlCVpkb3RiZWxvdwVsaXRlcgxrZ3JlZW5sYW5kaWMLbmFwb3N0cm9waGUIZG90bGVzc2oHYXNjcmlwdAVzY2h3YQdnc2NyaXB0BmFjYXJvbglhZG90YmVsb3cKYWhvb2thYm92ZRBhY2lyY3VtZmxleGFjdXRlEGFjaXJjdW1mbGV4Z3JhdmUUYWNpcmN1bWZsZXhob29rYWJvdmUQYWNpcmN1bWZsZXh0aWxkZRNhY2lyY3VtZmxleGRvdGJlbG93C2FicmV2ZWFjdXRlC2FicmV2ZWdyYXZlD2FicmV2ZWhvb2thYm92ZQthYnJldmV0aWxkZQ5hYnJldmVkb3RiZWxvdwlkZG90YmVsb3cKZGxpbmViZWxvdwllZG90YmVsb3cKZWhvb2thYm92ZQZldGlsZGUQZWNpcmN1bWZsZXhhY3V0ZRBlY2lyY3VtZmxleGdyYXZlFGVjaXJjdW1mbGV4aG9va2Fib3ZlEGVjaXJjdW1mbGV4dGlsZGUTZWNpcmN1bWZsZXhkb3RiZWxvdwZnY2Fyb24HZ21hY3JvbgloZG90YmVsb3cLaGJyZXZlYmVsb3cGaWNhcm9uCmlob29rYWJvdmUJaWRvdGJlbG93CWxkb3RiZWxvdw9sZG90YmVsb3dtYWNyb24KbGxpbmViZWxvdwltZG90YmVsb3cKbmRvdGFjY2VudAluZG90YmVsb3cKbmxpbmViZWxvdwVvaG9ybgZvY2Fyb24Jb2RvdGJlbG93Cm9ob29rYWJvdmUQb2NpcmN1bWZsZXhhY3V0ZRBvY2lyY3VtZmxleGdyYXZlFG9jaXJjdW1mbGV4aG9va2Fib3ZlEG9jaXJjdW1mbGV4dGlsZGUTb2NpcmN1bWZsZXhkb3RiZWxvdwpvaG9ybmFjdXRlCm9ob3JuZ3JhdmUOb2hvcm5ob29rYWJvdmUKb2hvcm50aWxkZQ1vaG9ybmRvdGJlbG93CXJkb3RiZWxvdw9yZG90YmVsb3dtYWNyb24KcmxpbmViZWxvdwpzZG90YWNjZW50CXNkb3RiZWxvdwh0Y2VkaWxsYQl0ZG90YmVsb3cKdGxpbmViZWxvdwl0ZGllcmVzaXMFdWhvcm4GdWNhcm9uD3VkaWVyZXNpc21hY3Jvbg51ZGllcmVzaXNhY3V0ZQ51ZGllcmVzaXNjYXJvbg51ZGllcmVzaXNncmF2ZQl1ZG90YmVsb3cKdWhvb2thYm92ZQp1aG9ybmFjdXRlCnVob3JuZ3JhdmUOdWhvcm5ob29rYWJvdmUKdWhvcm50aWxkZQ11aG9ybmRvdGJlbG93Cnlkb3RhY2NlbnQJeWRvdGJlbG93Cnlob29rYWJvdmUGeXRpbGRlCXpkb3RiZWxvdw5jb21tYXR1cm5lZG1vZA1hcG9zdHJvcGhlbW9kDXJpbmdoYWxmcmlnaHQMcmluZ2hhbGZsZWZ0D3ZlcnRpY2FsbGluZW1vZBBmaXJzdHRvbmVjaGluZXNlEXNlY29uZHRvbmVjaGluZXNlEWZvdXJ0aHRvbmVjaGluZXNlEnZlcnRpY2FsbGluZWxvd21vZAhncmF2ZWNtYghhY3V0ZWNtYg1jaXJjdW1mbGV4Y21iCHRpbGRlY21iCW1hY3JvbmNtYghicmV2ZWNtYgxkb3RhY2NlbnRjbWILZGllcmVzaXNjbWIHaG9va2NtYgdyaW5nY21iD2h1bmdhcnVtbGF1dGNtYghjYXJvbmNtYgdob3JuY21iC2RvdGJlbG93Y21iEGRpZXJlc2lzYmVsb3djbWIOY29tbWFhY2NlbnRjbWIKY2VkaWxsYWNtYglvZ29uZWtjbWINYnJldmViZWxvd2NtYg5tYWNyb25iZWxvd2NtYghvbmV0aGlyZAl0d290aGlyZHMJb25lZWlnaHRoDHRocmVlZWlnaHRocwtmaXZlZWlnaHRocwxzZXZlbmVpZ2h0aHMKZmlndXJlZGFzaA1ob3Jpem9udGFsYmFyCWNvbG9uc2lnbgRsaXJhBW5haXJhBnBlc2V0YQRkb25nBHBlc28HZ3VhcmFuaQRjZWRpB3VuaTIxMjAJZXN0aW1hdGVkC2JsYWNrc3F1YXJlDGJsYWNrZGlhbW9uZBd3aGl0ZXVwcG9pbnRpbmd0cmlhbmdsZRl3aGl0ZWRvd25wb2ludGluZ3RyaWFuZ2xlGXdoaXRlbGVmdHBvaW50aW5ndHJpYW5nbGUad2hpdGVyaWdodHBvaW50aW5ndHJpYW5nbGUXYmxhY2t1cHBvaW50aW5ndHJpYW5nbGUZYmxhY2tkb3ducG9pbnRpbmd0cmlhbmdsZRlibGFja2xlZnRwb2ludGluZ3RyaWFuZ2xlGmJsYWNrcmlnaHRwb2ludGluZ3RyaWFuZ2xlC2luZGlhbnJ1cGVlC3R1cmtpc2hsaXJhBXJ1YmxlDHNwYWNlLnRhYl9lbgl6ZXJvLnNpbmYIb25lLnNpbmYIdHdvLnNpbmYKdGhyZWUuc2luZglmb3VyLnNpbmYJZml2ZS5zaW5mCHNpeC5zaW5mCnNldmVuLnNpbmYKZWlnaHQuc2luZgluaW5lLnNpbmYOcGFyZW5sZWZ0LnNpbmYPcGFyZW5yaWdodC5zaW5mBm4uc3Vwcwl6ZXJvLnN1cHMIb25lLnN1cHMIdHdvLnN1cHMKdGhyZWUuc3Vwcwlmb3VyLnN1cHMJZml2ZS5zdXBzCHNpeC5zdXBzCnNldmVuLnN1cHMKZWlnaHQuc3VwcwluaW5lLnN1cHMOcGFyZW5sZWZ0LnN1cHMPcGFyZW5yaWdodC5zdXBzEHBlcmlvZGNlbnRlcmVkLnYTY29tbWF0dXJuZWRhYm92ZWNtYgABAAH//wAPAAEAAgAOAAAAAAAAAxIAAgCAAAIABwABAAkACgABAAwADQABAA8AHAABAB4AIwABACUALgABADAAMwABADUANgABADkAPAABAD4ASwABAE0AUAABAFIAUgABAFQAVAABAFYAYAABAGIAcQABAH0AfQABAH8AhAABAIYAhwABAIkAkAABAJIAmgABAJwAnAABAJ4AngABAKEAoQABAKMApgABAKgAswABALUAtwABARABEAABASkBKQADAacBqwABAa0BrgABAbMBtgABAbgBuAABAboBwAABAcIBwgABAcQBxwABAcoBygABAcwB0gABAdQB1AABAdYB1gABAdoB2gABAd8B4AABAeIB4gABAeQB6wABAe8B7wABAfEB8QABAfMB9AABAfYB9gABAfoB+gABAfwCBAABAgcCEQABAhMCFQABAiMCKAABAioCKwABAi4CNAABAjYCNwABAjkCPwABAkECQQABAkMCQwABAkYCRgABAkoCTAABAk4CTgABAlACUwABAlUCWQABAlwCXAABAqYCqwABAq0CrgABArACsQABArMCwAABAsICxwABAskC0gABAtQC1gABAtgC2QABAtwC3wABAuEC7gABAvAC8wABAvUC9QABAvcC9wABAvkDAwABAwUDFAABAxwDHAABAyIDIgABAysDKwABAzIDMgABAzkDOQABAzwDPAABA0IDQwABA0YDRgABA0kDSgABA00DTQABA1EDUQABA1kDWgABA1wDXAABA18DXwABA2EDYQABA2UDZQABA2cDaAABA2oDagABA24DbwABA3EDcQABA3MDcwABA3YDdgABA3kDeQABA3sDewABA38DfwABA4YDhgABA40DjQABA5ADkAABA5YDlwABA5oDmgABA50DngABA6EDoQABA6UDpQABA60DrgABA7ADsAABA7MDswABA7UDtQABA7kDugABA7wDvQABA78DvwABA8MDxAABA8YDxgABA8gDyAABA8sDywABA9ID1AABA9YD4QADA+MD5AADA+YD6QADBCYEJgADAAEAAQAAAAgAAgADASkBKQAAA9YD4QABBCYEJgANAAEAAAAKACoAGAACREZMVABGbGF0bgCCAAgA+gCsAEwAVgBgADwARABqAAZrZXJuAIptYXJrAJJta21rAHJzczExAHhzczEyAH52a3JuAIQBLAAAAAQAAAABAToABAAAAAEBPgACAAAAAgFWEMAAAgAIAAIIWAtSAAIACAACAugBYgAGABAAAQEkAAAA8AACQ0FUIADwUk9NIADwAAAAAQAHARAAAQAAAQ4AAQABAAAAAQACAAAAAgAEAAMAAAACAAUABgABAAAAJATqAT4BSAFSAVwBZgFwAXoBhAGOAZgBogGsAbYBwAHKAdQB3gHoAfIB/AIGAhACGgIkAi4COAJCAkwCVgJgAmoCdAJ+AogCkgABAAAAMgKyBhgCvALGAtAC2gLkAu4C+AMCAwwDFgMgAyoDNAM+A0gDUgNcA2YDcAN6A4QDjgOYA6IDrAO2A8ADygPUA94D6APyA/wEBgQQBBoEJAQuBDgEQgRMBFYEYARqBHQEfgSIBJIAAP//AAYAAAABAAIAAwAEAAUAAR8qH+QAASCcH7AAAR7CLDoAASAOMMQAAR62HqYAASACHswAAAEJAAABCgABH1gACAAAAAse1h7QIrIe0B7gICge4B7qHvQfJB82AAIfKAAEAAAfUiAuAAMABAAAAAD/zv+6AAD/zgAAAAAAAP+6AAAAAAABIigACv97AQkAASI0AAr/hgD0AAEiQAAK/zgBkAABIboACv4vA6IAASHEAAr/MAGgAAEhzgAK/34BBAABIdgACv8rAaoAASFcAAr/fgEDAAEhZAAK/4EA/gABIWwACv+CAPwAASDeAAr+eQMNAAEg5AAK/3wBCAABIOoACv+DAPkAASDwAAr/LQGlAAEg9gAK/ysBqQABIPwACv91ARUAASB4AAr/NAGYAAEgfAAK/xwByAABIIAACv8ZAc0AASAeAAr/dgETAAEgIAAK/4oA7AABICIACv8lAbYAASAkAAr/eAEPAAEfiAAK/lYDUwABIBwACv8XAdIAAR9+AAr/eAEQAAEffgAK/6AAvwABH34ACv9zARkAAR9+AAr/JwGxAAEffgAK/3YBFAABH34ACv96AQwAAR9+AAr/LgGkAAEffgAK/x8BwgABH34ACv8XAdEAAR9+AAr/JAG4AAEnYgAEAAAALSGSIVwodiKYJpghVibaJAgnuiFcIaAhoCGgIWIhYiGuIbwjRCNaIa4hvCHKIcoiqiKqIX4kKiQqIdghaCHmIXQhdCFoIWgivCK8IrwivCK8IfQhbiF+IYgizgABJgAABQCMARgAASeqAAUBCwIWAAEljAAFARMCJgABJpoABQEQAh8AASPAAAUBOQJyAAEkRAAFAYYDDAABJFwABQFSAqMAASWIAAUBOwJ2AAEivAAFAoAFAAABJMwABQEgAj8AASUSAAUBJQJJAAEk4AAFAQgCDwABJIgABQE4AnAAASRaAAUBBgIMAAEkLgAFAUYCjAABI24ABQEeAjwAASOAAAUBDQIZAAEjrgAFARECIgABI4gABQELAhUAASLMAAUBBQIJAAEiVAAFAOEBwQABIqAABQE2AmwAASDCAAUBEAIgAAEgwgAFAT8CfQABIMIABQHHA40AASJkAAUB0QOiAAEiSAAFAcADgAABIh4ABQEoAlAAASIkAAUAaQDSAAEhogAFASsCVgABIJAABQFNApkAASCQAAUBHwI+AAEhkgAFARsCNgABITIABQDYAa8AASB8AAUBqgNTAAEhKgAFAc4DnAABISwABQHTA6UAASEuAAX/5P/JAAEhMAAFARsCNQABITIABQHZA7EAASBKAAUBJgJMAAEgSgAFASoCVAABIEoABQEZAjIAASBKAAUAzwGdAAEgSgAFAWgC0AABIEoABQGcAzcAASBKAAUBjgMbAAEgSgAFAY4DHAABIEoABQF4AvAAAiaaAAoAXf74Ag/++AIP/pgC0P6YAtD+xQJ2/sUCdv9CAXz/QgF8/sUCdf7FAnX/2ABQ/9gAUABO/2UATv9l/fIEG/8oAa//eQEN/3EBHv9YAU//LgGj/0QBd/+FAPb/ggD7/3cBEf9hAT3/LAGo/4UA9v+CAPv/fQEG/3cBEf9hAT3/KAGw/5oAy/8xAZ3/eQEO/6kArv9TAVr/owC6/0QBd/+jALr/dQEW/30BBf95AQ7/0QBd/6kArv9gAT//KAGv/zoBjP8pAa7/UQFe/3EBHv9dAUX/XQFF/3ABH/9rASr/fQEF/1UBVv9vASH/mgDL/zEBnf85AY7/bQEl/zkBjv+DAPr/gwD6/hoDy/8sAaf+UgNc/u8CIv+3AJL+YwM5/mMDOf6ZAs3+mQLN/xYB1P8WAdT+WQNN/lkDTf86AYz/PQGG/osC6f89AYb/IQG+/oMC+f7zAhr/CAHw/iwDqP4sA6j/FAHX/xMB2f8RAd7/CwHq/xAB3wACJdwABQBlAhAEHwEWAisBSwKWAIoBEwD7AfUBDAIYAIUBCQFIAo8AhgELAXwC+AF6AvMBFQIpAVQCpwFBAoEBQgKDAR4COwE9AnkBJgJLAUcCjQEdAjkBJgJLAa4DXABJAJIBnQM5AZ0DOQEJAhIAfQD5/7v/dwE9AnoB5gPMAeYDzAFnAs0BZwLNAOoB1ADqAdQAVQCqAawDWAGtA1kB4gPDAQECAgFEAogBygOUAaMDRQEzAmYA/AH3ARgCLwEcAjcBDgIbAMkBkgETAiUBkwMmAOYBywEhAkEBPAJ4AWECwgC9AXkBjwMdAW8C3gFvAt4AvgF8AL4BfP/n/87/5//OARYCKwFLApYAigETAPsB9QEMAhgAhQEJAYIDBAA8AHcAJwBNACIAQwE8AncB5APIAeQDyAA4AG8AOABvADAAYAAsAFcAJwBNAEYAiwBJAJIBHAI4ARwCOAC9AXkBTgKbAB0AOf/v/98BagLUAXwC+AGKAxMBeALvAZIDIwFzAuUBYQLCAWoC1AGCAwQBigMTAZIDIwFzAuYAAS6wAAQAAAF4MaoopCikKKQopCikKKQopCikKKQopCjcKAYoBigGKAYoBigGKBAoECgGKAYoBigGKAYoBigGKAYoBigGKGYpGCkYKRgpGCkYJ/on+if6J/on+if6J/on+if6J/ooACgAKPoo+il2KXYpdigQKBAoECgQKBAoECgQKBAoECg8KBApNik2KTYpNigaKBooGigaKBooGiiOKI4ojigAKAAoACgAKAAoACgAKAAoACgAKAAoSif0J/Qn9Cf0J/QovihYKFgoWChYKFgoJCgkKCQoJCgGKBAoECh4KBAoACl2KAYo3CgGKAYoBigGKAYoBigGKAYoBigGKVQpVClUKVQoACgAKAAoACgAKL4oLiguKC4oLiguKAYvkjMQMJws2jSmNugtZC3uKKQopCikKKQopCikKKQopCikKKQo3CgGKAYoBigGKAYoBigQKBAoBigGKAYoBigGKAYoBigGKAYoBihmKRgpGCkYKRgpGCf6J/on+if6J/on+if6J/on+igAKAAo+ij6KXYpdil2KBAoECgQKBAoECgQKBAoECgQKDwoECk2KTYpNik2KBooGigaKBooGigaKI4ojiiOKAAoACgAKAAoACgAKAAoACgAKAAoAChKJ/Qn9Cf0J/Qn9Ci+KFgoWChYKFgoWCgkKCQoJCgkKNwoBigQKBAoeCgQJ/ooBiikKKQopCikKKQopCikKKQopCikKKQopCikKBAoECgGKAYoBigGKAYoBigGKAYpGCkYJ/on+if6KXYpdil2KBAoECgQKBAoECgQKBAoECk2KTYpNigaKBoojiiOKAAoACgAKAAoACgAKAAoWChYKFgoWCgkKPooACikKKQopCikKKQopCikKKQopCikKKQopCikKBAoECgGKAYoBigGKAYoBigGKAYpGCkYJ/on+if6KXYpdil2KBAoECgQKBAoECgQKBAoECk2KTYpNigaKBoojiiOKI4oACgAKAAoACgAKAAoAChYKFgoWChYKCQAAjbcAAQAADl+N6wAHwAWAAD/+wAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAP/sAAAAAP/sAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA//sAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAP/nAAD/2AAAAAAAAP/2AAAAAP/2AAAAAAAA//b/9v/2AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAP/sAAAAAP/sAAAAAAAAAAAAAAAAAAD/5wAA//sAAAAAAAAAAP/2/84AAP/s//YAAP/O//b/9gAAAAAAAAAAAAAAAAAAAAAAAP/7AAD/9gAAAAAAAAAAAAAAAAAAAAAAAAAA//sAAAAAAAAAAAAAAAAAAAAA//b/+//2AAAAAAAA//sAAAAA//sAAAAAAAAAAP/2//YAAAAAAAAAAAAAAAD/4gAAAAAAAAAAAAD/9gAAAAD/+wAAAAAAAP/2//b/8QAA//sAAAAAAAAAAP/iAAD/4v/7AAAAAP/xAAAAAP/2AAD/+wAA//H/8f/sAAAAAAAAAAAAAAAA/84AAP+6//YAAAAA/+cAAAAA/+cAAAAAAAD/5//s/+IAAP/7AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA/+wAAAAA/+wAAAAAAAAAAAAA//sAAP/YAAD/9gAAAAAAAAAA//b/pgAA//H/2AAA/7r/4gAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAD/9gAAAAAAAAAAAAAAAAAAAAAAAAAAAAD/9gAA//YAAP/7//b/9gAA/+z/+wAAAAAAAAAAAAD/9gAAAAAAAAAAAAAAAP/sAAD/5wAAAAAAAP/2AAAAAP/7AAD/9gAA//b/9v/2AAAAAAAA//YAAAAAAAAAAAAAAAD/9v/2AAD/9gAAAAD/2P/2AAAAAAAAAAAAAAAAAAAAAAAAAAD/7AAA/+cAAAAAAAD/8QAAAAD/+wAA//sAAP/x//H/8QAA//v/9gAAAAAAAP+w//v/nP/nAAD/+/+/AAAAAP/OAAAAAAAA/5f/iP+IAAAAAAAAAAAAAAAA/+wAAP/xAAAAAAAA//YAAAAA//sAAP/2AAD/9v/2//YAAAAAAAAAAP/sAAD/9gAA/9gAAP/sAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA//sAAP/dAAD/9gAAAAAAAAAAAAD/xAAA/+z/7AAA/+L/7P/2AAAAAAAAAAAAAAAA//YAAAAAAAAAAAAAAAD/9gAAAAAAAAAAAAD/7AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAD/+wAAAAAAAP/2AAAAAAAAAAAAAAAAAAAAAP/2AAAAAAAAAAAAAAAA//v/5wAA//sAAAAA/+IAAAAAAAAAAAAAAAAAAAAAAAAAAAAA/84AAP+6//YAAAAA/9gAAAAA/+IAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAD/9gAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA/+wAAP/2AAD/4gAAAAAAAP/2//YAAAAAAAAAAAAAAAAAAAAAAAAAAAAA//YAAP/7AAAAAAAAAAAAAP/nAAD/9gAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAD/zgAA/7r/9gAAAAD/zgAAAAD/4gAAAAAAAAAAAAAAAAAAAAAAAP/2AAAAAAAAAAAAAAAA//b/7AAA//YAAAAAAAAAAAAAAAAAAAAAAAAAAAAA//EAAP/7AAD/9gAAAAD/9v/nAAD/8QAAAAAAAAAAAAAAAAAAAAAAAjZGAAgAADccOXIAKgAuAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAD/+wAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAP/7AAD/+wAAAAD/+wAAAAD/+//xAAAAAAAAAAAAAAAA/+wAAP/x//YAAAAAAAAAAAAAAAAAAP/x//b/9gAAAAAAAAAA//YAAAAAAAAAAP/2//YAAP/2//YAAAAAAAAAAAAAAAAAAAAAAAAAAAAA//YAAAAAAAAAAAAAAAD/9gAA//b/+wAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA//b/9gAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAD/9gAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA//YAAAAAAAAAAAAAAAAAAAAAAAD/7P/2AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAP/2AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA//YAAAAAAAAAAAAAAAAAAAAA//YAAAAAAAAAAAAAAAAAAAAAAAAAAP/2AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAD/9gAAAAAAAAAAAAAABQAAAAAAAAAAAAAAAAAAAAAAAAAAAAoAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAD/9v/2AAAAAAAAAAAAAAAAAAAAAP/7AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAP/2//YAAAAA/5IAAAAAAAD/9gAA//sAAAAAAAAAAAAAAAAAAAAA//YAAAAAAAAAAP/YAAAAAAAAAAAAAAAAAAAAAAAA/37/fgAAAAAAAAAAAAAAAAAAAAAABQAAAAAAAAAAAAD/8QAAAAAAAAAAAAoAAP/sAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA//YAAAAAAAAAAAAAAAAAAAAAAAD/7P/sAAAAAAAAAAAAAAAA//b/9v/2AAD/9gAA//b/9v/2//YAAP/sAAD/9v/sAAAAAP/2AAAAAAAAAAAAAAAA/+z/7AAAAAD/9gAAAAAAAAAAAAAAAAAA//b/9gAAAAAAAAAAAAD/9gAAAAAAAAAAAAAAAAAAAAAAAAAA//YAAAAAAAAAAAAAAAAAAAAA//b/9gAAAAAAAAAAAAAAAAAAAAAAAP/2AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAD/9gAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAABQAAAAoAAP/2AAD/9gAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAP/7AAAAAAAAAAAAAAAAAAAAAP/7AAAAAAAAAAAAAAAAAAAAAAAAAAD/+wAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA//sAAAAAAAAAAAAAAAAAAAAA//sAAAAAAAAAAAAAAAAAAAAAAAAAAP/7AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAD/9gAAAAAAAAAAAAAAAAAAAAD/9v/2AAAAAAAAAAAAAAAAAAAAAAAA//YAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAD/9gAAAAAAAP/iAAAAAAAA//YAAAAA/+IAAP/7AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAP/O/8QAAAAAAAAAAAAAAAAAAP/s//b/9gAA//b/9gAA//YAAAAAAAD/8f/7//v/9v/2/34AAP/7//b/+//2AAAAAAAAAAD/4gAA/+z/9v/x//v/4v/2//YAAAAAAAAAAP/2AAD/9gAAAAAAAAAAAAD/+wAAAAD/+//7AAAAAAAAAAAAAAAAAAD/9gAA//YAAAAAAAD/9gAAAAAAAAAAAAAAAAAAAAAAAAAA//YAAAAAAAD/9gAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAP/iAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAP/s//b/9gAA//b/9gAA//YAAAAAAAD/8QAA//v/9v/2/37/+//7//b/+//2AAD/xP/2AAD/4gAA/+z/9v/xAAD/4v/2//YAAAAAAAAAAP/2AAD/9gAAAAD/+wAAAAAAAAAAAAAAAAAAAAD/9gAAAAAAAAAAAAAAAP/iAAD/9v/sAAAAAAAAAAAAAAAAAAD/+wAAAAAAAAAAAAAAAP/2AAAAAAAAAAD/7P/sAAD/9gAAAAAAAAAAAAD/7P/2//b/+//7AAAAAP/7AAAAAAAA//EAAP/7//b/9v+mAAD/+//2//v/9gAA/9j/9gAA/+IAAP/s//v/9v/2//b/9v/7AAAAAAAAAAD/9gAA//YAAAAAAAAAAAAAAAAAAAAAAAAAAAAA//sAAAAAAAAAAAAAAAAAAAAA//H/9gAAAAAAAAAAAAAAAAAAAAAAAP/xAAAAAAAAAAAAAAAAAAAAAAAA//b/9gAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAD/7AAAAAAAAAAAAAAAAAAAAAD/9gAAAAAAAAAAAAAAAAAAAAAAAAAA/+wAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAP/7AAAAAAAAAAAAAAAAAAAAAP/7AAAAAAAAAAAAAAAAAAAAAAAAAAD/+wAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA//EAAAAAAAAAAAAAAAAAAAAA//H/9gAAAAAAAAAAAAAAAAAAAAAAAP/2AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAD/+wAAAAAAAAAAAAAAAAAAAAD/9gAAAAAAAAAAAAAAAAAAAAAAAAAA//YAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAP/7AAAAAAAAAAAAAAAAAAAAAP/2AAAAAAAAAAAAAAAAAAAAAP/2//YAAAAAAAAAAAAAAAAAAAAAAAD/9gAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA//sAAAAAAAAAAAAAAAAAAAAA//b/9gAAAAAAAAAAAAAAAAAAAAAAAP/7AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAP/2AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAP/2AAAAAAAAAAAAAAAAAAAAAP/2//YAAAAAAAAAAAAAAAAAAAAAAAD/+wAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA//YAAAAA/5wAAAAAAAAAAAAAAAD/9v/2AAAAAAAA//YAAAAAAAAAAAAAAAAAAP/OAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAP/2AAAAAAAAAAAAAAAAAAAAAAAAAAD/+wAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAD/4v/s/+wAAAAA//YAAAAAAAAAAP/2AAAAAP/2AAAAAP9gAAAAAAAAAAD/9gAA/7r/7P/2/+IAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAD/9gAAAAAAAP/i/+z/7AAAAAD/7AAA//sAAP/2/+z/9v/2/+wAAAAA/2AAAAAAAAAAAP/sAAD/sP/s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ABIBEQKxArICswK0ArUCtgPyA/kAAQAQAHMAdgMXAxoDZgNuA28DcANxA3IDuwPDA8QDxQPGA8cAAQARAFQAVQBWAH0A5gDnAvcC+AL5AyIDYwNkA2UDtwO4A7kDugACAAYAaQBtAAAAegB6AAUDDAMQAAYDHwMfAAsDcwN2AAwDyAPLABAAAQASADoAOwA8AD0APgLdAt4C3wLgAuEDTQNOA08DegOhA6IDowP0AAEAEwA1ADYANwA4AHkBEgLYAtkC2gLbAx4DSQNKA0sDnQOeA58D8wQHAAIABwACAAsAAABiAGIACgEIAQgACwKmAq8ADAMFAwUAFgMrAzcAFwN/A4sAJAABABcATgBPAFAAUQBSAFMA8AEHARABfwGAAYcBiALxAvIC8wL0AvUC9gNhA2IDtQO2AAIACAAAAAAAAAE1AWMAAQFlAWUAMAGBAYIAMQGJAYwAMwGlAqUANwP8BAUBOAQLBAsBQgAQALv/9gC+//YAzP/iAM3/4gDO/+wAz//sAND/7ADR/+wA0v/YANP/4gDU/+wA1f/sAPT/7AD1/+wA/P/sARn/7AAQALr/+wC7//YAvv/xAMz/4gDN/+IAzv/2AM//9gDQ//YA0f/2ANL/4gDT/+IA1P/2ANX/9gDm//YA9P/2APX/9gACAAsAPwBHAAAASQBJAAkAaABoAAoAdAB0AAsArgCuAAwC4gLqAA0C7ALsABYDCwMLABcDGAMYABgDUQNYABkDpQOsACEAAgAOAAEAAQAAALcAugABALwAwAAFAMIAxAAKAM4A1wANANkA2QAXANsA3AAYAN8A4AAaAOcA6QAcAPIA9wAfAPkA+wAlAP0A/QAoARUBFQApARcBGQAqABcAuv/2ALv/9gC+//YAzP/iAM3/4gDO//YAz//2AND/9gDR//YA0v/iANP/4gDU//YA1f/2AOb/9gDp/+wA9P/2APX/9gD2//YA9//2APn/9gD6//YA+//2ARn/7AACAA8AEwAUAAAAMwA0AAIAVwBhAAQAewB7AA8ApACoABACtwK4ABUC1gLXABcC+gMEABkDIAMgACQDOAM5ACUDZwNtACcDeQN5AC4DfAN8AC8DjAONADADvAPCADIAHAC7/+IAwv/YAMP/2ADE/9gAzP/EAM3/xADO/84Az//OAND/zgDR/84A0v+6ANP/ugDU/84A1f/OANj/2ADa/9gA3P/sAPL/7ADz/+wA9P/OAPX/zgD2/+wA9//sAPn/7AD6/+wA+//sAPz/4gEZ/8QAAQBdAWkBagFtAW4BgQGCAYUBhgGJAYoBjQGOAZ8BoAGlAaYBrAGtAa8BsAGyAbwBvQG+AcEBwwHOAc8B0AHRAdMB1QHbAdwB5wHrAe0B8AH1AfcB+QH6AgACAwIEAgUCBgIYAhkCHwIqAiwCNQI9Aj4CPwJAAkECRAJFAkkCTQJPAlECUgJbAmMCZgJnAmgCbQJuAnUCdgJ3AngCeQJ7An8CgAKCAoMChAKGAocCiAKLAowCjQKUAp4CogKlAAEAZQABAAwAHwByAHcAeAB8AKIAtAC1ALYAtwC4ALkAugC7ALwAvQC+AL8AwADCAMQAyQDKAMsAzADNAM8A0gDTANgA2QDaANsA4wDkAOUA6gDuAO8A8gDzAPUBCQEKAQsBDAENAQ4BDwETARQBFQEWARgBGQFnAWgBgwGEAZ0BngKwAsMDFgMbAx0DIQMmAycDKAMpA3gDzwPQA+oD6wPsA+0D7gPvA/ED9QP3A/oEBgQJBAoEDAQQBBEEEgQTBBQEGAQZBB0EHgQgBCEAAgB7AAIABwAAAAkACgAGAAwADQAIAA8AHAAKAB4AIwAYACUALgAeADAAMwAoADUANgAsADkAPAAuAD4ASwAyAE0AUABAAFIAUgBEAFQAVABFAFYAYABGAGIAcQBRAH0AfQBhAH8AhABiAIYAhwBoAIkAkABqAJIAmgByAJwAnAB7AJ4AngB8AKEAoQB9AKMApgB+AKgAswCCALUAtwCOARABEACRAacBqwCSAa0BrgCXAbMBtgCZAbgBuACdAboBwACeAcIBwgClAcQBxwCmAcoBygCqAcwB0gCrAdQB1ACyAdYB1gCzAdoB2gC0Ad8B4AC1AeIB4gC3AeQB6wC4Ae8B7wDAAfEB8QDBAfMB9ADCAfYB9gDEAfoB+gDFAfwCBADGAgcCEQDPAhMCFQDaAiMCKADdAioCKwDjAi4CNADlAjYCNwDsAjkCPwDuAkECQQD1AkMCQwD2AkYCRgD3AkoCTAD4Ak4CTgD7AlACUwD8AlUCWQEAAlwCXAEFAqYCqwEGAq0CrgEMArACsQEOArMCwAEQAsICxwEeAskC0gEkAtQC1gEuAtgC2QExAtwC3wEzAuEC7gE3AvAC8wFFAvUC9QFJAvcC9wFKAvkDAwFLAwUDFAFWAxwDHAFmAyIDIgFnAysDKwFoAzIDMgFpAzkDOQFqAzwDPAFrA0IDQwFsA0YDRgFuA0kDSgFvA00DTQFxA1EDUQFyA1kDWgFzA1wDXAF1A18DXwF2A2EDYQF3A2UDZQF4A2cDaAF5A2oDagF7A24DbwF8A3EDcQF+A3MDcwF/A3YDdgGAA3kDeQGBA3sDewGCA38DfwGDA4YDhgGEA40DjQGFA5ADkAGGA5YDlwGHA5oDmgGJA50DngGKA6EDoQGMA6UDpQGNA60DrgGOA7ADsAGQA7MDswGRA7UDtQGSA7kDugGTA7wDvQGVA78DvwGXA8MDxAGYA8YDxgGaA8gDyAGbA8sDywGcA9ID1AGdAAEA6P/7AAEA8v/sAAEA6P/2AAIA3P/2APL/7AACAOj/9gDp//YAAgDS//YA0//2AAIA0//2APL/9gADAAH/+wDo/+cA7v/xAAMAAf/2AOj/8QDp//sAAwAB//sA6P/2AO7/9gADAAH/9gDo//EA7v/sAAQAAf/2AOj/3QDu/+wA8v/sAAUAxv/sAOb/9gDo//EA6f/sARj/7AAFAAH/9gDc//YA6P/YAO7/4gDy/+wABgAB//sA0v/YANP/2ADc//YA5v/2AOn/9gAHANL/7ADT/+wA3P/2AOb/9gDp//YBF//2ARj/9gAHANL/0wDT/90A3P/2AOb/9gDp/+wBF//2ARj/7AAHANL/3QDT/+IA3P/2AOb/9gDp//YBF//2ARj/9gAHANL/2ADT/+cA3P/2AOb/7ADp//YBF//2ARj/7AAHANL/2ADT/84A3P/2AOb/9gDp/+wBF//2ARj/7AAIAAH/7ADS/0wA0/9MANz/2ADm/9gA6f/iARf/2AEY/7AACAAB//YA0v9qANP/agDc//YA5v/sAOn/4gEX//YBGP/OAaAf2h5CHkgeTh5UHloeYB5mHoQehB5sHnIeeB5+H9ogrB6EHooekB6WHpweoh6oHq4etCAiHwgeuh7AHsYezB7SIDQe2B7eHuQe6h7wHvYe/By8IEYfAiBAHwgfDh8UHxofIB8mHywfaB8yHzgfPh9EH0ofUB9WH1wfYh9oH24fdB96H4Afhh+MH5IgOh+YH54fpB+qH7Afth+8H8IfyB/OH9Qf2h/gH+Yf7B/yH/gf/iAEIAogFiAQIBwgIiAoIJogLiA6H/4fMhzCHz4fRB9KH1AfViAiHMgekBzOHNQc2hzgHOYc7BzyHPIc8hz4HP4dBB0KHRAdFh8OHRwdIh+eH7wfqiCsHSIdKB0uHTQdOh/+HUAdRh1MHVIdWB1eHWQdah+AHXAddh18HfQdgh2IHY4dyh2UHZodoB4YHjYeJB4qHjAd9B36HgAeGB2mHiod+h4AHioeNh4kHioeMB4SHfQd+h4AHaweBh4SHiQeGB42HiQeKh4SHjAd9B36HbIduB4YHiQeKh4YHhgeNh3iHioeMB4SHfQd+h2+HcQePB4qHjYdyh3QHdYgBB3iHiod3B42HeIeAB3oHe4eNh4kHioeEh4wHfQd+h42HiQeKh4wHfQd+h4AHhgd7h42HiQeKh4wHhId9B36HgAeBh4MIEYeEh4kHhgeKh42HiQeMB4eHiQeKh4wHjYePB/aHkIeSB5OHlQeWh5gHmYehB6EHmwech54Hn4f2iCsHoQeih6QHpYenB6iHqgerh60ICIfCB66HsAexh7MHtIgNB7YHt4e5B7qHvAe9h78IEYfAiBAHwgfDh8UHxofIB8mHywfaB8yHzgfPh9EH0ofUB9WH1wfYh9oH24fdB96H4Afhh+MH5IgOh+YH54fpB+qH7Afth+8H8IfyB/OH9Qf2h/gH+Yf7B/yH/gf/iAEIAogECAWIBwgIiAoIJogLiA0IDogTCBSIFggXiBkIGogcCB2IHYgfCCCIL4giCCOIJQgmiCgIKwgsiC4IL4gxCDKINAg1iBAIEYgTCBSIFggXiBkIGogcCB2IHYgfCCCIL4giCCOIJQgmiCgIKYgrCCyILggviDEIMog0CDWINwg4iDoACIAVP/sAFX/7ABW/+wAaf/2AGr/9gBr//YAbP/2AG3/9gCv//YAsP/2ALH/9gCy//YAs//2Avf/7AL4/+wC+f/sAwz/9gMN//YDDv/2Aw//9gMQ//YDZP/sA2X/7ANz//YDdP/2A3X/9gN2//YDuP/sA7n/7AO6/+wDyP/2A8n/9gPK//YDy//2ACIAVP/OAFX/zgBW/84Aaf/sAGr/7ABr/+wAbP/sAG3/7ACv//YAsP/2ALH/9gCy//YAs//2Avf/zgL4/84C+f/OAwz/7AMN/+wDDv/sAw//7AMQ/+wDZP/OA2X/zgNz/+wDdP/sA3X/7AN2/+wDuP/OA7n/zgO6/84DyP/sA8n/7APK/+wDy//sADAAJ//sACj/7AAp/+wAKv/sACv/7AAs/+wALf/sAC7/7AAv/+wAMP/sAFT/7ABV/+wAVv/sAG7/9gBv//YAcP/2AHH/9gB4/+wCy//sAsz/7ALN/+wCzv/sAs//7ALQ/+wC0f/sAtL/7ALT/+wC9//sAvj/7AL5/+wDEf/2AxL/9gMT//YDFP/2Axz/7ANG/+wDR//sA0j/7ANk/+wDZf/sA3f/9gOa/+wDm//sA5z/7AO4/+wDuf/sA7r/7APM//YAAgAlAAEAJAAAACcANwAkAD8AdgA1AHgAeABtAHoAegBuAHwAfABvAH4AfgBwAIkAkgBxAJ0AnwB7AKIAogB+AKkAtAB/ANIA0wCLANwA3ACNAOcA6QCOAO4A7gCRAPIA8gCSAqYCyACTAssC2gC2AuIDGgDGAxwDHAD/AyEDIQEAAysDQwEBA0YDSwEaA1EDWAEgA14DYgEoA2QDZQEtA2cDbQEvA3MDdwE2A3kDeQE7A3sDewE8A38DlwE9A5oDnwFWA6UDrAFcA7IDtgFkA7gDugFpA7wDwgFsA8gDzAFzAEIAAv/YAAP/2AAE/9gABf/YAAb/2AAH/9gACP/YAAn/2AAK/9gAC//YADH/qwAy/6sAaP/sAG7/9gBv//YAcP/2AHH/9gBy/9gArv/sAqb/2AKn/9gCqP/YAqn/2AKq/9gCq//YAqz/2AKt/9gCrv/YAq//2ALU/6sC1f+rAwv/7AMR//YDEv/2AxP/9gMU//YDFv/YAyv/2AMs/9gDLf/YAy7/2AMv/9gDMP/YAzH/2AMy/9gDM//YAzT/2AM1/9gDNv/YAzf/2AN3//YDe/+rA3//2AOA/9gDgf/YA4L/2AOD/9gDhP/YA4X/2AOG/9gDh//YA4j/2AOJ/9gDiv/YA4v/2APM//YAQwAC//YAA//2AAT/9gAF//YABv/2AAf/9gAI//YACf/2AAr/9gAL//YAMf/2ADL/9gBU//YAVf/2AFb/9gBo//YAcv/2AK7/9gKm//YCp//2Aqj/9gKp//YCqv/2Aqv/9gKs//YCrf/2Aq7/9gKv//YC1P/2AtX/9gL3//YC+P/2Avn/9gML//YDFv/2Ayv/9gMs//YDLf/2Ay7/9gMv//YDMP/2AzH/9gMy//YDM//2AzT/9gM1//YDNv/2Azf/9gNk//YDZf/2A3v/9gN///YDgP/2A4H/9gOC//YDg//2A4T/9gOF//YDhv/2A4f/9gOI//YDif/2A4r/9gOL//YDuP/2A7n/9gO6//YAWQAC//sAA//7AAT/+wAF//sABv/7AAf/+wAI//sACf/7AAr/+wAL//sAMf/2ADL/9gBU//YAVf/2AFb/9gBi//sAaf/2AGr/9gBr//YAbP/2AG3/9gBy//sAr//7ALD/+wCx//sAsv/7ALP/+wKm//sCp//7Aqj/+wKp//sCqv/7Aqv/+wKs//sCrf/7Aq7/+wKv//sC1P/2AtX/9gL3//YC+P/2Avn/9gMF//sDDP/2Aw3/9gMO//YDD//2AxD/9gMW//sDK//7Ayz/+wMt//sDLv/7Ay//+wMw//sDMf/7AzL/+wMz//sDNP/7AzX/+wM2//sDN//7A2T/9gNl//YDc//2A3T/9gN1//YDdv/2A3v/9gN///sDgP/7A4H/+wOC//sDg//7A4T/+wOF//sDhv/7A4f/+wOI//sDif/7A4r/+wOL//sDuP/2A7n/9gO6//YDyP/2A8n/9gPK//YDy//2AGUAAv/TAAP/0wAE/9MABf/TAAb/0wAH/9MACP/TAAn/0wAK/9MAC//TADH/qwAy/6sATv/2AE//9gBQ//YAUf/2AFL/9gBT//YAaP/nAG7/9gBv//YAcP/2AHH/9gBy/9MAe//7AH//+wCA//sAgf/7AIL/+wCD//sAhP/7AIX/+wCG//sAh//7AIj/+wCj//sApP/7AKX/+wCm//sAp//7AKj/+wCu/+cAtP/7Aqb/0wKn/9MCqP/TAqn/0wKq/9MCq//TAqz/0wKt/9MCrv/TAq//0wLU/6sC1f+rAvH/9gLy//YC8//2AvT/9gL1//YC9v/2Awv/5wMR//YDEv/2AxP/9gMU//YDFv/TAyD/+wMr/9MDLP/TAy3/0wMu/9MDL//TAzD/0wMx/9MDMv/TAzP/0wM0/9MDNf/TAzb/0wM3/9MDYf/2A2L/9gN3//YDe/+rA3//0wOA/9MDgf/TA4L/0wOD/9MDhP/TA4X/0wOG/9MDh//TA4j/0wOJ/9MDiv/TA4v/0wO1//YDtv/2A8z/9gCQAAL/9gAD//YABP/2AAX/9gAG//YAB//2AAj/9gAJ//YACv/2AAv/9gAN//YADv/2AA//9gAQ//YAEf/2ABL/9gAg//YAIf/2ACL/9gAj//YAJP/2ADH/7AAy/+wAP//2AED/9gBB//YAQv/2AEP/9gBE//YARf/2AEb/9gBH//YASf/2AGj/9gBy//YAdP/2AHz/9gCJ//YAiv/2AIv/9gCM//YAjf/2AI7/9gCP//YAkP/2AJH/9gCS//YArv/2Aqb/9gKn//YCqP/2Aqn/9gKq//YCq//2Aqz/9gKt//YCrv/2Aq//9gKx//YCsv/2ArP/9gK0//YCtf/2Arb/9gLE//YCxf/2Asb/9gLH//YCyP/2AtT/7ALV/+wC4v/2AuP/9gLk//YC5f/2Aub/9gLn//YC6P/2Aun/9gLq//YC7P/2Awv/9gMW//YDGP/2AyH/9gMr//YDLP/2Ay3/9gMu//YDL//2AzD/9gMx//YDMv/2AzP/9gM0//YDNf/2Azb/9gM3//YDQv/2A0P/9gNQ//YDUf/2A1L/9gNT//YDVP/2A1X/9gNW//YDV//2A1j/9gNZ//YDWv/2A1v/9gNc//YDXf/2A3v/7AN///YDgP/2A4H/9gOC//YDg//2A4T/9gOF//YDhv/2A4f/9gOI//YDif/2A4r/9gOL//YDlv/2A5f/9gOk//YDpf/2A6b/9gOn//YDqP/2A6n/9gOq//YDq//2A6z/9gOt//YDrv/2A6//9gOw//YDsf/2ALsADf/2AA7/9gAP//YAEP/2ABH/9gAS//YAIP/2ACH/9gAi//YAI//2ACT/9gA///YAQP/2AEH/9gBC//YAQ//2AET/9gBF//YARv/2AEf/9gBJ//YAVP/YAFX/2ABW/9gAV//2AFj/9gBZ//YAWv/2AFv/9gBc//YAXf/2AF7/9gBf//YAYP/2AGH/9gBi//YAY//7AGT/+wBl//sAZv/7AGf/+wBp//EAav/xAGv/8QBs//EAbf/xAHT/9gB8//YAif/2AIr/9gCL//YAjP/2AI3/9gCO//YAj//2AJD/9gCR//YAkv/2AKn/9gCq//YAq//2AKz/9gCt//YAr//nALD/5wCx/+cAsv/nALP/5wKx//YCsv/2ArP/9gK0//YCtf/2Arb/9gLE//YCxf/2Asb/9gLH//YCyP/2AuL/9gLj//YC5P/2AuX/9gLm//YC5//2Auj/9gLp//YC6v/2Auz/9gL3/9gC+P/YAvn/2AL6//YC+//2Avz/9gL9//YC/v/2Av//9gMA//YDAf/2AwL/9gMD//YDBP/2AwX/9gMG//sDB//7Awj/+wMJ//sDCv/7Awz/8QMN//EDDv/xAw//8QMQ//EDGP/2AyH/9gNC//YDQ//2A1D/9gNR//YDUv/2A1P/9gNU//YDVf/2A1b/9gNX//YDWP/2A1n/9gNa//YDW//2A1z/9gNd//YDZP/YA2X/2ANm//YDZ//2A2j/9gNp//YDav/2A2v/9gNs//YDbf/2A27/9gNv//YDcP/2A3H/9gNy//YDc//xA3T/8QN1//EDdv/xA5b/9gOX//YDpP/2A6X/9gOm//YDp//2A6j/9gOp//YDqv/2A6v/9gOs//YDrf/2A67/9gOv//YDsP/2A7H/9gO4/9gDuf/YA7r/2AO7//YDvP/2A73/9gO+//YDv//2A8D/9gPB//YDwv/2A8P/9gPE//YDxf/2A8b/9gPH//YDyP/xA8n/8QPK//EDy//xAAIAIgACACQAAAAnADAAIwAzADcALQA/AFYAMgBiAHYASgB6AHwAXwB+AJIAYgCdAJ8AdwCiAKgAegCuALQAgQDCAMQAiADOANEAiwDUANsAjwDfAOAAlwKmAsgAmQLLAtMAvALWAtoAxQLiAvkAygMFAxoA4gMcAxwA+AMhAyEA+QMrA0MA+gNGA0sBEwNRA1gBGQNeA2IBIQNkA2UBJgNzA3cBKAN5A3kBLQN/A5cBLgOaA58BRwOlA6wBTQOyA7YBVQO4A7oBWgPIA8wBXQACAE0AAgALAAMADQASAAEAIAAkAAEAJwAwAAQAMQAyAAsAPwBHAAEASQBJAAEATgBTAAcAVABWAAgAVwBhAAIAYgBiAA8AYwBnAAkAaABoAA0AaQBtAAYAbgBxAAoAcgByAAMAdAB0AAEAeAB4AAQAewB7AAUAfAB8AAEAfwCIAAUAiQCSAAEAowCoAAUAqQCtAAIArgCuAA0ArwCzAAwAtAC0AAUAwgDEAA4AzgDPABMA0ADQABQA0QDRABUA1ADUABQA1QDVABUA2ADYABEA2QDZABIA2gDaABEA2wDbABIA3wDgABACpgKvAAMCsQK2AAECxALIAAECywLTAAQC1ALVAAsC4gLqAAEC7ALsAAEC8QL2AAcC9wL5AAgC+gMEAAIDBQMFAA8DBgMKAAkDCwMLAA0DDAMQAAYDEQMU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AhUCFgIXAhgCGQIaAhsCHAIdAh4CHwIgAiECIgIjAiQCJQImAicCKAIpAioCKwIsAi0CLgIvAjACMQIyAjMCNAI1AjYCNwI5AjoCOwI8Aj0CPgI/AkACQQJCAkMCRAJFAkYCRwJJAkoCSwJMAk0CTgJPAlACUQJSAlMCVAJVAlYCVwJYAlkCWgJcAl0CXgJfAmACYQJiAmMCZAJlAoMCgAKGAoICbwJwAosCjAJxAnICcwJ0AnUCdgJ3AngChwJ+An8CeQJ6AogCiQJ7AoECfAKKAn0ChAKFAlsBZgGmAacBqAGpAaoBqwGsAa0BrgGvAbABsQGyAbMBtAG1AbYBtwG4AbkBugG7AbwBvQG+Ab8BwAHBAcIBwwHEAcUBxgHHAcgByQHKAcsBzAHNAc4BzwHQAdEB0gHTAdUB1gHXAdgB2QHaAdsB3AHdAd4B3wHgAeEB4gHjAeQB5QHmAecB6AHpAeoB6wHsAe0B7gHvAfAB8QHyAfMB9AH1AfYB9wH4AfkB+gH7AfwB/QH+Af8CAAIBAgICAwIEAgUCBgIHAggCCQIKAgsCDAINAg4CEAIPAhECEgITAhQCFQIiAhYCFwIYAhkCGgIbAhwCHQIeAh8CIAIhAAIFqgF3AaUBpgGnAagBqQGqAasBrAGtAa4BrwGwAbEBsgGzAbQBtQG2AbcBuAG5AboBuwG8Ab0BvgG/AcABwQHCAcMBxAHFAcYBxwHIAckBygHLAcwBzQHOAc8B0AHRAdIB0wHUAdUB1gHXAdgB2QHaAdsB3AHdAd4B3wHgAeEB4gHjAeQB5QHmAecB6AHpAeoB6wHsAe0B7gHvAfAB8QHyAfMB9AH1AfYB9wH4AfkB+gH7AfwB/QH+Af8CAAIBAgICAwIEAgUCBgIHAggCCQIKAgsCDAINAg4CDwIQAhECEgITAhQCFQIWAhcCGAIZAhoCGwIcAh0CHgIfAiACIQIiAiMCJAIlAiYCJwIoAikCKgIrAiwCLQIuAi8CMAIxAjICMwI0AjUCNgI3AjkCOgI7AjwCPQI+Aj8CQAJBAkICQwJEAkUCRgJHAkkCSgJLAkwCTQJOAk8CUAJRAlICUwJUAlUCVgJXAlgCWQJaAlwCXQJeAl8CYAJhAmICYwJkAmUCZgJnAmgCaQJqAmsCbAJtAm4CgwKAAoYCggJvAnACiwKMAnECcgJzAnQCdQJ2AncCeAKHAn4CfwJ5AnoCiAKJAnsCgQJ8AooCfQKEAoUCWwFmAWkBagFtAW4BcQFyAXUBdgF5AXoBfQF+AYEBggGFAYYBiQGKAY0BjgGmAacBqAGpAaoBqwGsAa0BrgGvAbABsQGyAbMBtAG1AbYBtwG4AbkBugG7AbwBvQG+Ab8BwAHBAcIBwwHEAcUBxgHHAcgByQHKAcsBzAHNAc4BzwHQAdEB0gHTAdUB1gHXAdgB2QHaAdsB3AHdAd4B3wHgAeEB4gHjAeQB5QHmAecB6AHpAeoB6wHsAe0B7gHvAfAB8QHyAfMB9AH1AfYB9wH4AfkB+gH7AfwB/QH+Af8CAAIBAgICAwIEAgUCBgIHAggCCQIKAgsCDAINAg4CEAIPAhECEgITAhQCFQIiAhYCFwIYAhkCGgIbAhwCHQIeAh8CIAIhAAEAAQDuAAEDJgABAAIAUQL0AAEAAgDQANEAAQABAPMAAQABAjcAAQMMAAEDGAACAAEAtwDAAAAAAQACADUC2AABAAICpgLiAAEAAgA5AtwAAQACAGgDCwABAAECpgABAAEC4gACAAEBNQE8AAAAAgACADoAPgAAAt0C4QAFAAIAAgBjAGcAAAMGAwoABQACAAIAaQBtAAADDAMQAAUAAgACATUBPAAAAUMBSgAIAAIAAgFDAUoAAAFTAVoACAABAAwANQA2ADcAOAB5AHoC2ALZAtoC2wMeAx8AAgACACcAMAAAAssC0wAKAAIAAgAVAB4AAAK5AsIACgACAAQAAgALAAAAcgByAAoCpgKvAAsDFgMWABUAAQAdAMIAwwDEAMUAxgDHAMgAyQDKAWcBaAFrAWwBbwFwAXMBdAF3AXgBewF8AX8BgAGDAYQBhwGIAYsBjAACAAwBywHWAAAB2QHdAAwCBwILABECHQIeABYCNwI3ABgCOQJJABkCTwJTACoCkwKUAC8ClgKWADECnQKdADICogKiADMCpAKkADQAcAE1ATYBNwE4ATkBOgE7ATwBQwFEAUUBRgFHAUgBSgFJAVMBVAFYAVUBWQFaAVcBVgFLAUwBTQFOAVEBUgFQAU8BWwFcAV0BXgFgAWEBXwFiAT8BQAFBAUIBPgE9AWMBZAFlAWYBZwFoAWkBagGZAZoBnAGbAYgBhwGKAYkBjwGQAZEBkwGVAZcBnQGfAZ4BoAFrAWwBbQFuAW8BcAFxAXIBcwF0AXUBdgF3AXgBeQF6AXsBfAF9AX4BiwGMAY0BjgGDAYQBhQGGAaIBowGkAaEBfwGAAYEBggGSAZQBlgGYAAIACAABALQAAAC3AMAAtADMAOcAvgDuAO8A2gEpASkA3AFlAWUA3QKmAxsA3gMdAyIBVAACABMAAQC0AAAAtwDAALQAwgDKAL4AzADnAMcA7gDvAOMBKQEpAOUBZQFlAOYBZwFoAOcBawFsAOkBbwFwAOsBcwF0AO0BdwF4AO8BewF8APEBfwGAAPMBgwGEAPUBhwGIAPcBiwGMAPkCpgMbAPsDHQMiAXECOAACAjcAAAABAAIA8gA1AAEAAAACAAAAAQACAPIC2AABAAAAAgAAAAEQAAH0/gwAAAWb/Pj8+AbwAAAAAQAAAAAAAAAAAAAAAAKnA+gAZAPoA1wD6ACMA+j/lwPo/5cD6P+LA+j/qgPo/6kD6P+QA+j/vwPo/4sD6ACMA+gAjAPoAIwD6ACMA+j/lwPo/4sD6P+dA+j/iAPoAIwD6P+IA+gAjAPo/5cD6P+XA+j/iwPo/6kD6P+/A+j/iwPo/50D6ACMA+j/iAPoAIwD6ACMA+j/iwPo/4sD6P+dA+gAjAPoAIwD6P+LA+gAjAPo/5cD6P+XA+j/iwPo/6kD6P+qA+j/vwPo/4sD6ACMA+j/nQPoAIwD6P+LA+gAjAPoAIwD6ACMA+j/lwPoAIwD6ACMA+gAjAPoAIwD6P+qA+j/lwPoAIwD6P+IA+gAfQPo/5cD6P+XA+j/iwPo/6oD6P+pA+j/vwPo/4sD6P9PA+gAjAPoAH0D6ACMA+j/lwPoAIwD6P+IA+gAjAPo/5cD6P+LA+gAjAPo/4gD6ACMA+gAjAPoAIwD6P+IA+gAjAPo/5cD6P+XA+j/iwPo/6kD6P+qA+j/vwPo/4sD6P7qA+j/TwPoAIwD6ACMA+gAjAPo/4sD6P+XA+j/lwPo/6kD6ACMA+gAjAPo/5cD6P+LA+j/qQPo/5cD6ACMA+j/lwPo/50D6P+IA+gAjAPoAIwD6ABGA+gAjAPoAIwD6ACMA+gAjAPoAIwD6ACMA+gAfQPoAIwD6ACMA+gAjAPoAH0D6P+XA+j/lwPo/4sD6P+qA+j/qQPo/5AD6P+/A+j/iwPoAH0D6ACMA+j/lwPo/5cD6P+LA+j/qQPo/78D6P+LA+j/nQPoAIwD6P+IA+gAjAPo/5kD6P+XA+j/iwPo/6kD6P+qA+j/vwPo/4sD6ACMA+j/nQPoAIwD6P+XA+gAjAPoAIwD6ACMA+gAjAPoAH0D6AB9A+j/qgPo/5cD6AB9A+j/iAPoAIwD6P+LA+j/lwPo/5cD6P+pA+gAjAPoAI0D6P+XA+j/iwPo/6kD6P+XA+gAjAPoAIwD6ACCA+gAfQPoAIwD6ACMA+gAjAPoAIwD6ACMA+gAjAPoAIwD6AB9A+gAfQPoAvUD6AGNA+gBjQPoAY0D6AA8A+gAPAPoADwD6AA8A+gAPAPoADwD6ACMA+gAhwPoAIcD6ACMA+gAjAPoAIwD6ACMA+gAjAPoAIwD6ACMA+gAjAPoAkkD6AJJA+gBAwPoAQMD6AEGA+gBAAPoAIwD6ACMA+gAeAPoAkkD6AJJA+gA5gPoAOYD6AJJA+gAjAPoAIwD6ACMA+gAjAPoADID6AAyA+gAjAPoADID6AAyA+gAMQPoAIwD6AAyA+gAjAPoAIwD6AFtA+gBQQPoAIwD6ACMA+gAywPoAZcD6ACNA+gAtgPoAMwD6AEBA+gAwgPoAMID6AB8A+gAfAPoAOcD6ACqA+gBbwPoAI8D6AF4A+gAjAPoAIwD6ACMA+gAjAPoAH0D6AEiA+gBIgPoADID6ADeA+gAjAPoADID6AAyA+gAWgPoAIwD6AB7A+gAjAPoAIwD6ACMA+gAeAPoAIwD6ACHA+gAMQPoADED6P+XA+j/lwPo/08D6P+LA+j/iAPo/4sD6P+qA+j/vwPo/6kD6P+dA+j+6gPoArED6AMZA+gDhwPoAIwD6P6XA+j+lwPo/mYD6P6mA+j+gAPo/qYD6P6wA+j+pgPo/qYD6P6/A+gA0QPoALMD6ADRA+gAswPoAOsD6ADrA+gA3wPoAN8D6ABkA+gAZAPoAJsD6ACbA+gAoAPoAKAD6AD1A+gA9QPoAI0D6ACNA+gAXgPoAF4D6AC2A+gAtgPoAOoD6ACCA+gA6gPoAIID6ACgA+gAoAPoAEkD6ABJA+gBAAPoAQAD6ACNA+gAwgPoAMID6ACNA+gAdAPoAHQD6AD1A+gAggPoAPUD6ACCA+gAvQPoAL0D6ABuA+gAbgPoA1wD6ANcA+j/2APo/9gD6P/YA+j/2ALxAM8C8f/YA+j/fgPo/34CMAAyAjD/2APo/9gD6P/YAV4ARgFeAAAD6P++A+j/vgFeACEBXv/YA+j/2APo/9gBXgBkAV7/2APo/9gD6P/YAV4ARgFe/9gD6P/YA+j/2AKKAAQCiv/YA+j/GgPo/xoDhAAUA4T/2APo/wwD6P8MAosACgKL/9gD6P/YA+j8+ASw/6sEsP+rBQAAZAUAAFAFAABGBQAAZAUAAGQFAABkBQAAZAUA//wFAABkBQAAYwUAAGQFAABkBQAAZAUAAGQFAP+vBQD/rwWbAAoFmwACBQAAZAUAAGQFAP/9BQD/9gDlA1wDUQA+A/cAFwP3ABcD/QARA+0AIAP4ACoD8wAMA+IAKgQHABsDsQA+A10ARQNgAEgDiQBIA/wAFwQCABED8AARBAwAGANgAEgEDAAYA3AAUAQEABcEBAAXBAoAEQQFACoD7wAqBBQAGwP4ABEDwwBQBBQAGANYAFADWwBDBAIAEQQMABsD8AARBEEAQwNWAEMD/QARA3AAUAQEABcEBAAXBAoAEQQFACoD+gAgA+8AKgQUABsDwwBQA/gAEQNQADcEAgARA1YAQwRBAEMDVwA3BAQAFwQ1ADcDYwBDA1YAQwNWAEMD7QAgA/cAFwRBAEMEBwAYA2AAOQP8ABcD/AAXBAIAEQPyACAD/QAqA+cAKgQMABsEUgAlA08ASAOmADkDWwBIA/cAFwRGAEgEBwAYA2AASAP8ABcEAgARA4kASAQMABgERgBIA1cAUAPqAFAD+wAYA1sAQwP8ABcD/AAXBAIAEQP9ACoD8gAgA+cAKgQMABsEowARBFIAJQPBAEMDUQBDA1YAQwP9ABED9wAXA/cAFwP4ACoDVgBDA0oAQwPrABcD8QARA+wAKgPrABcDcABQBAQAFwP4ABEEFAAYA2gASANwAFADdAAMA1IAQQNwAFADcABQA1sAQwP0ADcDVwA3A6IAQwNwAFADVwBQA3AAUANcADkD9wAXA/cAFwP9ABED7QAgA/gAKgP0AAwD4gAqBAcAGwO7ADkDYABIA/wAFwP8ABcEAgARA/0AKgPnACoEDAAbA/AAEQO7AEgEDAAYAz4ANwNWAEMD6wAXA+sAFwPxABED7AAqA+EAIAPWACoD+wAbA6oANwPfABEDVwA3BAQAFwQ1ADcDYwBDA/QANwNXADcDLwA3A3IAQwNcADkD7QAgA/cAFwPbAC8EBwAYA3IAUAQMABEEBgAXBAYAFwQHACoDVgBDA0oAQwPrABcD8QARA+wAKgPrABcDaABIATUAEQNgADkDaABIA2gASANgAEgDSgBDA2gAUANbAEMDWQBQA2AAOQNcADkBpAAoAt4ARgRuAEYBrQAwAa0ALQGtADABrQAtAccAFAHHAC0B8wA0AfMASAHzADQB8wBIAfMASAHzAEgCMwA8AjMAUAMsADIDLAA8AbMAUAHzAEgBswBQAz4ANwNPADcDcABQA3QAPgN6AFADPgA3AhcAUAN6AFADQgA0A/EANgIHAEgC5gBQAxAASwNbAEsDTwBIAVgAIAFYACoDKQA+AzgASAM4AEgDSABQAzMAQwMuAEMDSABQAycANwMuAEMDLwA3Ay4AQwM4ADkDMwBIAzgASAMvAFADMwBDAy4AQwMiAEMDSABQAzMAOQM4AEgDFgA3AzMAOQNKAFADIQBDA+gAjP+X/5f/i/+q/6n/kP+//4sAjACMAIwAjP+X/4v/nf+IAIz/iACM/5f/l/+L/6n/v/+L/50AjP+IAIwAjP+L/4v/nQCMAIz/iwCM/5f/l/+L/6n/qv+//4sAjACM/4sAjACMAIz/lwCMAIwAjACM/6r/lwCM/4gAff+X/5f/i/+q/6n/v/+L/08AjAB9AIz/lwCM/4gAjP+X/4sAjP+IAIwAjACM/4gAjP+X/5f/i/+p/6r/v/+L/ur/TwCMAIwAjP+L/5f/l/+pAIwAjP+X/6n/i/+XAIz/l/+d/4gAjACMAIwARgCMAIwAjACMAIwAjACMAH0AjACMAIwAjACMAIwAjACMAIwAjP+IAIz/YP6m/r/+gP6w/4v+pv6m/mb+pv+LAIwAjACM/2D/qv6m/r/+gP6w/4v/iP+/AIwAjP+I/2AAjACM/78AjACM/50AjACMADv/iAB9/2D+pv6//oD+sP+L/5f/jf9g/6AAOwCM/78AjP+dAIwAjACMAIwAO/+I/uP+tf6s/rUAjP9g/5f/l/9g/6oAO/+dAIz/YP+qAIwAfQCM/y4AjAB9AIwAff+IAIz/YP6m/r/+gP6w/4v+pv6m/mb+pv+LAIwAjACM/2D/qv6m/r/+gP6w/4v/iP+/AIwAjP+I/2AAjACM/78AjACM/50AjACMADv/iAB9/2D+pv6//oD+sP+L/5f/jf9g/6AAOwCM/78AjP+dAIwAjACMAIz/qQA7/4j+4/61/qz+tQCM/2D/l/+X/2D/qgA7/50AjP9g/6oAjACMAIwAjACMAIz/v/+X/5cCcf+X/5f/i/+q/7//i/+d/6n/YP7q/0//iAA7A4UDhAOHArEDGQOHA4QAjACMAIwAjACMAIwBjQGNAFoAjACMAIwAjACMAFoAWgCMAH0BGAC9AQMBBADSANMBDQENANYA1gCMAIwAjACMAIwDXAFLAVYBVgFWAVYBVgFWAVYBSwFLARwBHACBAIEAjACMAIwAjACMAIwAjACBAIEAUgBSAW0AjA==", "russo": "AAEAAAARAQAABAAQRFNJRwAAAAEAAJjMAAAACEZGVE1gxuFqAAB+LAAAABxHREVGAcoABAAAfkgAAAAgR1BPU2+5ph4AAH5oAAAaQkdTVUJskXSPAACYrAAAACBPUy8ybmUDYQAAAZgAAABgY21hcCkwLZAAAAhsAAADdmdhc3AAAAAQAAB+JAAAAAhnbHlmRS4geQAADygAAF2YaGVhZPoUIwwAAAEcAAAANmhoZWEHVwRRAAABVAAAACRobXR4wcktmwAAAfgAAAZ0bG9jYaJ4uZoAAAvsAAADPG1heHAB7gChAAABeAAAACBuYW1lfay1cgAAbMAAAAdrcG9zdIlFNR4AAHQsAAAJ93ByZXBoBoyFAAAL5AAAAAcAAQAAAAEAAIjQysFfDzz1AAsD6AAAAADLn2/QAAAAAMufb9D+/P7pBLoDngAAAAgAAgAAAAAAAAABAAADnv7pAAAEzv78/vwEugABAAAAAAAAAAAAAAAAAAABnQABAAABnQBYAAcARQAFAAIAAAABAAEAAABAAAAAAwABAAMCVwGQAAUAAAK8AooAAACMArwCigAAAd0AMgD6AAACAAUDBQAAAgAEgAACrwAAAAsAAAAAAAAAAFBZUlMAQAAgISIDnv7pAAADngEXAAAAlwAAAAACEgK8AAAAIAACASwAAAAAAAABLAAAASwAAAEYADIBkAAeAtoACgJ1AB4DXAAUAtAAHgDSAB4BRQAeAUX/9gHvAAoCHAAeAPAAHgHWAB4A8AAeAdYAAAKeACgBlQAAAk4AFAJiABQCigAUAlgAFAJ2ACgCMAAKAp4AHgJ2ABQA8AAeAPAAHgH+ABQB6gAoAf4AKAJEAAoDAgAoAsb/9gLGADwCbAAoAtAAPAJ7ADwCcQA8ArwAKALaADwBpAAeAcwACgKkADwCZwA8A4QAPALaADwC2gAoAsYAPALaACgC0AA8Ap4AHgJsAAoC7gA8Asb/9gPU//YClP/2Ap7/7AJiABQBaAA8AdYAAAFoAAAB/gAAAdYAHgD6AAACUwAZAmwAMgImACgCdgAoAlgAKAHCABQCbAAoAnYAMgFAABQBLP+mAlgAMgFUADIDnQAyAnYAMgJ2ACgCdgAyAmwAKAHMADICRAAUAbgAFAKAADICRP/2A3D/9gIm//YCOv/2AhcAFAFyAAoBLAA8AXIAAAH1AAoBGAAyAiYAKAI1AA8C2gAKAp7/7AEsADwCTgAeAZAAAANSABQBbQAKAmMACgIcACgB1gAeA1IAFAEsAAABhgAUAhwAHgFZABQBXgAUAQQACgKAADICsgAUASwAPADcAAAA+gAKAXwAFAJjABQC7gAKAxEACgM0ABQCRAAUAsb/9gLG//YCxv/2Asb/9gLG//YCxv/2A+P/9gJsACgCewA8AnsAPAJ7ADwCewA8AaQAHgGkAB4BpAAUAaQACgLkABQC2gA8AtoAKALaACgC2gAoAtoAKALaACgCHAAoAtoAGQLuADwC7gA8Au4APALuADwCnv/sAtoAPAJsADICUwAZAlMAGQJTABkCUwAZAlMAGQJTABkDmAAZAiYAKAJYACgCWAAoAlgAKAJYACgBQAAUAUAAFAFA/+cBQP/YAmIAKAJ2ADICdgAoAnYAKAJ2ACgCdgAoAnYAKAIcAB4CdgAPAoAAMgKAADICgAAyAoAAMgI6//YCdgAyAjr/9gLG//YCUwAZAsb/9gJTABkCxv/2AlMAGQJsACgCJgAoAmwAKAImACgC0AA8AzQAKALkABQClAAoAnsAPAJYACgCewA8AlgAKAJ7ADwCWAAoAnsAPAJYACgCvAAoAmwAKAK8ACgCbAAoApQAFAGkAB4BQP/xAaQAHgFAAAoBpAAeAUAAFAGkAB4BQAAUAmIAFAHMAAoBLP+mAqQAPAJYADICWAAyAmcAPAFUADICZwA8AVQAMgJnADwB0QAyAeoAMgJ7ABQBcgAUAtoAPAJ2ADIC2gA8AnYAMgLaADwCdgAyAtoAKAJ2ACgC2gAoAnYAKAPjACgDsQAoAtAAPAHMADIC0AA8AcwAMgLQADwBzAAyAp4AHgJEABQCngAeAkQAFAKeAB4CRAAUAmwACgG4ABQCbAAKAlgAFALuADwCgAAyAu4APAKAADIC7gA8AoAAMgLuADwCgAAyAp7/7AJiABQCFwAUAmIAFAIXABQCYgAUAhcAFAHM/34CngAeAkQAFAF8AAABfAAAAWgAAACqAAAAAP78AM0AAAFeAAABfAAAAnsAPAMWAAoCZwA8AmwAKAKeAB4BpAAeAaQACgHMAAoERwAKBDgAPAMWAAACowA8ArL/7ALaADwCxv/2AsYAPALGADwCZwA8AwwACgJ7ADwD8gAAAoAAFALaADwC2gA8AqMAPALpAAoDhAA8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Lm9yZy9PRkwAAFIAdQBzAHMAbwAgAE8AbgBlAABSdXNzbyBPbmUAAAACAAAAAAAA/7UAMgAAAAAAAAAAAAAAAAAAAAAAAAAAAZ0AAAABAAIAAwAEAAUABgAHAAgACQAKAAsADAANAA4ADwAQABEAEgATABQAFQAWABcAGAAZABoAGwAcAB0AHgAfACAAIQAiACMAJAAlACYAJwAoACkAKgArACwALQAuAC8AMAAxADIAMwA0ADUANgA3ADgAOQA6ADsAPAA9AD4APwBAAEEAQgBDAEQARQBGAEcASABJAEoASwBMAE0ATgBPAFAAUQBSAFMAVABVAFYAVwBYAFkAWgBbAFwAXQBeAF8AYABhAKMAhACFAL0AlgDoAIYAjgCLAJ0AqQCkAQIAigDaAIMAkwDyAPMAjQCXAIgAwwDeAPEAngCqAPUA9AD2AKIArQDJAMcArgBiAGMAkABkAMsAZQDIAMoAzwDMAM0AzgDpAGYA0wDQANEArwBnAPAAkQDWANQA1QBoAOsA7QCJAGoAaQBrAG0AbABuAKAAbwBxAHAAcgBzAHUAdAB2AHcA6gB4AHoAeQB7AH0AfAC4AKEAfwB+AIAAgQDsAO4AugEDAQQBBQEGAQcBCAD9AP4A/wEAAQkBCgELAQEBDAENAQ4BDwEQAREBEgETAPgA+QEUARUBFgEXARgBGQEaARsBHAD6ANcBHQEeAR8BIAEhASIBIwEkASUBJgEnASgBKQDiAOMBKgErASwBLQEuAS8BMAExATIBMwCwALEBNAE1ATYBNwE4ATkBOgE7APsA/ADkAOUBPAE9AT4BPwFAAUEBQgFDAUQBRQFGAUcAuwFIAUkBSgFLAOYA5wCmAUwBTQDYAOEA2wDcAN0A4ADZAN8BTgFPAVABUQFSAVMBVAFVAVYBVwFYAVkBWgFbAVwBXQFeAV8BYAFhAWIBYwFkAWUBZgFnAWgBaQFqAWsBbAFtAW4BbwFwAXEBcgFzAXQBdQF2AXcBeAF5AXoBewF8AX0BfgF/AYABgQGCAYMBhAGFAYYBhwGIAYkBigGLAYwBjQGOAY8BkAGRAZIBkwGUAZUBlgGXAZgBmQGaAZsBnAGdAZ4BnwGgAaEBogGjAaQBpQGmAacBqAGpAaoBqwCyALMAtgC3AMQAtAC1AMUAggDCAIcAqwDGAL4AvwGsAa0BrgGvAIwBsAGxB3VuaTAwQUQHQW1hY3JvbgdhbWFjcm9uBkFicmV2ZQZhYnJldmUHQW9nb25lawdhb2dvbmVrBkRjYXJvbgZkY2Fyb24GRGNyb2F0B0VtYWNyb24HZW1hY3JvbgpFZG90YWNjZW50CmVkb3RhY2NlbnQHRW9nb25lawdlb2dvbmVrBkVjYXJvbgZlY2Fyb24MR2NvbW1hYWNjZW50DGdjb21tYWFjY2VudARoYmFyBkl0aWxkZQZpdGlsZGUHSW1hY3JvbgdpbWFjcm9uB0lvZ29uZWsHaW9nb25lawJpagtKY2lyY3VtZmxleAtqY2lyY3VtZmxleAxLY29tbWFhY2NlbnQMa2NvbW1hYWNjZW50DGtncmVlbmxhbmRpYwZMYWN1dGUGbGFjdXRlDExjb21tYWFjY2VudAxsY29tbWFhY2NlbnQGTGNhcm9uBmxjYXJvbgRsZG90Bk5hY3V0ZQZuYWN1dGUMTmNvbW1hYWNjZW50DG5jb21tYWFjY2VudAZOY2Fyb24GbmNhcm9uB09tYWNyb24Hb21hY3Jvbg1PaHVuZ2FydW1sYXV0DW9odW5nYXJ1bWxhdXQGUmFjdXRlBnJhY3V0ZQxSY29tbWFhY2NlbnQMcmNvbW1hYWNjZW50BlJjYXJvbgZyY2Fyb24GU2FjdXRlBnNhY3V0ZQxUY29tbWFhY2NlbnQMdGNvbW1hYWNjZW50BlRjYXJvbgZ0Y2Fyb24HVW1hY3Jvbgd1bWFjcm9uBVVyaW5nBXVyaW5nDVVodW5nYXJ1bWxhdXQNdWh1bmdhcnVtbGF1dAdVb2dvbmVrB3VvZ29uZWsGWmFjdXRlBnphY3V0ZQpaZG90YWNjZW50Cnpkb3RhY2NlbnQMU2NvbW1hYWNjZW50DHNjb21tYWFjY2VudAlhZmlpMTAwMjMJYWZpaTEwMDUxCWFmaWkxMDA1MglhZmlpMTAwNTMJYWZpaTEwMDU0CWFmaWkxMDA1NQlhZmlpMTAwNTYJYWZpaTEwMDU3CWFmaWkxMDA1OAlhZmlpMTAwNTkJYWZpaTEwMDYwCWFmaWkxMDA2MQlhZmlpMTAwNjIJYWZpaTEwMTQ1CWFmaWkxMDAxNwlhZmlpMTAwMTgJYWZpaTEwMDE5CWFmaWkxMDAyMAlhZmlpMTAwMjEJYWZpaTEwMDIyCWFmaWkxMDAyNAlhZmlpMTAwMjUJYWZpaTEwMDI2CWFmaWkxMDAyNwlhZmlpMTAwMjgJYWZpaTEwMDI5CWFmaWkxMDAzMAlhZmlpMTAwMzEJYWZpaTEwMDMyCWFmaWkxMDAzMwlhZmlpMTAwMzQJYWZpaTEwMDM1CWFmaWkxMDAzNglhZmlpMTAwMzcJYWZpaTEwMDM4CWFmaWkxMDAzOQlhZmlpMTAwNDAJYWZpaTEwMDQxCWFmaWkxMDA0MglhZmlpMTAwNDMJYWZpaTEwMDQ0CWFmaWkxMDA0NQlhZmlpMTAwNDYJYWZpaTEwMDQ3CWFmaWkxMDA0OAlhZmlpMTAwNDkJYWZpaTEwMDY1CWFmaWkxMDA2NglhZmlpMTAwNjcJYWZpaTEwMDY4CWFmaWkxMDA2OQlhZmlpMTAwNzAJYWZpaTEwMDcyCWFmaWkxMDA3MwlhZmlpMTAwNzQJYWZpaTEwMDc1CWFmaWkxMDA3NglhZmlpMTAwNzcJYWZpaTEwMDc4CWFmaWkxMDA3OQlhZmlpMTAwODAJYWZpaTEwMDgxCWFmaWkxMDA4MglhZmlpMTAwODMJYWZpaTEwMDg0CWFmaWkxMDA4NQlhZmlpMTAwODYJYWZpaTEwMDg3CWFmaWkxMDA4OAlhZmlpMTAwODkJYWZpaTEwMDkwCWFmaWkxMDA5MQlhZmlpMTAwOTIJYWZpaTEwMDkzCWFmaWkxMDA5NAlhZmlpMTAwOTUJYWZpaTEwMDk2CWFmaWkxMDA5NwlhZmlpMTAwNzEJYWZpaTEwMDk5CWFmaWkxMDEwMAlhZmlpMTAxMDEJYWZpaTEwMTAyCWFmaWkxMDEwMwlhZmlpMTAxMDQJYWZpaTEwMTA1CWFmaWkxMDEwNglhZmlpMTAxMDcJYWZpaTEwMTA4CWFmaWkxMDEwOQlhZmlpMTAxMTAJYWZpaTEwMTkzCWFmaWkxMDA1MAlhZmlpMTAwOTgMemVyb3N1cGVyaW9yDGZvdXJzdXBlcmlvcgRFdXJvCWFmaWk2MTM1Mgtjb21tYWFjY2VudAwudHRmYXV0b2hpbnQAAAEAAf//AA8AAAABAAAAAMmJbzEAAAAAy54CfwAAAADLn2+5AAEAAAAOAAAAGAAAAAAAAgABAAEBnAABAAQAAAACAAAAAQAAAAoAHgAsAAFsYXRuAAgABAAAAAD//wABAAAAAWtlcm4ACAAAAAEAAAABAAQAAgAAAAEACAABGHwABAAAAMUBlAGUAZQB4gKcAqICqAKyAugC6ALyApwCnAMMA8oEAAQSBGwF8gYUBj4GhAbeByAHcgewB/4JeAmiC1gLtgv4Db4BlAGUDcQN0g3SDeQOJg4sDqoN0g3SDtAPjg+4EJoRVA4sEVQBlAMMAwwDDAMMAwwDDAQABBIG3gbeBt4G3gbeBt4JeAl4CXgJeAv4BBINxA3EDcQNxA3EDcQN0g3SDdIN0g3SDdIN0g3SDdIN0g3SDdIN0gMMDcQDDA3EAwwNxAQABAAEEgQSDdIN0g3SDdIGPg4sBoQGhAaEBoQG3g3SBt4N0g3SDtAO0A7QB7APjgewD44HsA+OB/4PuAf+D7gJeAl4CXgJeAv4Db4Nvg2+Eg4SXBM+Eg4SDhIOE0gTVhQ8FJ4U1BJcFPYVHBUqE0gTPhVYFY4VrBNWFooWxBbeFt4SDhIOEz4TPhcAFwoXIBc+F2QXeheIF54XehewF9YXehgYF2QXZBg2GDYXnheeF3oXPheeGDYYNhfWElwXPgGUAZQBlAGUABMAF//YACT/xACB/8QAgv/EAIP/xACE/8QAhf/EAIb/xADB/8QAw//EAMX/xAEw/9gBMf/YATf/xAE7/9gBQv/YAVv/4gFi/+IBf//iAC4AFP/YABX/4gAW/+IAGv/OACT/4gAt/+IAN//EADn/4gA6/+wAPP/OAD3/2ACB/+IAgv/iAIP/4gCE/+IAhf/iAIb/4gCH/+IAnv/OAMH/4gDD/+IAxf/iAQv/xAEN/8QBF//OARj/2AEa/9gBHP/YASr/zgEw/+IBMf/iATP/zgE1/8QBN//iATv/4gE9/9gBPv/YAUL/4gFJ/8QBSv/EAUz/zgFR/84BVP/iAVv/7AFi/+wBf//sAAEAGv/sAAEAF//YAAIAFv/sABr/7AANAAX/2AAK/9gADf/YABT/zgAVABQAGv/EAEH/2ABD/9gAcf/YAYn/2AGK/9gBjP/YAY3/2AACABT/4gAa/+wABgAP/84AEf/OABf/2AGL/84Bjv/OAZL/zgAvAAX/xAAK/8QADf/EABD/4gAm/+wAKv/sADL/7AA0/+wAN/+6ADj/7AA5/7oAOv/OADz/sABB/8QAQ//EAFn/4gBa/+wAXP/iAHH/xACI/+wAk//sAJT/7ACV/+wAlv/sAJf/7ACZ/+wAmv/sAJv/7ACc/+wAnf/sAJ7/sADH/+wAyf/sAPn/7AD7/+wA/f/sAQv/ugEN/7oBD//sARH/7AET/+wBFf/sARf/sAGJ/8QBiv/EAYz/xAGN/8QADQA3/+wAOf/sADr/7AA7/+wAPP/sAD3/9gCe/+wBC//sAQ3/7AEX/+wBGP/2ARr/9gEc//YABAAQ/+IAWf/YAFr/2ABc/9gAFgAk/+IAN//sADn/7AA7/+wAPP/sAD3/9gCB/+IAgv/iAIP/4gCE/+IAhf/iAIb/4gCe/+wAwf/iAMP/4gDF/+IBC//sAQ3/7AEX/+wBGP/2ARr/9gEc//YAYQAP/7AAEP/iABH/sAAk/8QALf/OAET/2ABG/9gAR//YAEj/2ABJ/+wASv/YAFD/7ABR/+wAUv/YAFP/7ABU/9gAVf/YAFb/7ABX/+wAWP/sAFn/2ABa/9gAW//YAFz/2ABd/9gAgf/EAIL/xACD/8QAhP/EAIX/xACG/8QAh//OAKH/2ACi/9gAo//YAKT/2ACl/9gApv/YAKf/2ACo/9gAqf/YAKr/2ACr/9gArP/YALH/2ACy/+wAs//YALT/2AC1/9gAtv/YALf/2AC5/9gAuv/sALv/7AC8/+wAvf/sAL7/7ADA/+wAwf/EAML/2ADD/8QAxP/YAMX/xADG/9gAyP/YAMr/2ADM/9gAzv/YAND/2ADS/9gA1P/YANb/2ADa/9gA9P/sAPb/7AD4/+wA+v/YAPz/2AD+/9gBAP/YAQL/2AEE/9gBBv/sAQj/7AEK/+wBDP/sAQ7/7AEQ/+wBEv/sART/7AEW/+wBGf/YARv/2AEd/9gBi/+wAY7/sAGS/7AACAA3/84AOf/YADr/4gA8/9gAnv/YAQv/zgEN/84BF//YAAoAJP/iAIH/4gCC/+IAg//iAIT/4gCF/+IAhv/iAMH/4gDD/+IAxf/iABEAEP/iACb/7AAq/+wAMv/sADT/7ACI/+wAk//sAJT/7ACV/+wAlv/sAJf/7ACZ/+wAx//sAMn/7AD5/+wA+//sAP3/7AAWAAX/zgAK/84ADf/OABD/2AA3/4gAOf+cADr/sAA8/4gAQf/OAEP/zgBZ/9gAWv/YAFz/2ABx/84Anv+IAQv/iAEN/4gBF/+IAYn/zgGK/84BjP/OAY3/zgAQACT/7AA5/+wAOv/+ADv/7AA8/+wAgf/sAIL/7ACD/+wAhP/sAIX/7ACG/+wAnv/sAMH/7ADD/+wAxf/sARf/7AAUAA//sAAR/7AAJP/EADn//gA7/+wAPP/sAIH/xACC/8QAg//EAIT/xACF/8QAhv/EAJ7/7ADB/8QAw//EAMX/xAEX/+wBi/+wAY7/sAGS/7AADwAk/+wAOf/sADv/7AA8/+wAgf/sAIL/7ACD/+wAhP/sAIX/7ACG/+wAnv/sAMH/7ADD/+wAxf/sARf/7AATACT/7AA3/84AOf/iADr/4gA7/+wAPP/iAIH/7ACC/+wAg//sAIT/7ACF/+wAhv/sAJ7/4gDB/+wAw//sAMX/7AEL/84BDf/OARf/4gBeAA//sAAQ/8QAEf+wACT/ugAt/84ARP/OAEb/zgBH/84ASP/OAEn/4gBK/84AUP/OAFH/zgBS/84AU//OAFT/zgBV/84AVv/OAFj/zgBZ/84AWv/OAFv/zgBc/84AXf/OAIH/ugCC/7oAg/+6AIT/ugCF/7oAhv+6AIf/zgCh/84Aov/OAKP/zgCk/84Apf/OAKb/zgCn/84AqP/OAKn/zgCq/84Aq//OAKz/zgCx/84Asv/OALP/zgC0/84Atf/OALb/zgC3/84Auf/OALr/zgC7/84AvP/OAL3/zgC+/84AwP/OAMH/ugDC/84Aw/+6AMT/zgDF/7oAxv/OAMj/zgDK/84AzP/OAM7/zgDQ/84A0v/OANT/zgDW/84A2v/OAPT/zgD2/84A+P/OAPr/zgD8/84A/v/OAQD/zgEC/84BBP/OAQb/zgEI/84BCv/OARD/zgES/84BFP/OARb/zgEZ/84BG//OAR3/zgGL/7ABjv+wAZL/sAAKACT/7ACB/+wAgv/sAIP/7ACE/+wAhf/sAIb/7ADB/+wAw//sAMX/7ABtAA//sAAQ/+IAEf+wACT/ugAm/+wAKv/sAC3/zgAy/+wANP/sADb//gBE/9gARv/iAEf/4gBI/+IASv/iAFD/4gBR/+IAUv/iAFP/4gBU/+IAVf/iAFb/4gBY/+IAXf/sAIH/ugCC/7oAg/+6AIT/ugCF/7oAhv+6AIf/zgCI/+wAk//sAJT/7ACV/+wAlv/sAJf/7ACZ/+wAof/YAKL/2ACj/9gApP/YAKX/2ACm/9gAp//iAKj/4gCp/+IAqv/iAKv/4gCs/+IAsf/iALL/4gCz/+IAtP/iALX/4gC2/+IAt//iALn/4gC6/+IAu//iALz/4gC9/+IAvv/iAMD/4gDB/7oAwv/YAMP/ugDE/9gAxf+6AMb/2ADH/+wAyP/iAMn/7ADK/+IAzP/iAM7/4gDQ/+IA0v/iANT/4gDW/+IA2v/iAPT/4gD2/+IA+P/iAPn/7AD6/+IA+//sAPz/4gD9/+wA/v/iAQD/4gEC/+IBBP/iAQX//gEG/+IBB//+AQj/4gEJ//4BCv/iARD/4gES/+IBFP/iARb/4gEZ/+wBG//sAR3/7AGL/7ABjv+wAZL/sAAXAA//zgAQ/+wAEf/OACT/zgAm/+wAKv/sAC3/2ACB/84Agv/OAIP/zgCE/84Ahf/OAIb/zgCH/9gAiP/sAMH/zgDD/84Axf/OAMf/7ADJ/+wBi//OAY7/zgGS/84AEAAm/+wAKv/sADL/7AA0/+wAiP/sAJP/7ACU/+wAlf/sAJb/7ACX/+wAmf/sAMf/7ADJ/+wA+f/sAPv/7AD9/+wAcQAP/7AAEP/OABH/sAAk/7AAJv/sACr/7AAt/84AMv/sADT/7AA2//4ARP/OAEb/zgBH/84ASP/OAEr/zgBQ/+IAUf/iAFL/zgBT/+IAVP/OAFX/4gBW/84AWP/iAFn/4gBa/+IAW//iAFz/4gBd/+IAgf+wAIL/sACD/7AAhP+wAIX/sACG/7AAh//OAIj/7ACT/+wAlP/sAJX/7ACW/+wAl//sAJn/7ACh/84Aov/OAKP/zgCk/84Apf/OAKb/zgCn/84AqP/OAKn/zgCq/84Aq//OAKz/zgCx/84Asv/iALP/zgC0/84Atf/OALb/zgC3/84Auf/OALr/4gC7/+IAvP/iAL3/4gC+/+IAwP/iAMH/sADC/84Aw/+wAMT/zgDF/7AAxv/OAMf/7ADI/84Ayf/sAMr/zgDM/84Azv/OAND/zgDS/84A1P/OANb/zgDa/84A9P/iAPb/4gD4/+IA+f/sAPr/zgD7/+wA/P/OAP3/7AD+/84BAP/iAQL/4gEE/+IBBf/+AQb/zgEH//4BCP/OAQn//gEK/84BEP/iARL/4gEU/+IBFv/iARn/4gEb/+IBHf/iAYv/sAGO/7ABkv+wAAEAEP/YAAMAWf/2AFr/9gBc//YABABZ//YAWv/2AFv/9gBc//YAEAAP/84AEf/OAET/4gBPABQAof/iAKL/4gCj/+IApP/iAKX/4gCm/+IAwv/iAMT/4gDG/+IBi//OAY7/zgGS/84AAQBNACgAHwBG//YAR//2AEj/9gBK//YAUv/2AFT/9gCn//YAqP/2AKn/9gCq//YAq//2AKz/9gCx//YAs//2ALT/9gC1//YAtv/2ALf/9gC5//YAyP/2AMr/9gDM//YAzv/2AND/9gDS//YA1P/2ANb/9gDa//YA+v/2APz/9gD+//YACQBJ/9gASv/sAFf/7ABZ/9gAWv/YAFz/2ADa/+wBDP/sAQ7/7AAvAA//zgAR/84ARP/YAEb/7ABH/+wASP/sAEr/7ABN/+wAUv/sAFT/7ACh/9gAov/YAKP/2ACk/9gApf/YAKb/2ACn/+wAqP/sAKn/7ACq/+wAq//sAKz/7ACx/+wAs//sALT/7AC1/+wAtv/sALf/7AC5/+wAwv/YAMT/2ADG/9gAyP/sAMr/7ADM/+wAzv/sAND/7ADS/+wA1P/sANb/7ADa/+wA+v/sAPz/7AD+/+wBi//OAY7/zgGS/84ACgBM//YAWf/sAFr/7ABc/+wArf/2AK7/9gCv//YAsP/2AN//9gDh//YAOAAQ/+wARP/sAEb/9gBH//YASP/2AEr/7ABM/+wAT//sAFL/7ABU/+wAV//sAFn/7ABa/+wAXP/sAKH/7ACi/+wAo//sAKT/7ACl/+wApv/sAKf/7ACo//YAqf/2AKr/9gCr//YArP/2AK3/7ACu/+wAr//sALD/7ACx/+wAs//sALT/7AC1/+wAtv/sALf/7AC5/+wAwv/sAMT/7ADG/+wAyP/2AMr/9gDM//YAzv/2AND/9gDS//YA1P/2ANb/9gDa/+wA3//sAOH/7AD6/+wA/P/sAP7/7AEM/+wBDv/sAC4AD//YABH/2ABE/+wARv/2AEf/9gBI//YASv/2AFL/9gBU//YAof/sAKL/7ACj/+wApP/sAKX/7ACm/+wAp//2AKj/9gCp//YAqv/2AKv/9gCs//YAsf/2ALP/9gC0//YAtf/2ALb/9gC3//YAuf/2AML/7ADE/+wAxv/sAMj/9gDK//YAzP/2AM7/9gDQ//YA0v/2ANT/9gDW//YA2v/2APr/9gD8//YA/v/2AYv/2AGO/9gBkv/YAC4AD//iABH/4gBE/+wARv/2AEf/9gBI//YASv/2AFL/9gBU//YAof/sAKL/7ACj/+wApP/sAKX/7ACm/+wAp//2AKj/9gCp//YAqv/2AKv/9gCs//YAsf/2ALP/9gC0//YAtf/2ALb/9gC3//YAuf/2AML/7ADE/+wAxv/sAMj/9gDK//YAzP/2AM7/9gDQ//YA0v/2ANT/9gDW//YA2v/2APr/9gD8//YA/v/2AYv/4gGO/+IBkv/iABMABf/EAAr/xAAN/8QAQf/EAEP/xABx/8QBKv/EATP/xAE1/84BPf/sAUn/sAFK/84BTP/sAU7/7AFR/8QBif/EAYr/xAGM/8QBjf/EADgAD/+cABD/ugAR/5wBMP/OATH/zgE3/4gBO/+wAUL/zgFL/+wBV/+cAVj/2AFZ/7ABWv+wAVv/nAFc/7ABXf+wAV7/sAFf/7ABYP+wAWH/sAFi/5wBY/+wAWT/sAFl/5wBZv+wAWf/sAFo/5wBaf+wAWr/sAFr/5wBbP+wAW3/sAFu/7ABb/+wAXD/sAFx/7ABcv+wAXP/sAF0/7ABdf+wAXb/sAF3/84Bef+wAXr/nAF7/5wBfP+wAX3/sAF+/7ABf/+cAYD/sAGD/7ABhP+wAYb/sAGL/5wBjv+cAZL/nAACATv/7AFM/+wAAwAQ/+IBaf/sAW7/7AA5AA//nAAQ/84AEf+cATD/2AEx/9gBN/+wATv/ugFC/9gBSP/sAUv/7AFX/84BWP/sAVn/4gFa/+IBW/+wAVz/2AFd/+wBXv/iAV//4gFg/+IBYf/iAWL/sAFj/+IBZP/iAWX/zgFm/+IBZ//iAWj/zgFp/+IBav/iAWv/zgFs/9gBbf/iAW7/4gFv/+IBcP/iAXH/4gFy/+IBc//iAXT/4gF1/+IBdv/YAXf/7AF5/+IBev/OAXv/zgF8/+IBff/iAX7/4gF//7ABgP/iAYP/4gGE/+IBhv/iAYv/nAGO/5wBkv+cABgABf/EAAr/xAAN/8QAEP/iAEH/xABD/8QAcf/EASr/zgEz/84BNf+6AUn/ugFK/7oBS//sAU7/zgFR/84Baf/OAWr/4gFu/+IBcf/YAYP/4gGJ/8QBiv/EAYz/xAGN/8QADQEq/84BM//OATX/zgE9//4BSf/OAUr/zgFM/+wBTv/sAVH/zgFp/+wBav/sAXH/7AGD/+wACAEq/+wBM//sATX/7AFJ/+wBSv/sAUz/7AFR/+wBcf/sAAkBKv/sATP/7AE1/+wBSf/sAUr/7AFO/+wBUf/sAWn/7AFx/+wAAwAQ/9gBaf/sAW7/7AALASr/7AEw/+wBMf/sATP/7AE1/+wBO//sAUL/7AFJ/+wBSv/sAUz/7AFR/+wADQAP/7AAEf+wATD/4gEx/+IBNf/sATf/xAE7/9gBQv/iAUr/7AFM/+wBi/+wAY7/sAGS/7AABwAQ/+IBS//sAWn/2AFq/9gBbv/iAXH/4gGD/9gANwAP/7AAEP/EABH/sAEw/+IBMf/iATf/ugE7/8QBQv/iAUv/7AFX/84BWP/sAVn/2AFa/9gBW/+wAV3/2AFe/9gBX//YAWD/2AFh/9gBYv+wAWP/2AFk/9gBZf/OAWb/2AFn/9gBaP/OAWn/2AFq/9gBa//OAWz/2AFt/9gBbv/YAW//2AFw/9gBcf/YAXL/2AFz/9gBdP/YAXX/2AF2/9gBd//iAXn/2AF6/84Be//OAXz/2AF9/9gBfv/YAX//sAGA/9gBg//YAYT/2AGG/9gBi/+wAY7/sAGS/7AADgEq/+IBMP/sATH/7AEz/+IBNf/sATf/7AE7/+IBPv/+AUL/7AFJ/+wBSv/sAUz/4gFR/+IBVP/iAAYAEP/OAS3/7AFF/+wBSP/sAUv/4gFO/+wACAEq/+IBM//iATX/7AFK/+wBTv/sAVH/4gFp/+wBcf/sAAIBav/2AYP/9gAFAWn/7AFq/+wBbP/sAXH/4gGD/+wABwFb//YBaf/sAWr/7AFs//YBbv/2AXH/7AGD/+wACQAP/7oAEf+6AVf/4gFb/9gBYv/YAX//2AGL/7oBjv+6AZL/ugAFAWn/7AFq//YBbv/iAXH/4gGD//YAAwFq//YBbP/2AYP/9gAFAVv/9gFq//YBbP/2AXH/9gGD//YABAFq//YBbP/2AXH/9gGD//YACQAP/84AEf/OAVf/7AFb/9gBYv/YAX//2AGL/84Bjv/OAZL/zgAQAA//4gAR/+IBV//sAVv/7AFc//YBYv/sAWX/9gFo//YBa//2AXf/9gF6//YBe//2AX//7AGL/+IBjv/iAZL/4gAHAVz/9gFl//YBaP/2AWv/9gF3//YBev/2AXv/9gARAAX/zgAK/84ADf/OAEH/zgBD/84Acf/OAV3/9gFp/84Bav/iAWz/9gFu/+wBcf/OAYP/4gGJ/84Biv/OAYz/zgGN/84AAQDFAAUACgANABAAEwAVABYAFwAYABkAGgAbABwAJAAlACYAJwApACoALQAuAC8AMgAzADQANgA3ADgAOQA6ADsAPAA9AEEAQwBEAEUASABJAE0ATgBPAFIAUwBVAFYAVwBZAFoAWwBcAHEAgQCCAIMAhACFAIYAiACRAJMAlACVAJYAlwCZAJoAmwCcAJ0AngCfAKEAogCjAKQApQCmAKcAqQCqAKsArACxALMAtAC1ALYAtwC5AL8AwQDCAMMAxADFAMYAxwDJAMsAzQDQANIA1ADWAOcA6ADqAOwA7gDxAPkA+gD7APwA/gEAAQIBBAEFAQYBBwEIAQkBCgELAQwBDQEOAQ8BEQETARUBFwEYARoBHAEqASsBLQExATIBMwE0ATUBNwE4ATkBOgE7AT0BPgFBAUUBRwFIAUkBSgFLAUwBTQFQAVEBUwFUAVUBVwFYAVkBWgFbAVwBXgFlAWcBaQFqAWsBbAFtAXABcQFzAXQBdQF3AXkBewF/AYABgwGFAYYBiQGKAYwBjQAAAAEAAAAKABwAHgABbGF0bgAIAAQAAAAA//8AAAAAAAAAAAABAAAAAA==", "rubik": "AAEAAAAOAIAAAwBgR0RFRhxZFfIAAJgQAAAA6kdQT1NZTRPvAACY/AAAR7RHU1VCx9EC9AAA4LAAAAdiT1MvMmsbNx8AAAFoAAAAYGNtYXBix3xqAAAHmAAAA05nYXNwAAAAEAAAmAgAAAAIZ2x5Zv8qzIsAAA3kAAB+ZmhlYWQwXi8oAAAA7AAAADZoaGVhBxICoAAAASQAAAAkaG10ePrYK78AAAHIAAAFzmxvY2HnGMkDAAAK6AAAAvptYXhwAYoA0wAAAUgAAAAgbmFtZT5uXKgAAIxMAAACdnBvc3QDxpzsAACOxAAACUQAAQAAAAJMzZj84PRfDzz1AAED6AAAAADm78+EAAAAAObvz4T/Kf7VBD8DmwAAAAYAAgAAAAAAAAABAAADp/8GAAAEc/8p/bsEPwABAAAAAAAAAAAAAAAAAAABawABAAABfABtAAUAZAAFAAEAAAAAAAAAAAAAAAAAAwABAAQCNwMgAAUAAAKKAlgAAABLAooCWAAAAV4AMgE4AAAAAAAAAAAAAAAAgAAIZ0AAAEsAAAAAAAAAAE5PTkUAwAAg+0sDp/8GAAAEKgHSIAAA9wAIAAACCAK8AAAAIAADArcAUALfAAUC3wAFAt8ABQLfAAUC3wAFAt8ABQLfAAUC3wAFA90ABALPAD4CzgApAs4AKQLYAD4C7gAOAo0APgKNAD4CjQA+Ao0APgKNAD4CeAA+AuAAKgL3AD4BWgA+AVoAPgFa/+IBWv/hAVr/yQKuABECrgARArEAPgJjAD4DSgA+AtoAPgLaAD4C1wAqAtcAKgLXACoC1wAqAtcAKgLXACoC1wAqA9cAKQKzAD4CtAA+AtcAKQLDAD4CqAAYAowAEwLgADgC4AA4AuAAOALgADgC4AA4AsYAEwNLAB0CywAGArcACQK3AAkCoAAkAl4AFgJeABYCXgAWAl4AFgJeABYCXgAWAl4AFgOdABYChgA0Al4AIgJeACIChgAjAm4AHwJhACECYQAhAmEAIQJhACECYQAhAdMAEAKKACMCmwA0ATAANAEwADQBMAA0ATD/0QEw/9wBMP+3AUT/wgG6ABQBugAUAmYANAExADQDnwA0ApIANAKSADQCcgAjAnIAIwJyACMCcgAjAnIAIwJyACMCcgAjA70AIwKGADQChwA1AoYAJAHmADQCPAAaApUANAH0AA0CkQAvApEALwKRAC8CkQAvApEALwJkAA4DVQAVAmEACgJpABECaQARAmkAEQI7ACUDVwAQBF4AEARzABAC2wAQAvAAEAFiAB0BYAAgArsALgIPAAwCpQAmAqwAHALFABsCnAAcAp8AGwJXABwCtgApApYAGQKpACUCqQAwAqkAKAKpABsCqQAOAqkAIwKpACACqQBFAqkAIgKpACMBegAdATUABwFrABkBaAATAYIAFAFmABYBZQAYAUEAEwFrABoBZQARAXoAHQE1AAcBawAZAWgAEwGCABQBZgAWAWUAGAFBABMBawAaAWUAEQC0/y4DVAAHA2sABwOdABMBegAdATUABwFrABkBaAATAYIAFAFmABYBZQAYAUEAEwFrABoBZQARATUABwFrABkBaAATAYIAFADIAAAAyAAAAP4AGwD+ABoA/gAbAP4AGgEqADABIwAZATMANAE5AB0DGQAvATYANwEwADQCcQAaAmwAGAFKACEBgwA9AbwAIQKqACoCLQAWAiwAFQCb//0ABP8pAdoAMwJYADMCNAAzAvIAMwLaACcA/gAbAP4AGgGUACQBlAAXAcIAAgHCABgBlwA4AZcAGQKpAKsCqQClASIAGAIYABgCEwAXAg4AIgEdABcBGAAiAnMAGgJzADcBWAAaAVgANwHlACEA/QAhA1IAKwL7ACcCnAAZAmwAHgMgACgDIAAoAo0AJQGkABkBFgA5ARsAOwJkACICcAAtArEAHQMiAB0C4wAoAs8AGQItABYCWAAfAoQAOQJtACgCDgAlAjUAOQIPADgCDwAbAjwALQIoADcCNwAwAd4AKAKmADkDOgAfAAAANgAAADYAAAA2AAAANgAAADYAAAA2AAAAIgAA/+EAAAA2AAAAZAAAAFQAAAA7AAAANgAAADYAAAA2AAAANgHkADYBqAA4AagANgH6ADYBLAA2AeMANgHIADYBIQAxAMsAAAMiAB0CzwAZArcAUALfAAUC3wAFAt8ABQKOAC0CjgAtAo4ALQKOAC0CSgAkAkoAJAHyAC4B8gAuAi4AGgIuABoCkQA2ApEANgE1ADYBff/8ATUANgGoACABqP/1ApUANgKOADACjgAwAS4AMwGJAA0CJQAYAiUAGAIeAC4CHgAuAhwAGgIcABoCgQA2AroAIQK6ACEBLQA2AccAIwHHACMCjAAwAowAMAKNACECSgAm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AAYAKAFOAAMAAQQJAA4ANgF2AAMAAQQJAQAADAGsAAMAAQQJAQYAEgG4AAMAAQQJAQgADAHKAAMAAQQJAQkACgHWAEMAbwBwAHkAcgBpAGcAaAB0ACAAMgAwADEANQAgAFQAaABlACAAUgB1AGIAaQBrACAAUAByAG8AagBlAGMAdAAgAEEAdQB0AGgAbwByAHMAIAAoAGgAdAB0AHAAcwA6AC8ALwBnAGkAdABoAHUAYgAuAGMAbwBtAC8AZwBvAG8AZwBsAGUAZgBvAG4AdABzAC8AcgB1AGIAaQBrACkAUgB1AGIAaQBrACAATABpAGcAaAB0ACAARQB4AHQAcgBhAEIAbwBsAGQAUgBlAGcAdQBsAGEAcgAyAC4AMwAwADAAOwBOAE8ATgBFADsAUgB1AGIAaQBrAEwAaQBnAGgAdAAtAEUAeAB0AHIAYQBCAG8AbABkAFYAZQByAHMAaQBvAG4AIAAyAC4AMwAwADAAOwBnAGYAdABvAG8AbABzAFsAMAAuADkALgAzADAAXQBSAHUAYgBpAGsATABpAGcAaAB0AC0ARQB4AHQAcgBhAEIAbwBsAGQAaAB0AHQAcABzADoALwAvAHMAYwByAGkAcAB0AHMALgBzAGkAbAAuAG8AcgBnAC8ATwBGAEwAVwBlAGkAZwBoAHQARQB4AHQAcgBhAEIAbwBsAGQASQB0AGEAbABpAGMAUgBvAG0AYQBuAAAAAgAAAAAAAP+6ADIAAAAAAAAAAAAAAAAAAAAAAAAAAAF8AAAAJADJAQIAxwBiAK0AYwCuAJAAJQAmAGQAJwDpACgAZQDIAMoAywApACoAKwAsAMwAzQDOAM8ALQEDAC4ALwAwADEAZgAyANAA0QBnANMAkQCvALAAMwDtADQANQA2ADcAOADUANUAaADWADkAOgA7ADwA6wA9AEQAaQBrAGwAagBuAG0AoABFAEYAbwBHAOoASABwAHIAcwBxAEkASgBLAEwA1wB0AHYAdwB1AE0BBAEFAE4ATwBQAFEAeABSAHkAewB8AHoAoQB9ALEAUwDuAFQAVQBWAIkAVwBYAH4AgACBAH8AWQBaAFsAXADsALoAXQEGAQcBCADAAMEAnQCeABMAFAAVABYAFwAYABkAGgAbABwBCQEKAQsBDAENAQ4BDwEQAREBEgETARQBFQEWARcBGAEZARoBGwEcAR0BHgEfASABIQEiASMBJAElASYAvAD0APUA9gEnASgBKQEqASsBLAEtAS4BLwEwATEBMgEzATQAAwE1ATYBNwE4ATkAEQAPAB0AHgCrAAQAowAiAKIAwwCHAA0ABgASAD8BOgE7ABABPACyALMAQgE9AT4ACwAMAF4AYAA+AEABPwFAAMQAxQC0ALUAtgC3AKkAqgC+AL8ABQAKACMACQCIAIYAiwCKAIwAgwBfAOgAhAC9AAcBQQCFAJYBQgAOAO8A8AC4ACAAIQAfAJMAYQCkAEEBQwAIAUQBRQFGAUcBSAFJAUoBSwFMAU0BTgFPAVABUQFSAVMAjgBDAI0A2ADdANkA2gDeAVQBVQFWAVcBWAFZAVoBWwFcAV0BXgFfAWABYQFiAWMBZAFlAWYBZwFoAWkBagFrAWwBbQFuAW8BcAFxAXIBcwF0AXUBdgF3AXgBeQF6AXsBfAF9AX4BfwGAAYEBggGDAYQBhQGGAYcBiAGJAYoBiwGMAY0BjgGPAZABkQGSAZMBlAGVAZYBlwGYAZkBmgGbAZwBnQGeAZ8BoAGhAaIBowGkAaUBpgGnAagBqQGqAasBrAZBYnJldmULdW5pMDA0QTAzMDEHdW5pMDIzNwt1bmkwMDZBMDMwMQNmX2YFZl9mX2kFZl9mX2wHemVyby50ZgZvbmUudGYGdHdvLnRmCHRocmVlLnRmB2ZvdXIudGYHZml2ZS50ZgZzaXgudGYIc2V2ZW4udGYIZWlnaHQudGYHbmluZS50Zgl6ZXJvLmRub20Ib25lLmRub20IdHdvLmRub20KdGhyZWUuZG5vbQlmb3VyLmRub20JZml2ZS5kbm9tCHNpeC5kbm9tCnNldmVuLmRub20KZWlnaHQuZG5vbQluaW5lLmRub20JemVyby5udW1yCG9uZS5udW1yCHR3by5udW1yCnRocmVlLm51bXIJZm91ci5udW1yCWZpdmUubnVtcghzaXgubnVtcgpzZXZlbi5udW1yCmVpZ2h0Lm51bXIJbmluZS5udW1yB3VuaTIwODAHdW5pMjA4MQd1bmkyMDgyB3VuaTIwODMHdW5pMjA4NAd1bmkyMDg1B3VuaTIwODYHdW5pMjA4Nwd1bmkyMDg4B3VuaTIwODkHdW5pMDBCOQd1bmkwMEIyB3VuaTAwQjMHdW5pMjA3NAd1bmkwMEEwDnBhcmVubGVmdC5kbm9tD3BhcmVucmlnaHQuZG5vbQ5wYXJlbmxlZnQubnVtcg9wYXJlbnJpZ2h0Lm51bXIWcGVyaW9kY2VudGVyZWQubG9jbENBVBtwZXJpb2RjZW50ZXJlZC5sb2NsQ0FULmNhc2UHdW5pMDBBRAd1bmkyMDhEB3VuaTIwOEUMcGFyZW5sZWZ0LnRmDXBhcmVucmlnaHQudGYERXVybwd1bmkyMjE1B3VuaTAwQjUHdW5pMDMwOAlncmF2ZWNvbWIJYWN1dGVjb21iCXRpbGRlY29tYgd1bmkwMzA0B3VuaTAzMjYHdW5pMDMzNwd1bmkwMzM4DHVuaTAzMDguY2FzZQ5ncmF2ZWNvbWIuY2FzZQ5hY3V0ZWNvbWIuY2FzZQx1bmkwMzAyLmNhc2UMdW5pMDMwNi5jYXNlDHVuaTAzMEEuY2FzZQ50aWxkZWNvbWIuY2FzZQx1bmkwMzA0LmNhc2UHdW5pMDJCQxVFdXJvLkJSQUNLRVQudmFyQWx0MDEUeWVuLkJSQUNLRVQudmFyQWx0MDEJLm5vdGRlZi4xA0EuMQhBYWN1dGUuMQhBYnJldmUuMQd1bmkwNUQwB3VuaUZCMkUHdW5pRkIyRgd1bmlGQjMwB3VuaTA1RDEHdW5pRkIzMQd1bmkwNUQyB3VuaUZCMzIHdW5pMDVEMwd1bmlGQjMzB3VuaTA1RDQHdW5pRkIzNAd1bmkwNUQ1B3VuaUZCMzUHdW5pRkI0Qgd1bmkwNUQ2B3VuaUZCMzYHdW5pMDVENwd1bmkwNUQ4B3VuaUZCMzgHdW5pMDVEOQd1bmlGQjM5B3VuaTA1REEHdW5pRkIzQQd1bmkwNURCB3VuaUZCM0IHdW5pMDVEQwd1bmlGQjNDB3VuaTA1REQHdW5pMDVERQd1bmlGQjNFB3VuaTA1REYHdW5pMDVFMAd1bmlGQjQwB3VuaTA1RTEHdW5pRkI0MQd1bmkwNUUyB3VuaTA1RTMHdW5pRkI0Mwd1bmkwNUU0B3VuaUZCNDQHdW5pMDVFNQd1bmkwNUU2B3VuaUZCNDYHdW5pMDVFNwd1bmlGQjQ3B3VuaTA1RTgHdW5pRkI0OAd1bmkwNUU5B3VuaUZCMkEHdW5pRkIyQgd1bmlGQjJDB3VuaUZCMkQHdW5pRkI0OQd1bmkwNUVBB3VuaUZCNEEHdW5pMDVG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ALv/8gDB/+QAwv/kAMP//gDE//4Axf/kAM7/0ADS//4A1P/+ANX//gDh/+QA4v/kAOj//QDq//0ACAA2/+gAOP/fAHX/+ADP/+kA2v/qANz/7ADe/+0A8//2AAcASP//AFcAIQDPADMA2gAvANwALwDeAC0A9QASAAcASP//AFcAIQDPADIA2gAuANwALgDeAC0A9QATAAkASP/mAHP/0ACB//cAgv/qAIX//QCK//cAu//+APH/5wDy/+cAFQA2/6gASP/+AHP/sQB//44AgP+NAIH//gCC/7UAhf/8AIj/6gCK/94Au//qAMj/xwDK/4EAzP+PAM//sADa//sA3P/8AN7//ADx//kA8v/5APP/jQAHAEj//wBXACEAzwAzANoAJwDcACgA3gAmAPUAKgAGADb//gBI//4AVwAuAHP//QCC//4Ahf/+AEAAAf/MAAL/zAAD/8wABP/MAAX/zAAG/8wAB//MAAj/zAAJ/8UAHP/0AB3/9AA2/+kAN///ADj/1QA5/+sAOv/rADv/+gA8//QAPf/0AD7/9AA///QAQP/0AEH/9ABC//QAQ//0AEX/+gBG//oAR//7AEj/7QBJ//oASv/6AEv/+gBM//oATf/6AE///wBRAAAAX//6AGD/+gBh//oAYv/6AGP/+gBk//oAZf/6AGb/+gBp//sAhP/+AIX//ACH//4Au//rAMH/yQDC/8kAxf/JAM7/xADP//EA0v/8ANT//ADV//wA2v/uANz/8ADe/+8A4f/JAOL/yQDu//UA8//6ACgAAf/oAAL/6AAD/+gABP/oAAX/6AAG/+gAB//oAAj/6AAw/+oANv/lADf/+AA4/8MAOf/PADr/zwA7//IAc///AHX/8wB2//wAd//8AHj//AB5//8AgP/4AMH/6wDC/+sAxf/rAMz//gDO/9sAz//dANr/2ADc/9oA3v/dAOH/6wDi/+sA4//7AOT/+gDl//sA5v/6AOv//ADs//wA8//nAAoANv/qADj/3gB1//gAiP/+AMwACwDP/+MA2v/mANz/6ADe/+kA8//wAAcANv/pAEj/9ADP/+gA2v/8ANz//ADe//wA8//2AAkANv/nADj/5QBz//8Adf/2AM//5gDa/+sA3P/tAN7/7QDz//IAFABH/8QASP+sAFL/6gBUADAAVQAoAFYAHQBX/+4AbP/lAHP/5wB1/+UAgf/+AIL//QCF/80Ah//aALv/6gDMAAYA7f/4AO7/7gDx//oA8v/6AAYAOP/6AEj//wB1//wA2v/+ANz//gDe//4AcwAB/8YAAv/GAAP/xgAE/8YABf/GAAb/xgAH/8YACP/GAAn/wAAL/+oADP/qABX/6gAc/+wAHf/sACP/6gAk/+oAJf/qACb/6gAn/+oAKP/qACn/6gAq/+oALf/qAC//6AA8/8MAPf/DAD7/wwA//8MAQP/DAEH/wwBC/8MAQ//DAEX/yQBG/8kAR//LAEj/wQBJ/8kASv/JAEv/yQBM/8kATf/JAE7/8QBP/80AUf/yAFL/3gBT//IAVAAlAFUAKgBWACMAWP/zAFn/8wBc/94AXf/eAF7/3gBf/8kAYP/JAGH/yQBi/8kAY//JAGT/yQBl/8kAZv/JAGf/3gBo/+kAaf/LAGr/3gBr/88AbP/pAG3/9ABu/+IAb//iAHD/4gBx/+IAcv/iAHP/7QB0/+4Adf/mAHb/6wB3/+sAeP/rAHn/4QB6//EAe//xAHz/8QB9//EAfv/xAIH/8ACC//MAg//xAIX/2ACG//AAh//dAIn/7wCK//QAu//nAMH/ygDC/8oAw//vAMT/7wDF/8oAyP/3AM7/tgDS/98A1P/fANX/3wDh/8oA4v/KAOf/5QDo//UA6f/lAOr/9QDt/+MA7v/gAPH/6gDy/+oACQBI/+gAVAAYAFUAIQBWACEAdf/6AIX//QCH//0Au//8AO7/9gBXAAv/3QAM/90AFf/dABz/9AAd//QAI//dACT/3QAl/90AJv/dACf/3QAo/90AKf/dACr/3QAt/90AL//oADH/+gAy//oAM//6ADT/+gA1//oAPP/5AD3/+QA+//kAP//5AED/+QBB//kAQv/5AEP/+QBF/+MARv/jAEf/5wBI/+UASf/jAEr/4wBL/+MATP/jAE3/4wBO/+EAT//eAFEAAABSABcAUwAXAFQAFwBVACYAVgAiAFj//gBZ//4AX//jAGD/4wBh/+MAYv/jAGP/4wBk/+MAZf/jAGb/4wBp/+cAa//0AG3/2gBu/+wAb//sAHD/7ABx/+wAcv/sAHP/zgB0/9cAdv/LAHf/ywB4/8sAev/hAHv/4QB8/+EAff/hAH7/4QCB//YAgv/pAIX//gCK//YAyP/4ANL/2wDU/9sA1f/bAOP/7wDl/+8A5//YAOn/2ADx/+cA8v/nABgAP/+pAED/pgBI/6cAVAAVAFUAJQBWACUAbP/5AHP/0AB1/8oAgf/rAIL/8QCD/+4Ahf+/AIb/8ACH/8UAif/sAIr/8wC7/+QAyP/1AO3/1gDu/9wA8f/eAPL/3gDzAAsABQBI//0Ac//3AIX//QDx//0A8v/9AAwANv/KAFcAKwBz/+8Af//uAID/6QDI/+wAzP/sAM//0gDa/+8A3P/yAN7/+gDz/9sADAA2/8oAVwArAHP/7wB//+4AgP/pAMj/7ADM/+wAz//FANr/7wDc//IA3v/6APP/2wANADb/0QA4/+oAc//wAHX/8QB//+4AgP/oAMj/8ADM/+0Az//IANr/1wDc/9kA3v/eAPP/2wATAHP/+AB1/+4Adv/3AHf/9wB4//cAef//AID/+QDB//4Awv/+AMX//gDM//kAzv/mAM//7ADa/+0A3P/uAN7/7wDh//4A4v/+APP/9QANADb/yAA4/+cAc//rAHX/7AB//+sAgP/lAMj/6QDM/+oAz//TANr/1wDc/9oA3v/eAPP/2AARADAAHAA2ACkANwAYADgAIQA5ACUAOgAlAEQAEABQABAAUQAQAFIAEABTABAAVAAQAFUAOQBWABAAVwApAFoAEABbABAAFwAwADAANgAlADcAGAA5ABwAOgAcAEQAGABQABgAUQAIAFIACABTAAgAVAAIAFUAKQBWAAgAVwAKAFoAGABbABgAxgAoAM8ABwDaADUA3AA0AN4AMwDzADcA9QAdABcAMAAlADYAKgA3ACEAOAApADkALQA6AC0ARAAYAFAAGABUAAgAVgAxAFoAGABbABgAfwAeAIAAKQDGACEAyAAVAMwAIgDPAC4A2gAuANwALQDeACwA8wAyAPUAFgAEADb/4ABUAAgAVgAIAFcADwAJADb/5QBI/+YAu//+AMz//wDP/9gA2v/6ANz//ADe//sA8//rAAsANv/KAHP/7wB//+8AgP/qAMj/7ADM/+wAz//FANr/7wDc//IA3v/6APP/3AANADb/yQA4/+MAc//sAHX/6gB//+wAgP/oAMj/6wDM/+sAz//FANr/1QDc/9cA3v/cAPP/2QANADb/yAA4/+cAc//rAHX/7AB//+sAgP/lAMj/6QDM/+oAz//FANr/1wDc/9oA3v/eAPP/2AANADb/ywA4/+cAc//tAHX/7QB//+wAgP/oAMj/7ADM/+sAz//GANr/2ADc/9oA3v/fAPP/2QAJADb/8QA4/8YASP/zALv/7gDP/+QA2v/WANz/2ADe/9kA8//1AA0ANv/JADj/9ABz/+wAdf/0AH//8ACA/+oAyP/xAMz/7gDP/8YA2v/gANz/4gDe/+cA8//cAB0ATv/7AG3//ABz//EAdP/0AHX/8AB2/+4Ad//uAHj/7gB5//wAev/7AHv/+wB8//sAff/7AH7/+wDB//4Awv/+AMX//gDO/+gAz//dANr/6ADc/+kA3v/qAOH//gDi//4A5P//AOb//wDr//8A7P//APP/8AAGADb/6gDP/9sA2v/8ANz//QDe//0A8//vAAgANv/eAFcAEQDM//4Az//TANr/8ADc//IA3v/7APP/6gA/AAH/1wAC/9cAA//XAAT/1wAF/9cABv/XAAf/1wAI/9cAHP/vAB3/7wAw/+4ANv/tADj/zwA5/9AAOv/QADv/9AA8/+gAPf/oAD7/6AA//+gAQP/oAEH/6ABC/+gAQ//oAEX/7ABG/+wAR//tAEj/4QBJ/+wASv/sAEv/7ABM/+wATf/sAE//7QBf/+wAYP/sAGH/7ABi/+wAY//sAGT/7ABl/+wAZv/sAGn/7QBr/+4Aef/4ALv/5wDB/9UAwv/VAMX/1QDO/8QAz//dANL/7wDU/+8A1f/vANr/1wDc/9kA3v/aAOH/1QDi/9UA5//9AOn//QDu//EA8//0AAoANv/uADj/2ABI/+kAu//rAM//3QDa/9sA3P/eAN7/3gDu//gA8//3AEQAC//4AAz/+AAV//gAHP/1AB3/9QAj//gAJP/4ACX/+AAm//gAJ//4ACj/+AAp//gAKv/4AC3/+AAv//wAMP/lADH//AAy//wAM//8ADT//AA1//wANv/mADf/+gA5/8sAOv/LADz/9AA9//QAPv/0AD//9ABA//QAQf/0AEL/9ABD//QARf/pAEb/6QBH/+wASP/lAEn/6QBK/+kAS//pAEz/6QBN/+kAT//pAF//6QBg/+kAYf/pAGL/6QBj/+kAZP/pAGX/6QBm/+kAaf/sAGv/9QBu//0Ab//9AHD//QBx//0Acv/9AM//2wDS/+oA1P/qANX/6gDa//oA3P/7AN7/+wDn//IA6f/yAPP/8AALADb/7QA4/88ASP/gALv/5wDIAAYAz//eANr/2ADc/9sA3v/bAO7/8ADz//YACAA2/9wASP/6AHP/+gDP/9EA2v/6ANz/+wDe//sA8//oAAsANgAHAEj/7gBR//8AVgAxAIAACAC7/+0AzAAHANoADADcAAsA3gAKAPMACwADADb/4ABUAAgAVgAIAAYAUQAAAFQAGABVABgAVgAYAMr/1wD1AD0ADQAB//gAAv/4AAP/+AAE//gABf/4AAb/+AAH//gACP/4ADD//gA2/+8AOP/1ADn/6gA6/+oAAwA2//AAOf/vADr/7wABADb/9wAFADD/5AA2/+AAN//+ADn/2wA6/9sAAwA2//cAOf/+ADr//gAFADD/2wA2/98AN//+ADn/1gA6/9YACAAB/88AAv/PAAP/zwAE/88ABf/PAAb/zwAH/88ACP/PAAMANv/uADn/6gA6/+oADwAB/94AAv/eAAP/3gAE/94ABf/eAAb/3gAH/94ACP/eABz//QAd//0ANv/0ADj/8wA5//QAOv/0ADv//gAcAAH/5wAC/+cAA//nAAT/5wAF/+cABv/nAAf/5wAI/+cACf/oADD/6gA2/+cAN//8ADn/5AA6/+QATv/wAFj//QBZ//0Abf/tAHP/5wB0/+sAdv/nAHf/5wB4/+cAev/wAHv/8AB8//AAff/wAH7/8AABADb/7wAEADb/ygBI//8AV//+AHP/1QAFADD/9QA2/+YAOf/XADr/1wBXACUAPQAL/94ADP/eABX/3gAc//AAHf/wACP/3gAk/94AJf/eACb/3gAn/94AKP/eACn/3gAq/94ALf/eAC//8QAw/7wAMf/dADL/3QAz/90ANP/dADX/3QA2/7gAN//eADn/rQA6/60ARf/wAEb/8ABH//UASP/yAEn/8ABK//AAS//wAEz/8ABN//AATv/oAFcALgBf//AAYP/wAGH/8ABi//AAY//wAGT/8ABl//AAZv/wAGn/9QBt/9MAbv/zAG//8wBw//MAcf/zAHL/8wBz/8MAdP/QAHb/xgB3/8YAeP/GAHr/6AB7/+gAfP/oAH3/6AB+/+gABABE/9cAUP/XAFr/1wBb/9cANQAB/8YAAv/GAAP/xgAE/8YABf/GAAb/xgAH/8YACP/GAAn/wQAwAAYAPP/qAD3/6gA+/+oAP//qAED/6gBB/+oAQv/qAEP/6gBF/+sARv/rAEf/6wBI/+EASf/rAEr/6wBL/+sATP/rAE3/6wBP/+4AVQAiAFgAAwBZAAMAXP/+AF3//gBe//4AX//rAGD/6wBh/+sAYv/rAGP/6wBk/+sAZf/rAGb/6wBn//4AaAAUAGn/6wBq//4Aa//wAGwAFABu//4Ab//+AHD//gBx//4Acv/+AAoAGgAxAED/0ABI/8sATf/MAFQADQBVADIAVgBXAFf/9QBz/90Adf/bAEgAC//kAAz/5AAV/+QAHP/0AB3/9AAj/+QAJP/kACX/5AAm/+QAJ//kACj/5AAp/+QAKv/kAC3/5AAv//MAMP+6ADH/4gAy/+IAM//iADT/4gA1/+IANv+2ADf/3QA5/6sAOv+rADz/9wA9//cAPv/3AD//9wBA//cAQf/3AEL/9wBD//cARf/nAEb/5wBH/+kASP/oAEn/5wBK/+cAS//nAEz/5wBN/+cATv/bAFcAOwBY//4AWf/+AF//5wBg/+cAYf/nAGL/5wBj/+cAZP/nAGX/5wBm/+cAaf/pAGv/8gBt/88Abv/oAG//6ABw/+gAcf/oAHL/6ABz/8QAdP/PAHb/zQB3/80AeP/NAHr/2wB7/9sAfP/bAH3/2wB+/9sABQA2/98AOP/bAFf/9gBz/+8Adf/qAGwAAf/6AAL/+gAD//oABP/6AAX/+gAG//oAB//6AAj/+gAJ//sACgAnAAv/5gAM/+YADQAnAA4AJwAPACcAEAAnABEAJwASACcAEwAnABQAJwAV/+YAFgAnABcAJwAYACcAGQAuABoAKgAbACcAHgAnAB8AJwAgACcAIQAnACIAJwAj/+YAJP/mACX/5gAm/+YAJ//mACj/5gAp/+YAKv/mACsAJwAsACcALf/mAC4AJwAv/+4AMf/+ADL//gAz//4ANP/+ADX//gA8/+QAPf/kAD7/5AA//+QAQP/kAEH/5ABC/+QAQ//kAEX/1QBG/9UAR//YAEj/3ABJ/9UASv/VAEv/1QBM/9UATf/VAE7/5gBRAAAAVAA2AFUALgBWAFEAVwBAAFz/7wBd/+8AXv/vAF//1QBg/9UAYf/VAGL/1QBj/9UAZP/VAGX/1QBm/9UAZ//vAGgABwBp/9gAav/vAGv/4ABsAAcAbf/lAG7/3QBv/90AcP/dAHH/3QBy/90Ac//XAHT/2wB1//oAdv/fAHf/3wB4/98Aef/6AHr/5gB7/+YAfP/mAH3/5gB+/+YAawAB//sAAv/7AAP/+wAE//sABf/7AAb/+wAH//sACP/7AAn//AAKACgAC//oAAz/6AANACgADgAoAA8AKAAQACgAEQAoABIAKAATACgAFAAoABX/6AAWACgAFwAoABgAKAAZAC8AGgArABsAKAAeACgAHwAoACAAKAAhACgAIgAoACP/6AAk/+gAJf/oACb/6AAn/+gAKP/oACn/6AAq/+gAKwAoACwAKAAt/+gALgAoAC//8AAx//4AMv/+ADP//gA0//4ANf/+ADz/5wA9/+cAPv/nAD//5wBA/+cAQf/nAEL/5wBD/+cARf/YAEb/2ABH/9oASP/dAEn/2ABK/9gAS//YAEz/2ABN/9gATv/nAFQANQBVAC0AVgBQAFcAPwBc//EAXf/xAF7/8QBf/9gAYP/YAGH/2ABi/9gAY//YAGT/2ABl/9gAZv/YAGf/8QBoAAcAaf/aAGr/8QBr/+MAbAAHAG3/5gBu/+AAb//gAHD/4ABx/+AAcv/gAHP/2QB0/94Adf/7AHb/4QB3/+EAeP/hAHn/+wB6/+cAe//nAHz/5wB9/+cAfv/nAGsAAf/7AAL/+wAD//sABP/7AAX/+wAG//sAB//7AAj/+wAJ//sACgAmAAv/6QAM/+kADQAmAA4AJgAPACYAEAAmABEAJgASACYAEwAmABQAJgAV/+kAFgAmABcAJgAYACYAGQAtABoAKQAbACYAHgAmAB8AJgAgACYAIQAmACIAJgAj/+kAJP/pACX/6QAm/+kAJ//pACj/6QAp/+kAKv/pACsAJgAsACYALf/pAC4AJgAv//IAMf/+ADL//gAz//4ANP/+ADX//gA8/+sAPf/rAD7/6wA//+sAQP/rAEH/6wBC/+sAQ//rAEX/3ABG/9wAR//fAEj/4QBJ/9wASv/cAEv/3ABM/9wATf/cAE7/6ABUADQAVQAsAFYAUABXAD4AXP/6AF3/+gBe//oAX//cAGD/3ABh/9wAYv/cAGP/3ABk/9wAZf/cAGb/3ABn//oAaAAGAGn/3wBq//oAa//nAGwABgBt/+cAbv/jAG//4wBw/+MAcf/jAHL/4wBz/9oAdP/eAHX/+wB2/+EAd//hAHj/4QB5//sAev/oAHv/6AB8/+gAff/oAH7/6AAFADD/yQA2/8oASP//AFf//gBz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"}   # Rubik = Hebrew

# ---------------------------------------------------------------------------
#  languages: English / Español / עברית
# ---------------------------------------------------------------------------
LANGS = [("EN", "ENGLISH"), ("ES", "ESPAÑOL"), ("HE", "עברית")]
TR = {"ES": {}, "HE": {}}
def tr(t):
    L = S.get("lang", "EN")
    if L == "EN" or not t: return t
    return TR[L].get(t, t)
def L(tmpl, *a):
    """Translate a template, then fill it: L("ROLLS: {0}", 12)"""
    return tr(tmpl).format(*a)
_HEB = re.compile(r"[\u0590-\u05FF]")
_LTR_RUN = re.compile(r"[A-Za-z0-9@#%][A-Za-z0-9@#.:/%+\-_',x ]*[A-Za-z0-9%@#!?]|[A-Za-z0-9@#%]")
_MIRROR = str.maketrans("()[]{}<>", ")(][}{><")
def bidi(t):
    """pygame draws left-to-right: put Hebrew in visual order (English/number runs stay readable)."""
    if not _HEB.search(t): return t
    v = t[::-1].translate(_MIRROR)
    return _LTR_RUN.sub(lambda m: m.group(0)[::-1].translate(_MIRROR), v)
TR_TABLE = [
    ('DEV PREVIEW  -  WINTER EVENT starts {0}', 'VISTA DEV  -  EL EVENTO DE INVIERNO empieza el {0}', 'תצוגת DEV  -  אירוע החורף מתחיל ב-{0}'),
    ('WINTER SHOP', 'TIENDA DE INVIERNO', 'חנות החורף'),
    ('WINTER BOX', 'CAJA DE INVIERNO', 'קופסת חורף'),
    ('WINTER BOX x3', 'CAJA DE INVIERNO x3', 'קופסת חורף x3'),
    ('GOLDEN WINTER BOX', 'CAJA DORADA DE INVIERNO', 'קופסת חורף מוזהבת'),
    ('One winter character, for sure', 'Un personaje de invierno, seguro', 'דמות חורף אחת, בטוח'),
    ('Three winter characters', 'Tres personajes de invierno', 'שלוש דמויות חורף'),
    ('Much better odds - never a PENGUIN', 'Mucha mejor suerte - nunca PENGUIN', 'סיכויים הרבה יותר טובים - אף פעם לא PENGUIN'),
    ('WINTER CHARACTERS', 'PERSONAJES DE INVIERNO', 'דמויות החורף'),
    ('Best: {0}', 'Mejor: {0}', 'הכי נדיר: {0}'),
    ('FROZEN SHADOW: {0}%', 'FROZEN SHADOW: {0}%', 'FROZEN SHADOW: {0}%'),
    ('GIFT OPENER', 'ABRE REGALOS', 'פותח מתנות'),
    ('Open 10 winter boxes', 'Abre 10 cajas de invierno', 'פתח 10 קופסאות חורף'),
    ('WINTER', 'INVIERNO', 'חורף'),
    ('PENGUIN', 'PINGÜINO', 'פינגווין'),
    ('SNOWMAN', 'MUÑECO DE NIEVE', 'איש שלג'),
    ('REINDEER', 'RENO', 'איל צפוני'),
    ('GINGERBREAD', 'GALLETA DE JENGIBRE', "עוגיית ג'ינג'ר"),
    ('FROZEN SHADOW', 'SOMBRA CONGELADA', 'צל קפוא'),
    ('MANGER', 'EL ENCARGADO', 'המנהל'),
    ('MAN STUDIO FRIEND', 'AMIGO DE MAN STUDIO', 'חבר של Man Studio'),
    ('THE SIGNAL', 'LA SEÑAL', 'האות'),
    ('Three short. Three long. Three short. Make them see you.', 'Tres cortas. Tres largas. Tres cortas. Que te vean.', 'שלוש קצרות. שלוש ארוכות. שלוש קצרות. שיראו אותך.'),
    ('SNOW DAY', 'DÍA DE NIEVE', 'יום שלג'),
    ('Find a WINTER character', 'Encuentra un personaje de INVIERNO', 'מצא דמות של החורף'),
    ('WINTER COMPLETE', 'INVIERNO COMPLETO', 'חורף מושלם'),
    ('Find all 5 WINTER characters', 'Encuentra los 5 personajes de INVIERNO', 'מצא את כל 5 דמויות החורף'),
    ('FRESH FROM THE OVEN', 'RECIÉN HORNEADA', 'ישר מהתנור'),
    ('Roll GINGERBREAD', 'Consigue GINGERBREAD', 'גלגל את GINGERBREAD'),
    ('FROZEN IN TIME', 'CONGELADO EN EL TIEMPO', 'קפוא בזמן'),
    ('Roll FROZEN SHADOW', 'Consigue FROZEN SHADOW', 'גלגל את FROZEN SHADOW'),
    ('DISTRESS SIGNAL', 'SEÑAL DE AUXILIO', 'קריאת מצוקה'),
    ('Send SOS with the lights', 'Envía SOS con la luz', 'שלח SOS עם האור'),
    ('GOOD COMPANY', 'BUENA COMPAÑÍA', 'חברה טובה'),
    ('Find MR_BURGER and LIA SAID', 'Encuentra a MR_BURGER y LIA SAID', 'מצא את MR_BURGER ואת LIA SAID'),
    ('WINTER EVENT  -  until {0}', 'EVENTO DE INVIERNO  -  hasta el {0}', 'אירוע החורף  -  עד {0}'),
    ('INDEX', 'ÍNDICE', 'אוסף'),
    ('BADGES', 'INSIGNIAS', 'תגים'),
    ('STATS', 'ESTADÍSTICAS', 'סטטיסטיקות'),
    ('LEADERBOARD', 'CLASIFICACIÓN', 'טבלת שיאים'),
    ('LUCK SHOP', 'TIENDA DE SUERTE', 'חנות מזל'),
    ('SETTINGS', 'AJUSTES', 'הגדרות'),
    ('SIGN IN', 'ENTRAR', 'התחברות'),
    ('SIGN OUT', 'SALIR', 'התנתקות'),
    ('BACK', 'ATRÁS', 'חזרה'),
    ('NEXT', 'SIGUIENTE', 'הבא'),
    ('SKIP', 'SALTAR', 'דלג'),
    ("LET'S ROLL!", '¡A TIRAR!', 'בוא נגלגל!'),
    ('AUTO: ON', 'AUTO: SÍ', 'אוטומטי: פועל'),
    ('AUTO: OFF', 'AUTO: NO', 'אוטומטי: כבוי'),
    ('LUCK  x{0}', 'SUERTE  x{0}', 'מזל  x{0}'),
    ('BONUS ROLL x2', 'TIRADA BONUS x2', 'גלגול בונוס x2'),
    ('LUCKY ROLL x{0}', 'TIRADA DE SUERTE x{0}', 'גלגול מזל x{0}'),
    ('BOOST x2  {0}s', 'BOOST x2  {0}s', "בוסט x2  {0} שנ'"),
    ('MEGA x{0}  {1}s', 'MEGA x{0}  {1}s', "מגה x{0}  {1} שנ'"), ('MEGA BOOST', 'MEGA BOOST', 'מגה בוסט'),
    ('Next BONUS ROLL in {0} rolls', 'Próxima TIRADA BONUS en {0} tiradas', 'גלגול בונוס בעוד {0} גלגולים'),
    ('No companion yet', 'Aún sin compañero', 'עוד אין חבר'),
    ('Pick one in the INDEX', 'Elige uno en el ÍNDICE', 'בחר אחד באוסף'),
    ('YOUR RAREST', 'TU MÁS RARO', 'הכי נדיר שלך'),
    ('GUEST  -  sign in for coins', 'INVITADO  -  entra para usar monedas', 'אורח  -  התחבר בשביל מטבעות'),
    ('ROLLS: {0}', 'TIRADAS: {0}', 'גלגולים: {0}'),
    ('GLOBAL  -  RARE ROLLS', 'GLOBAL  -  TIRADAS RARAS', 'עולמי  -  גלגולים נדירים'),
    ('{0} rolled {1}  ({2})', '{0} sacó {1}  ({2})', '{0} הוציא את {1}  ({2})'),
    ('1 in {0}', '1 en {0}', '1 ל-{0}'),
    ('SECRET', 'SECRETO', 'סוד'),
    ('1 in 1,000,000...?', '1 en 1.000.000...?', '1 למיליון...?'),
    ('SOMETHING RARE IS COMING...', 'ALGO RARO SE ACERCA...', 'משהו נדיר מגיע...'),
    ('YOU ROLLED THE DEVS!', '¡TE TOCARON LOS DEVS!', 'הוצאת את המפתחים!'),
    ('A DEVELOPER APPEARED!', '¡APARECIÓ UN DESARROLLADOR!', 'מפתחת הופיעה!'),
    ('NEW!', '¡NUEVO!', 'חדש!'),
    ('luck x{0}', 'suerte x{0}', 'מזל x{0}'),
    ('click to continue', 'haz clic para continuar', 'לחץ כדי להמשיך'),
    ('SECRET FOUND!', '¡SECRETO ENCONTRADO!', 'מצאת סוד!'),
    ('CLICK... CLICK... CLICK...', 'CLIC... CLIC... CLIC...', 'קליק... קליק... קליק...'),
    ('38 YEARS LATER...', '38 AÑOS DESPUÉS...', '38 שנה אחר כך...'),
    ('SOMETHING WOKE UP.', 'ALGO DESPERTÓ.', 'משהו התעורר.'),
    ('BONES.', 'HUESOS.', 'עצמות.'),
    ('HE HEARD YOU.', 'TE ESCUCHÓ.', 'הוא שמע אותך.'),
    ('{0} / {1} FOUND', '{0} / {1} ENCONTRADOS', 'נמצאו {0} / {1}'),
    ('Pick a character', 'Elige un personaje', 'בחר דמות'),
    ('Found {0} time  •  first: {1}', 'Encontrado {0} vez  •  primera: {1}', 'נמצא פעם {0}  •  לראשונה: {1}'),
    ('Found {0} times  •  first: {1}', 'Encontrado {0} veces  •  primera: {1}', 'נמצא {0} פעמים  •  לראשונה: {1}'),
    ('COMPANION', 'COMPAÑERO', 'החבר שלך'),
    ('SET COMPANION', 'ELEGIR COMPAÑERO', 'בחר כחבר'),
    ('HINT: ', 'PISTA: ', 'רמז: '),
    ('Keep rolling...', 'Sigue tirando...', 'תמשיך לגלגל...'),
    ('38 years later, the gears still turn...', '38 años después, los engranajes siguen girando...', '38 שנה אחר כך, גלגלי השיניים עדיין מסתובבים...'),
    ("Turn off the lights. Spell what's left of him.", 'Apaga la luz. Deletrea lo que queda de él (en inglés).', 'כבו את האור. תאייתו את מה שנשאר ממנו (באנגלית).'),
    ('FIRST ROLL', 'PRIMERA TIRADA', 'גלגול ראשון'),
    ('Roll for the first time', 'Tira por primera vez', 'גלגל בפעם הראשונה'),
    ('ROLLER', 'TIRADOR', 'גלגלן'),
    ('Roll 100 times', 'Tira 100 veces', 'גלגל 100 פעמים'),
    ('DICE MASTER', 'MAESTRO DE DADOS', 'אלוף הקוביות'),
    ('Roll 1,000 times', 'Tira 1.000 veces', 'גלגל 1,000 פעמים'),
    ('LEGENDARY PULL', 'TIRADA LEGENDARIA', 'שליפה אגדית'),
    ('Find a LEGENDARY character', 'Encuentra un personaje LEGENDARY', 'מצא דמות LEGENDARY'),
    ('HE IS COMING', 'ÉL VIENE', 'הוא מגיע'),
    ('Find a character from the TAPES', 'Encuentra un personaje de las TAPES', 'מצא דמות מה-TAPES'),
    ('MYTHIC', 'MYTHIC', 'MYTHIC'),
    ('Find a MYTHIC character', 'Encuentra un personaje MYTHIC', 'מצא דמות MYTHIC'),
    ('TESTED BY LUNA', 'PROBADO POR LUNA', 'נבדק על ידי לונה'),
    ('Roll LUNAVR_TESTER', 'Saca a LUNAVR_TESTER', 'הוצא את LUNAVR_TESTER'),
    ('YOU ROLLED THE DEVS', 'TE TOCARON LOS DEVS', 'הוצאת את המפתחים'),
    ('Roll MAN STUDIO (1 in 1,000,000)', 'Saca a MAN STUDIO (1 en 1.000.000)', 'הוצא את MAN STUDIO (1 למיליון)'),
    ('EGG HUNTER', 'CAZADOR DE SECRETOS', 'צייד ביצים'),
    ('Find a SECRET character', 'Encuentra un personaje SECRETO', 'מצא דמות סודית'),
    ('NOTHING STAYS HIDDEN', 'NADA SE QUEDA OCULTO', 'שום דבר לא נשאר נסתר'),
    ('Find both SECRET characters', 'Encuentra los dos personajes SECRETOS', 'מצא את שתי הדמויות הסודיות'),
    ('COMPLETE INDEX', 'ÍNDICE COMPLETO', 'אוסף מלא'),
    ('Find all 37 characters', 'Encuentra los 37 personajes', 'מצא את כל 37 הדמויות'),
    ('TESTER.COM', 'TESTER.COM', 'TESTER.COM'),
    ('Man Studio team only', 'Solo el equipo de Man Studio', 'רק לצוות של Man Studio'),
    ('BADGE UNLOCKED', 'INSIGNIA DESBLOQUEADA', 'תג חדש!'),
    ('TOTAL ROLLS', 'TIRADAS TOTALES', 'סה"כ גלגולים'),
    ('CHARACTERS', 'PERSONAJES', 'דמויות'),
    ('TIME PLAYED', 'TIEMPO JUGADO', 'זמן משחק'),
    ('DAYS PLAYED', 'DÍAS JUGADOS', 'ימי משחק'),
    ('LUCKIEST ROLL', 'TIRADA MÁS SUERTUDA', 'הגלגול הכי מוצלח'),
    ('BEST LUCK', 'MEJOR SUERTE', 'המזל הכי גבוה'),
    ('LUCKY ROLLS', 'TIRADAS DE SUERTE', 'גלגולי מזל'),
    ('BONUS ROLLS', 'TIRADAS BONUS', 'גלגולי בונוס'),
    ('AUTO ROLLS', 'TIRADAS AUTO', 'גלגולים אוטומטיים'),
    ('COINS SPENT', 'MONEDAS GASTADAS', 'מטבעות שהוצאת'),
    ('SINCE LEGENDARY+', 'DESDE LEGENDARY+', 'מאז LEGENDARY+'),
    ('LONGEST DRY RUN', 'RACHA SECA MÁS LARGA', 'הרצף הכי ארוך בלי'),
    ('{0} rolls', '{0} tiradas', '{0} גלגולים'),
    ('ROLLS BY RARITY', 'TIRADAS POR RAREZA', 'גלגולים לפי נדירות'),
    ('MOST FOUND: {0} x{1}', 'MÁS ENCONTRADO: {0} x{1}', 'הכי הרבה: {0} x{1}'),
    ('RAREST: {0}  ({1})', 'MÁS RARO: {0}  ({1})', 'הכי נדיר: {0}  ({1})'),
    ('Coins from Color Under Pressure: ', 'Monedas de Color Under Pressure: ', 'מטבעות מ-Color Under Pressure: '),
    ('Sign in with your Color Under Pressure account to use your coins', 'Entra con tu cuenta de Color Under Pressure para usar tus monedas', 'התחבר עם החשבון של Color Under Pressure כדי להשתמש במטבעות'),
    ('Sign in with your Color Under Pressure account to use coins', 'Entra con tu cuenta de Color Under Pressure para usar monedas', 'התחבר עם החשבון של Color Under Pressure כדי להשתמש במטבעות'),
    ('LUCKY ROLL', 'TIRADA DE SUERTE', 'גלגול מזל'),
    ('SUPER LUCKY ROLL', 'SÚPER TIRADA DE SUERTE', 'גלגול סופר מזל'),
    ('LUCK BOOST', 'BOOST DE SUERTE', 'בוסט מזל'),
    ('Next roll: x10 luck', 'Próxima tirada: suerte x10', 'הגלגול הבא: מזל x10'),
    ('Next roll: x100 luck', 'Próxima tirada: suerte x100', 'הגלגול הבא: מזל x100'),
    ('x2 luck for 5 minutes', 'Suerte x2 durante 5 minutos', 'מזל x2 ל-5 דקות'),
    ('{0} COINS', '{0} MONEDAS', '{0} מטבעות'),
    ('Free rolls never cost anything. Coins only make you luckier.', 'Las tiradas gratis nunca cuestan nada. Las monedas solo te dan más suerte.', 'גלגולים חינמיים תמיד חינם. מטבעות רק נותנים עוד מזל.'),
    ('{0}!  -{1} coins', '¡{0}!  -{1} monedas', '{0}!  -{1} מטבעות'),
    ('Not enough coins ({0})', 'No tienes suficientes monedas ({0})', 'אין מספיק מטבעות ({0})'),
    ('YOUR ITEMS', 'TUS OBJETOS', 'הפריטים שלך'),
    ('USE {0} x{1}', 'USAR {0} x{1}', 'השתמש: {0} x{1}'),
    ('{0} is ON!', '¡{0} activado!', '{0} פועל!'),
    ('HAVE A CODE?', '¿TIENES UN CÓDIGO?', 'יש לך קוד?'),
    ('type it here', 'escríbelo aquí', 'כתוב אותו כאן'),
    ('REDEEM', 'CANJEAR', 'הפעל'),
    ('Sign in to use codes', 'Entra para usar códigos', 'התחבר כדי להשתמש בקודים'),
    ("This code doesn't exist", 'Este código no existe', 'הקוד הזה לא קיים'),
    ("This code isn't active yet", 'Este código aún no está activo', 'הקוד הזה עוד לא פעיל'),
    ('This code expired', 'Este código expiró', 'הקוד הזה פג תוקף'),
    ('You already used this code', 'Ya usaste este código', 'כבר השתמשת בקוד הזה'),
    ('CODE ACCEPTED!  {0}', '¡CÓDIGO ACEPTADO!  {0}', 'הקוד התקבל!  {0}'),
    ('MUSIC', 'MÚSICA', 'מוזיקה'),
    ('SOUNDS', 'SONIDOS', 'צלילים'),
    ('LANGUAGE', 'IDIOMA', 'שפה'),
    ('SCREEN', 'PANTALLA', 'מסך'),
    ('FULLSCREEN: ON', 'PANTALLA COMPLETA: SÍ', 'מסך מלא: פועל'),
    ('FULLSCREEN: OFF', 'PANTALLA COMPLETA: NO', 'מסך מלא: כבוי'),
    ('ACCOUNT', 'CUENTA', 'חשבון'),
    ('HELP', 'AYUDA', 'עזרה'),
    ('TUTORIAL', 'TUTORIAL', 'הדרכה'),
    ('Your coins and account are the same as in Color Under Pressure.', 'Tus monedas y tu cuenta son las mismas que en Color Under Pressure.', 'המטבעות והחשבון שלך זהים לאלה של Color Under Pressure.'),
    ('Signed out', 'Sesión cerrada', 'התנתקת'),
    ('Use your Color Under Pressure account (same name + password)', 'Usa tu cuenta de Color Under Pressure (mismo nombre + contraseña)', 'השתמש בחשבון של Color Under Pressure (אותו שם + סיסמה)'),
    ('NAME', 'NOMBRE', 'שם'),
    ('PASSWORD', 'CONTRASEÑA', 'סיסמה'),
    ('Write your name and password', 'Escribe tu nombre y contraseña', 'כתוב שם וסיסמה'),
    ('Welcome, {0}!', '¡Bienvenido, {0}!', 'ברוך הבא, {0}!'),
    ('No connection', 'Sin conexión', 'אין חיבור'),
    ('Wrong password', 'Contraseña incorrecta', 'סיסמה שגויה'),
    ('Sign in failed', 'No se pudo entrar', 'ההתחברות נכשלה'),
    ('No account with this name. Make one in Color Under Pressure!', 'No hay cuenta con ese nombre. ¡Crea una en Color Under Pressure!', 'אין חשבון בשם הזה. תפתח אחד ב-Color Under Pressure!'),
    ('COMING OCTOBER 13, 2026', 'LLEGA EL 13 DE OCTUBRE DE 2026', 'מגיע ב-13 באוקטובר 2026'),
    ('{0} days to go', 'faltan {0} días', 'עוד {0} ימים'),
    ('WELCOME TO RNG!', '¡BIENVENIDO A RNG!', 'ברוכים הבאים ל-RNG!'),
    ('One button. One roll. Who will you get?', 'Un botón. Una tirada. ¿Quién te tocará?', 'כפתור אחד. גלגול אחד. מי ייצא לך?'),
    ('Pick your language:', 'Elige tu idioma:', 'בחר שפה:'),
    ('PRESS ROLL', 'PULSA ROLL', 'לחץ ROLL'),
    ('Every roll gives you a random character.', 'Cada tirada te da un personaje al azar.', 'כל גלגול נותן לך דמות אקראית.'),
    ('Free roll every 2 seconds. SPACE also rolls.', 'Tirada gratis cada 2 segundos. ESPACIO también tira.', 'גלגול חינם כל 2 שניות. גם רווח מגלגל.'),
    ('Turn on AUTO and just watch.', 'Activa AUTO y solo mira.', 'תפעיל AUTO ופשוט תסתכל.'),
    ('RARITY & LUCK', 'RAREZA Y SUERTE', 'נדירות ומזל'),
    ('Every character has odds, like 1 in 400.', 'Cada personaje tiene una probabilidad, como 1 en 400.', 'לכל דמות יש סיכוי, למשל 1 ל-400.'),
    ('More LUCK = rare characters show up more.', 'Más SUERTE = salen más personajes raros.', 'יותר מזל = יותר דמויות נדירות.'),
    ('Every 10th roll = BONUS ROLL x2.', 'Cada 10 tiradas = TIRADA BONUS x2.', 'כל גלגול עשירי = גלגול בונוס x2.'),
    ('Coins from Color Under Pressure buy more luck.', 'Las monedas de Color Under Pressure compran más suerte.', 'במטבעות מ-Color Under Pressure קונים עוד מזל.'),
    ('COLLECT THEM ALL', '¡CONSÍGUELOS TODOS!', 'תאסוף את כולם'),
    ('INDEX: every character you found.', 'ÍNDICE: todos los personajes que encontraste.', 'אוסף: כל הדמויות שמצאת.'),
    ('Pick a COMPANION to stand next to you.', 'Elige un COMPAÑERO que esté a tu lado.', 'בחר חבר שיעמוד לידך.'),
    ('BADGES, STATS and the LEADERBOARD.', 'INSIGNIAS, ESTADÍSTICAS y la CLASIFICACIÓN.', 'תגים, סטטיסטיקות וטבלת שיאים.'),
    ('2 SECRET characters are hidden. Look carefully...', 'Hay 2 personajes SECRETOS escondidos. Mira bien...', '2 דמויות סודיות מוסתרות. תסתכל טוב...'),
    ('RAREST ROLL', 'TIRADA MÁS RARA', 'הגלגול הכי נדיר'),
    ('MOST CHARACTERS', 'MÁS PERSONAJES', 'הכי הרבה דמויות'),
    ('MOST ROLLS', 'MÁS TIRADAS', 'הכי הרבה גלגולים'),
    ('Loading...', 'Cargando...', 'טוען...'),
    ('Nobody here yet. Be the first!', 'Aún no hay nadie. ¡Sé el primero!', 'עוד אין פה אף אחד. תהיה הראשון!'),
    ('REFRESH', 'ACTUALIZAR', 'רענון'),
    ('Sign in to get on the leaderboard!', '¡Entra para aparecer en la clasificación!', 'התחבר כדי להיכנס לטבלה!'),
    ('DEV accounts are not on the leaderboard (they can force rolls).', 'Las cuentas DEV no salen en la clasificación (pueden forzar tiradas).', 'חשבונות DEV לא בטבלה (הם יכולים לבחור דמות).'),
    ('DEV  -  FORCE NEXT ROLL', 'DEV  -  FORZAR SIGUIENTE TIRADA', 'DEV  -  לבחור את הגלגול הבא'),
    ('RESET MY PROGRESS', 'BORRAR MI PROGRESO', 'לאפס את ההתקדמות'),
    ('SHINY!', '¡BRILLANTE!', 'נוצץ!'), ('Roll a SHINY character (1 in 50)', 'Saca un personaje BRILLANTE (1 en 50)', 'הוצא דמות נוצצת (1 ל-50)'),
    ('SPARKLE COLLECTOR', 'COLECCIONISTA DE BRILLOS', 'אספן נצנצים'), ('Find 10 different SHINY characters', 'Encuentra 10 personajes BRILLANTES distintos', 'מצא 10 דמויות נוצצות שונות'),
    ('EVERY DAY', 'TODOS LOS DÍAS', 'כל יום'), ('Claim the daily gift 7 days in a row', 'Reclama el regalo diario 7 días seguidos', 'קח את המתנה היומית 7 ימים ברצף'),
    ('DAILY GIFT!', '¡REGALO DIARIO!', 'מתנה יומית!'), ('DAILY GIFT: {0}', 'REGALO DIARIO: {0}', 'מתנה יומית: {0}'), ('(day {0})', '(día {0})', '(יום {0})'),
    ('SHINY x{0}', 'BRILLANTE x{0}', 'נוצץ x{0}'), ('SHINIES', 'BRILLANTES', 'נוצצים'),
    ('DEMO  -  {0} rolls left', 'DEMO  -  quedan {0} tiradas', 'דמו  -  נשארו {0} גלגולים'),
    ('THE DEMO IS OVER!', '¡LA DEMO TERMINÓ!', 'הדמו נגמר!'),
    ('You found {0} characters. Want to keep rolling?', 'Encontraste {0} personajes. ¿Quieres seguir tirando?', 'מצאת {0} דמויות. רוצה להמשיך לגלגל?'),
    ('Sign in with your Color Under Pressure account. Your characters come with you!', 'Entra con tu cuenta de Color Under Pressure. ¡Tus personajes vienen contigo!', 'התחבר עם החשבון של Color Under Pressure. הדמויות שלך עוברות איתך!'),
    ('No account? Make one for free in Color Under Pressure.', '¿Sin cuenta? Crea una gratis en Color Under Pressure.', 'אין חשבון? אפשר לפתוח בחינם ב-Color Under Pressure.'),
    ('LATER', 'LUEGO', 'אחר כך'),
    ('Progress reset', 'Progreso borrado', 'ההתקדמות אופסה'),
    ('MY CHARACTERS', 'MIS PERSONAJES', 'הדמויות שלי'),
    ('{0} characters  •  {1} in total  •  worth {2} coins', '{0} personajes  •  {1} en total  •  valen {2} monedas', '{0} דמויות  •  {1} בסך הכל  •  שווים {2} מטבעות'),
    ('Sell {0}x {1}?', '¿Vender {0}x {1}?', 'למכור {0}x {1}?'), ('+{0} coins', '+{0} monedas', '+{0} מטבעות'),
    ('YES, SELL', 'SÍ, VENDER', 'כן, למכור'), ('NO', 'NO', 'לא'),
    ('Roll to get characters!', '¡Tira para conseguir personajes!', 'תגלגלו כדי לקבל דמויות!'),
    ('You have {0}', 'Tienes {0}', 'יש לך {0}'), ('Worth {0} coins each', 'Vale {0} monedas cada uno', 'שווה {0} מטבעות כל אחד'),
    ("Secret characters can't be sold", 'Los personajes secretos no se venden', 'אי אפשר למכור דמויות סודיות'),
    ('Sign in to sell characters', 'Inicia sesión para vender personajes', 'צריך להתחבר כדי למכור דמויות'),
    ('SELL 1   +{0}', 'VENDER 1   +{0}', 'למכור 1   +{0}'), ('SELL ALL BUT 1   +{0}', 'VENDER TODOS MENOS 1   +{0}', 'למכור הכל חוץ מ-1   +{0}'),
    ('SELL ALL   +{0}', 'VENDER TODOS   +{0}', 'למכור הכל   +{0}'),
    ("This is your companion: you can't sell the last one", 'Es tu compañero: no puedes vender el último', 'זה החבר שלך: אי אפשר למכור את האחרון'),
    ('Every NEW character = +{0} coins', 'Cada personaje NUEVO = +{0} monedas', 'כל דמות חדשה = +{0} מטבעות'),
    ('NEW CHARACTER!  +{0} coins', '¡PERSONAJE NUEVO!  +{0} monedas', 'דמות חדשה!  +{0} מטבעות'),
    ('Sold {0}x {1}  +{2} coins', 'Vendiste {0}x {1}  +{2} monedas', 'נמכר {0}x {1}  +{2} מטבעות'),
    ('Pick a character', 'Elige un personaje', 'בחרו דמות'),
    ('COINS SPENT / EARNED', 'MONEDAS GASTADAS / GANADAS', 'מטבעות שהוצאו / הרווחו'),
    ('AUTO ROLL: no mouse or keys for 2 hours = disconnected', 'AUTO: sin ratón ni teclas 2 horas = desconectado', 'גלגול אוטומטי: שעתיים בלי עכבר או מקלדת = ניתוק'),
    ('Move the mouse!  Disconnect in {0}', '¡Mueve el ratón!  Desconexión en {0}', 'תזיזו את העכבר!  ניתוק בעוד {0}'),
    ('DISCONNECTED', 'DESCONECTADO', 'נותקת'),
    ("You didn't move the mouse or press a key for 2 hours.", 'No moviste el ratón ni pulsaste una tecla en 2 horas.', 'לא הזזת את העכבר ולא לחצת על מקש שעתיים.'),
    ('AUTO ROLL was stopped.', 'Se detuvo el AUTO.', 'הגלגול האוטומטי נעצר.'), ('Click to continue', 'Haz clic para continuar', 'לחצו כדי להמשיך'),
]
for _en, _es, _he in TR_TABLE: TR['ES'][_en] = _es; TR['HE'][_en] = _he
def _prep(name, size, text):
    t = tr(str(text))
    if _HEB.search(t): return "rubik", max(8, int(size * 0.95)), bidi(t)
    return name, size, t
_fonts = {}
def font(name, size):
    k = (name, size)
    if k not in _fonts:
        try: _fonts[k] = pygame.font.Font(io.BytesIO(base64.b64decode(FONT_DATA[name])), size)
        except Exception: _fonts[k] = pygame.font.SysFont("arial", size, bold=True)
    return _fonts[k]
_tc = {}
def txt(name, size, text, col=(255, 255, 255)):
    k = (name, size, text, col, S.get("lang"))
    if k not in _tc:
        if len(_tc) > 3000: _tc.clear()
        fn, sz, t = _prep(name, size, text)
        _tc[k] = font(fn, sz).render(t, True, col)
    return _tc[k]
def fit(name, size, text, maxw, col=(255, 255, 255)):
    while size > 8:
        fn, sz, t = _prep(name, size, text)
        if font(fn, sz).size(t)[0] <= maxw: break
        size -= 2
    return txt(name, size, text, col)
def blit(surf, img, pos, anchor="center", alpha=255):
    if alpha <= 0: return
    r = img.get_rect(**{anchor: pos})
    if alpha < 255: img = img.copy(); img.set_alpha(int(alpha))
    surf.blit(img, r); return r

WHITE = (255, 255, 255)
def mix(a, b, k): k = max(0.0, min(1.0, k)); return tuple(int(a[i] + (b[i] - a[i]) * k) for i in range(3))
def clamp(x, a=0.0, b=1.0): return max(a, min(b, x))
def eo(x): x = clamp(x); return 1 - (1 - x) ** 3
def eob(x): x = clamp(x); c = 1.9; return 1 + (c + 1) * (x - 1) ** 3 + c * (x - 1) ** 2

_glow = {}
def glow(s, col, x, y, r, a=60, n=6):
    k = (col, r, a, n)
    if k not in _glow:
        sm = pygame.Surface((48, 48), pygame.SRCALPHA)            # smooth light, no rings
        for yy in range(48):
            for xx in range(48):
                d = min(1.0, math.hypot(xx - 23.5, yy - 23.5) / 24)
                sm.set_at((xx, yy), col + (int(min(255, a * 1.6) * (1 - d) ** 2),))
        g = pygame.transform.smoothscale(sm, (max(2, r * 2), max(2, r * 2)))
        if len(_glow) > 400: _glow.clear()
        _glow[k] = g
    s.blit(_glow[k], (int(x - r), int(y - r)))

CVALS = [(235, 64, 64), (60, 120, 255), (60, 200, 100), (250, 210, 50), (170, 90, 240), (255, 140, 40), (255, 105, 180), (60, 220, 230)]

# ---------------------------------------------------------------------------
#  sound (generated - original)
# ---------------------------------------------------------------------------
try:
    import numpy as np
except Exception:
    np = None
SR = 44100
def _snd(arr):
    if np is None: return None
    a = np.clip(arr, -1, 1); a = (a * 32767).astype(np.int16)
    try: return pygame.sndarray.make_sound(np.ascontiguousarray(np.column_stack([a, a])))
    except Exception: return None
def _env(n, a=0.003, d=0.2): t = np.arange(n) / SR; return np.minimum(1, t / a) * np.exp(-t / d)
def _tone(f, dur, kind="sine", g=0.3, d=0.2):
    n = int(dur * SR); t = np.arange(n) / SR
    if kind == "square": x = np.sign(np.sin(2 * np.pi * f * t)) * 0.5
    else: x = np.sin(2 * np.pi * f * t) + 0.4 * np.sin(4 * np.pi * f * t) * np.exp(-t * 8)
    return x * _env(n, 0.003, d) * g
def _mf(m): return 440 * 2 ** ((m - 69) / 12)
SND = {}
def make_sounds():
    if np is None: return
    SND["tick"] = _snd(_tone(1400, 0.04, "square", 0.12, 0.02))
    SND["click"] = _snd(_tone(800, 0.06, "square", 0.12, 0.03))
    def chord(notes, g=0.22, d=0.6, gap=0.05):
        L = int(SR * (gap * len(notes) + d * 2)); out = np.zeros(L)
        for i, m in enumerate(notes):
            x = _tone(_mf(m), d * 2, "sine", g, d); s0 = int(i * gap * SR); out[s0:s0 + len(x)] += x
        return out
    SND["common"] = _snd(chord([72], 0.25, 0.25))
    SND["rare"] = _snd(chord([72, 79], 0.22, 0.35))
    SND["epic"] = _snd(chord([72, 76, 79, 84], 0.18, 0.5))
    SND["legendary"] = _snd(chord([72, 76, 79, 84, 88, 91], 0.16, 0.8, 0.07))
    n = int(SR * 1.2); t = np.arange(n) / SR; f = 50 + 140 * np.exp(-t * 12)
    boom = np.sin(2 * np.pi * np.cumsum(f) / SR) * np.exp(-t * 3) * 0.8 + np.random.randn(n) * np.exp(-t * 9) * 0.25
    SND["boom"] = _snd(boom)
    n = int(SR * 0.6); glitch = np.sign(np.sin(2 * np.pi * np.cumsum(np.random.choice([90, 200, 400, 1200], n)) / SR)) * 0.25 * np.exp(-np.arange(n) / SR * 4)
    SND["glitch"] = _snd(glitch)
    n = int(SR * 2.5); t = np.arange(n) / SR
    SND["rise"] = _snd(np.random.randn(n) * (t / 2.5) ** 2 * 0.25 + np.sin(2 * np.pi * np.cumsum(110 * (1 + t)) / SR) * 0.15 * t / 2.5)
    SND["badge"] = _snd(chord([79, 84, 88], 0.2, 0.4, 0.08))
    SND["error"] = _snd(_tone(180, 0.25, "square", 0.15, 0.1))
def play(name):
    s = SND.get(name)
    if s:
        s.set_volume(S.get("sfx", 0.8)); s.play()

MUSIC = {"snd": None, "ch": None}
def make_music():
    """A calm 16-bar loop (original). In the winter event: a warmer song with bells, 96 bpm."""
    if np is None: return
    win = winter_now()
    bpm = 96 if win else 110
    B = 60 / bpm; L = int(SR * B * 32); out = np.zeros(L)
    def add(x, t):
        i = int(t * SR); j = min(L, i + len(x)); out[i:j] += x[:j - i]
    if win:
        prog = [(50, (62, 65, 69)), (57, (60, 64, 69)), (55, (59, 62, 67)), (53, (57, 60, 65))]
    else:
        prog = [(57, (69, 72, 76)), (53, (65, 69, 72)), (48, (64, 67, 72)), (55, (62, 67, 71))]
    for bar in range(8):
        root, ch = prog[bar % 4]
        for b in range(4):
            tb = (bar * 4 + b) * B
            add(_tone(_mf(root - 12), B * 0.95, "sine", 0.22, 0.35), tb)
            for k in range(2):
                add(_tone(_mf(ch[(b * 2 + k) % 3] + 12), B / 2, "square", 0.035, 0.12), tb + k * B / 2)
            n = int(0.05 * SR); add(np.random.randn(n) * np.exp(-np.arange(n) / SR * 80) * 0.05, tb + B / 2)
            if win:                                      # sleigh bells on the off-beats
                nb = int(0.09 * SR)
                bell = np.random.randn(nb) * np.exp(-np.arange(nb) / SR * 55) * 0.045
                bell += _tone(_mf(ch[0] + 36), 0.09, "sine", 0.025, 0.06)[:nb]
                add(bell, tb + B * 0.5)
                add(_tone(_mf(ch[(b + bar) % 3] + 24), B * 0.45, "sine", 0.05, 0.22), tb + B * 0.25)
        add(_tone(_mf(ch[0] + 24), B * 3, "sine", 0.05, 1.2), bar * 4 * B)
    d = int(0.21 * SR); wet = np.zeros(L); wet[d:] += out[:-d] * (0.42 if win else 0.3)
    out = np.tanh((out + wet) * 1.2) * 0.6
    MUSIC["snd"] = _snd(out)
    if MUSIC["snd"]:
        MUSIC["snd"].set_volume(S.get("music", 0.6) * 0.6)
        MUSIC["ch"] = MUSIC["snd"].play(-1)
def set_music_vol():
    if MUSIC["snd"]: MUSIC["snd"].set_volume(S.get("music", 0.6) * 0.6)
make_sounds()
bg(make_music)

# ---------------------------------------------------------------------------
#  characters
# ---------------------------------------------------------------------------
def eyes(s, x, y, r, open_=1.0, look=0.0, col=WHITE, pup=(20, 20, 30)):
    for ex in (-0.32, 0.32):
        eh = max(2, int(r * 0.34 * open_)); rr = pygame.Rect(0, 0, max(2, int(r * 0.24)), eh)
        rr.center = (int(x + ex * r), int(y - r * 0.08))
        pygame.draw.ellipse(s, col, rr)
        if open_ > 0.5: pygame.draw.circle(s, pup, (int(rr.centerx + look * r * 0.05), rr.centery + 1), max(1, int(r * 0.07)))
def blink(u, per=3.0): return 1.0 if (u % per) > 0.15 else 0.1
def orb(s, x, y, r, col, u, eyes_=True):
    glow(s, col, x, y, int(r * 2.0), 45)
    pygame.draw.circle(s, col, (int(x), int(y)), r)
    pygame.draw.circle(s, mix(col, WHITE, 0.35), (int(x - r * 0.3), int(y - r * 0.35)), max(1, int(r * 0.28)))
    pygame.draw.circle(s, mix(col, (0, 0, 0), 0.4), (int(x), int(y)), r, max(2, r // 14))
    if eyes_: eyes(s, x, y, r, blink(u), math.sin(u * 1.4))
def crown(s, x, y, w, col=(250, 200, 40)):
    pts = [(x - w / 2, y), (x - w / 2, y - w * 0.45), (x - w / 4, y - w * 0.2), (x, y - w * 0.55), (x + w / 4, y - w * 0.2), (x + w / 2, y - w * 0.45), (x + w / 2, y)]
    pygame.draw.polygon(s, col, pts); pygame.draw.polygon(s, mix(col, (0, 0, 0), 0.4), pts, 2)
def d_color(col):
    return lambda s, x, y, r, u: orb(s, x, y, r, col, u)
def d_crimson(s, x, y, r, u):
    orb(s, x, y, r, (225, 50, 55), u); crown(s, x, y - r * 0.82, r * 1.1)
    for k in (-1, 1): pygame.draw.line(s, (90, 10, 15), (x + k * r * 0.5, y - r * 0.42), (x + k * r * 0.12, y - r * 0.3), max(2, r // 20))
def d_ocean(s, x, y, r, u):
    orb(s, x, y, r, (50, 110, 240), u)
    for k in range(3):
        yy = y + r * 0.45 + k * r * 0.08
        pts = [(x - r * 0.8 + i * r * 0.1, yy + math.sin(u * 4 + i * 0.9 + k) * r * 0.05) for i in range(17)]
        pygame.draw.lines(s, (170, 220, 255), False, pts, max(1, r // 30))
    tx = x + r * 1.15; lw = max(2, r // 15); gold = (240, 210, 120)
    pygame.draw.line(s, gold, (tx, y + r), (tx, y - r * 1.2), lw)
    for dx in (-0.18, 0, 0.18): pygame.draw.line(s, gold, (tx + dx * r, y - r * 1.2), (tx + dx * r, y - r * 1.55), lw)
    pygame.draw.line(s, gold, (tx - r * 0.18, y - r * 1.2), (tx + r * 0.18, y - r * 1.2), lw)
def d_sun(s, x, y, r, u):
    for i in range(12):
        a = u * 0.8 + i * math.pi / 6
        pygame.draw.line(s, (255, 200, 40), (x + math.cos(a) * r * 1.05, y + math.sin(a) * r * 1.05), (x + math.cos(a) * r * 1.45, y + math.sin(a) * r * 1.45), max(2, r // 12))
    orb(s, x, y, r, (250, 205, 45), u, False)
    pygame.draw.rect(s, (25, 20, 30), (x - r * 0.75, y - r * 0.33, r * 1.5, r * 0.38), border_radius=max(2, r // 8))
    eyes(s, x, y, r, 1.0, math.sin(u * 2))
def d_gray(s, x, y, r, u):
    orb(s, x, y, r, (130, 130, 138), u)
    pygame.draw.ellipse(s, (250, 200, 40), (x - r * 0.75, y - r * 1.12, r * 1.5, r * 0.75))
    pygame.draw.rect(s, (250, 200, 40), (x - r * 0.95, y - r * 0.62, r * 1.9, r * 0.16), border_radius=4)
    pygame.draw.rect(s, (60, 60, 66), (x - r * 0.45, y + r * 0.35, r * 0.9, r * 0.12))
def d_candy(s, x, y, r, u):
    bob = math.sin(u * 2) * r * 0.08; yy = y + bob
    glow(s, (255, 180, 230), x, yy, int(r * 2), 40)
    pygame.draw.circle(s, (245, 245, 255), (int(x), int(yy - r * 0.15)), int(r * 0.85))
    pygame.draw.rect(s, (245, 245, 255), (x - r * 0.85, yy - r * 0.15, r * 1.7, r * 0.9))
    for i in range(4):
        pygame.draw.circle(s, (245, 245, 255), (int(x - r * 0.64 + i * r * 0.43), int(yy + r * 0.75)), int(r * 0.22))
    eyes(s, x, yy, r, blink(u), 0, (30, 30, 40), (255, 255, 255))
    cx, cy = x + r * 0.95, yy + r * 0.3
    pygame.draw.circle(s, (255, 90, 160), (int(cx), int(cy)), int(r * 0.25))
    for k in (-1, 1): pygame.draw.polygon(s, (255, 90, 160), [(cx + k * r * 0.22, cy), (cx + k * r * 0.48, cy - r * 0.18), (cx + k * r * 0.48, cy + r * 0.18)])
    pygame.draw.circle(s, WHITE, (int(cx - r * 0.07), int(cy - r * 0.07)), max(1, int(r * 0.07)))
def _dark(s, x, y, r, u, col, eye=(255, 40, 50)):
    glow(s, col, x, y, int(r * 2.1), 50)
    pygame.draw.circle(s, mix(col, (0, 0, 0), 0.82), (int(x), int(y)), r)
    pygame.draw.circle(s, mix(col, (0, 0, 0), 0.4), (int(x), int(y)), r, max(2, r // 14))
    for ex in (-0.33, 0.33):
        pygame.draw.ellipse(s, eye, (x + ex * r - r * 0.14, y - r * 0.2, r * 0.28, r * 0.2 * blink(u, 3.7)))
def d_earth(s, x, y, r, u):
    _dark(s, x, y, r, u, (150, 95, 50), (255, 170, 80))
    for a in (0.6, 2.2, 4.0):
        p = [(x + math.cos(a) * r * k, y + math.sin(a) * r * k + (k * 7 % 5)) for k in (0.3, 0.55, 0.75, 1.0)]
        pygame.draw.lines(s, (200, 130, 70), False, p, max(1, r // 25))
def d_life(s, x, y, r, u):
    _dark(s, x, y, r, u, (60, 200, 100), (140, 255, 140))
    for i in range(5):
        a = i * 1.26 + u * 0.3
        p = [(x + math.cos(a + k * 0.25) * r * (0.9 + k * 0.12), y + math.sin(a + k * 0.25) * r * (0.9 + k * 0.12)) for k in range(5)]
        pygame.draw.lines(s, (60, 180, 80), False, p, max(2, r // 14))
        pygame.draw.circle(s, (90, 220, 110), (int(p[-1][0]), int(p[-1][1])), max(2, r // 10))
def d_fire(s, x, y, r, u):
    for i in range(7):
        a = -math.pi / 2 + (i - 3) * 0.35; h = r * (0.5 + 0.25 * math.sin(u * 8 + i))
        bx, by = x + math.cos(a) * r * 0.8, y + math.sin(a) * r * 0.8
        pygame.draw.polygon(s, (255, 120 + i * 12, 30), [(bx - r * 0.15, by), (bx + r * 0.15, by), (bx + math.cos(a) * h, by + math.sin(a) * h)])
    _dark(s, x, y, r, u, (255, 140, 40), (255, 220, 80))
def d_complete(s, x, y, r, u):
    for i, c in enumerate(CVALS):
        a = u * 1.2 + i * math.pi / 4
        pygame.draw.circle(s, c, (int(x + math.cos(a) * r * 1.25), int(y + math.sin(a) * r * 1.25)), max(2, r // 9))
    _dark(s, x, y, r, u, (120, 120, 140), CVALS[int(u * 2) % 8])
def d_shadow3(s, x, y, r, u):     # SHADOW, the boss of the factory (chapter 3)
    _dark(s, x, y, r, u, (110, 110, 120))
    pygame.draw.polygon(s, (20, 20, 24), [(x - r * 0.55, y + r * 0.85), (x + r * 0.55, y + r * 0.85), (x, y + r * 0.35)])
    pygame.draw.polygon(s, (190, 30, 40), [(x - r * 0.1, y + r * 0.45), (x + r * 0.1, y + r * 0.45), (x + r * 0.06, y + r * 0.85), (x - r * 0.06, y + r * 0.85)])
    pygame.draw.rect(s, (40, 40, 46), (x - r * 0.5, y - r * 1.25, r, r * 0.38)); pygame.draw.rect(s, (40, 40, 46), (x - r * 0.75, y - r * 0.9, r * 1.5, r * 0.1))
def d_chroma(s, x, y, r, u):
    glow(s, WHITE, x, y, int(r * 2.1), 35)
    for i in range(8):
        a0 = u * 0.8 + i * 2 * math.pi / 8
        pygame.draw.arc(s, CVALS[i], (x - r, y - r, 2 * r, 2 * r), a0, a0 + 2 * math.pi / 8 + 0.02, max(3, int(r * 0.18)))
    pygame.draw.circle(s, (34, 30, 52), (int(x), int(y)), int(r * 0.82))
    pygame.draw.circle(s, (60, 54, 90), (int(x - r * 0.2), int(y - r * 0.25)), int(r * 0.35))
    eyes(s, x, y, r, blink(u), math.sin(u))
def d_white(s, x, y, r, u):
    glow(s, WHITE, x, y, int(r * 2.2), 70)
    pygame.draw.circle(s, (250, 250, 255), (int(x), int(y)), r); pygame.draw.circle(s, WHITE, (int(x), int(y)), r, 3)
    eyes(s, x, y, r, blink(u, 3.1), math.sin(u * 1.3), (40, 40, 60), WHITE)
def d_black(s, x, y, r, u):
    pygame.draw.circle(s, (4, 4, 8), (int(x), int(y)), r); pygame.draw.circle(s, (200, 200, 215), (int(x), int(y)), r, 3)
    eyes(s, x, y, r, blink(u, 2.7), -math.sin(u * 1.1))
def d_watcher(s, x, y, r, u):
    rnd = random.Random(int(u * 24))
    bw, bh = int(r * 1.6), int(r * 2.6)
    body = pygame.Surface((bw, bh), pygame.SRCALPHA)
    pygame.draw.ellipse(body, (60, 60, 64), (bw * 0.2, 0, bw * 0.6, bh * 0.38))
    pygame.draw.rect(body, (60, 60, 64), (bw * 0.1, bh * 0.3, bw * 0.8, bh * 0.7), border_radius=int(bw * 0.3))
    for _ in range(int(bw * bh / 90)):
        px, py = rnd.randrange(bw), rnd.randrange(bh)
        if body.get_at((px, py))[3]: v = rnd.randint(0, 140); body.set_at((px, py), (v, v, v, 255))
    s.blit(body, (x - bw // 2 + rnd.randint(-2, 2), y - bh // 2))
    pygame.draw.circle(s, WHITE, (int(x), int(y - bh * 0.32)), max(2, int(r * 0.16)))
    pygame.draw.circle(s, (255, 40, 50), (int(x), int(y - bh * 0.32)), max(1, int(r * 0.07)))
    for k in range(2):
        yy = y - bh // 2 + rnd.randint(0, bh); pygame.draw.rect(s, (60, 255, 120), (x - bw // 2 - r * 0.2, yy, bw + r * 0.4, max(1, r // 40)))
def d_static(s, x, y, r, u):
    tw, th = int(r * 2.0), int(r * 1.6)
    pygame.draw.line(s, (120, 120, 130), (x, y - th / 2), (x - r * 0.6, y - th / 2 - r * 0.6), 3)
    pygame.draw.line(s, (120, 120, 130), (x, y - th / 2), (x + r * 0.6, y - th / 2 - r * 0.6), 3)
    pygame.draw.rect(s, (70, 55, 45), (x - tw / 2, y - th / 2, tw, th), border_radius=max(3, r // 5))
    scr = pygame.Rect(int(x - tw / 2 + r * 0.2), int(y - th / 2 + r * 0.18), int(tw - r * 0.9), int(th - r * 0.36))
    rnd = random.Random(int(u * 30)); pygame.draw.rect(s, (120, 120, 120), scr)
    for _ in range(scr.w * scr.h // 40):
        v = rnd.randint(30, 230); s.set_at((scr.x + rnd.randrange(scr.w), scr.y + rnd.randrange(scr.h)), (v, v, v))
    for ex in (-0.22, 0.22): pygame.draw.rect(s, (10, 10, 10), (scr.centerx + ex * scr.w - r * 0.1, scr.centery - r * 0.24, r * 0.2, r * 0.25))
    pygame.draw.arc(s, (10, 10, 10), (scr.centerx - r * 0.4, scr.centery - r * 0.08, r * 0.8, r * 0.5), math.pi + 0.3, 2 * math.pi - 0.3, max(2, r // 20))
    for k in range(2): pygame.draw.circle(s, (200, 190, 170), (int(x + tw / 2 - r * 0.37), int(y - th / 4 + k * r * 0.5)), max(2, int(r * 0.12)))
def d_theshadow(s, x, y, r, u):
    glow(s, (130, 30, 170), x, y, int(r * 2.4), 70)
    for i in range(7):
        a = u * 1.5 + i * 0.9
        pygame.draw.circle(s, (8, 4, 12), (int(x + math.cos(a) * r * 0.9), int(y + r * 0.6 + math.sin(a * 1.3) * r * 0.2)), int(r * 0.35))
    pygame.draw.circle(s, (6, 3, 10), (int(x), int(y)), r)
    for ex in (-0.33, 0.33): pygame.draw.ellipse(s, (255, 40, 50), (x + ex * r - r * 0.14, y - r * 0.2, r * 0.28, r * 0.2))
    pts = [(x - r * 0.45 + i * r * 0.09, y + r * 0.25 + (r * 0.08 if i % 2 else 0)) for i in range(11)]
    pygame.draw.lines(s, (255, 70, 80), False, pts, max(2, r // 30))
def d_pixel(s, x, y, r, u):
    for i in range(3):
        a = u * 1.5 + i * 2.1; nx, ny = x + math.cos(a) * r * 1.4, y + math.sin(a) * r * 1.0 - r * 0.3
        pygame.draw.circle(s, (255, 230, 120), (int(nx), int(ny)), max(2, r // 9)); pygame.draw.line(s, (255, 230, 120), (nx + r * 0.1, ny), (nx + r * 0.1, ny - r * 0.35), max(1, r // 25))
    orb(s, x, y, r, (255, 120, 190), u)
    pygame.draw.arc(s, (30, 30, 40), (x - r * 1.05, y - r * 1.15, r * 2.1, r * 1.9), 0.15, math.pi - 0.15, max(3, r // 9))
    for k in (-1, 1): pygame.draw.rect(s, (30, 30, 40), (x + k * r * 1.0 - r * 0.18, y - r * 0.35, r * 0.36, r * 0.6), border_radius=max(2, r // 10))
def d_luna(s, x, y, r, u):
    orb(s, x, y, r, (150, 120, 255), u, False)
    pygame.draw.rect(s, (30, 30, 40), (x - r * 0.85, y - r * 0.42, r * 1.7, r * 0.55), border_radius=max(3, r // 5))
    pygame.draw.rect(s, (120, 230, 255), (x - r * 0.72, y - r * 0.33, r * 1.44, r * 0.37), border_radius=max(2, r // 7))
    pygame.draw.line(s, (30, 30, 40), (x - r * 0.98, y - r * 0.15), (x + r * 0.98, y - r * 0.15), max(2, r // 15))
    mx, my = x + r * 0.95, y - r * 0.95
    pygame.draw.circle(s, (255, 240, 180), (int(mx), int(my)), max(2, int(r * 0.3))); pygame.draw.circle(s, (30, 20, 50), (int(mx + r * 0.12), int(my - r * 0.06)), max(2, int(r * 0.26)))
    rr = pygame.Rect(0, 0, int(r * 0.9), int(r * 0.18)); rr.center = (int(x), int(y + r * 0.45)); pygame.draw.arc(s, (40, 30, 60), rr, math.pi, 2 * math.pi, max(2, r // 30))
def d_man(s, x, y, r, u):
    for i in range(16):
        a = u * 0.6 + i * math.pi / 8
        pygame.draw.line(s, CVALS[i % 8], (x + math.cos(a) * r * 1.1, y + math.sin(a) * r * 1.1), (x + math.cos(a) * r * 1.7, y + math.sin(a) * r * 1.7), max(2, r // 15))
    orb(s, x, y, r, (255, 205, 70), u, False)
    P = ["1...1", "11.11", "1.1.1", "1...1", "1...1"]; c = max(2, int(r * 0.13))
    for j, row in enumerate(P):
        for i, ch in enumerate(row):
            if ch == "1": pygame.draw.rect(s, (60, 35, 10), (x - 2.5 * c + i * c, y + r * 0.22 + j * c * 0.8 - c * 1.4, c, max(1, int(c * 0.8))))
    crown(s, x, y - r * 0.86, r * 1.0, (255, 240, 150)); eyes(s, x, y - r * 0.12, r, blink(u), math.sin(u * 2))
def d_dobe(s, x, y, r, u):     # DOBE: the old workshop robot (38 years later, still running)
    glow(s, (255, 170, 60), x, y, int(r * 2), 40)
    pygame.draw.line(s, (150, 150, 160), (x, y - r * 0.85), (x, y - r * 1.3), max(2, r // 15))
    pygame.draw.circle(s, (255, 60, 50) if (u % 1.2) < 0.6 else (120, 30, 30), (int(x), int(y - r * 1.35)), max(2, int(r * 0.12)))
    pygame.draw.rect(s, (120, 125, 135), (x - r * 0.9, y - r * 0.85, r * 1.8, r * 1.55), border_radius=max(3, r // 6))
    pygame.draw.rect(s, (70, 72, 80), (x - r * 0.9, y - r * 0.85, r * 1.8, r * 1.55), max(2, r // 14), border_radius=max(3, r // 6))
    for (bx, by) in ((-0.75, -0.7), (0.75, -0.7), (-0.75, 0.55), (0.75, 0.55)): pygame.draw.circle(s, (60, 60, 66), (int(x + bx * r), int(y + by * r)), max(1, r // 18))
    pygame.draw.circle(s, (20, 20, 26), (int(x), int(y - r * 0.15)), int(r * 0.42))
    pygame.draw.circle(s, (255, 170, 60), (int(x + math.sin(u) * r * 0.1), int(y - r * 0.15)), int(r * 0.2 * blink(u, 4.0) + 1))
    for i in range(5): pygame.draw.rect(s, (40, 40, 46), (x - r * 0.5 + i * r * 0.22, y + r * 0.38, r * 0.14, r * 0.18))
    for k in (-1, 1): pygame.draw.rect(s, (90, 90, 100), (x + k * r * 0.9 - (r * 0.18 if k < 0 else 0), y - r * 0.4, r * 0.18, r * 0.5))
def d_skeleton(s, x, y, r, u):    # SKELETON: lives in the dark rooms of the mansion
    glow(s, (200, 220, 255), x, y, int(r * 2), 30)
    for k in (-1, 1):
        bx = x + k * r * 0.9
        pygame.draw.line(s, (235, 235, 225), (bx, y + r * 0.9), (bx + k * r * 0.3, y + r * 1.25), max(2, r // 10))
    pygame.draw.circle(s, (240, 240, 230), (int(x), int(y - r * 0.1)), int(r * 0.9))
    pygame.draw.rect(s, (240, 240, 230), (x - r * 0.5, y + r * 0.5, r, r * 0.4), border_radius=max(2, r // 10))
    for ex in (-0.35, 0.35): pygame.draw.circle(s, (15, 15, 20), (int(x + ex * r), int(y - r * 0.2)), int(r * 0.24))
    for ex in (-0.35, 0.35): pygame.draw.circle(s, (120, 220, 255), (int(x + ex * r), int(y - r * 0.2)), max(1, int(r * 0.07 * blink(u, 2.5))))
    pygame.draw.polygon(s, (15, 15, 20), [(x, y + r * 0.05), (x - r * 0.1, y + r * 0.25), (x + r * 0.1, y + r * 0.25)])
    for i in range(4): pygame.draw.line(s, (60, 60, 60), (x - r * 0.33 + i * r * 0.22, y + r * 0.55), (x - r * 0.33 + i * r * 0.22, y + r * 0.85), max(1, r // 30))


# ---- added in v1.2 ----
def d_pumpkin(s, x, y, r, u):     # THE HAUNT
    glow(s, (255, 140, 40), x, y, int(r * 2), 45)
    for k in (-0.55, 0.55, 0):
        pygame.draw.ellipse(s, (235, 120, 25) if k else (250, 140, 35), (x + k * r - r * 0.62, y - r * 0.85, r * 1.24, r * 1.7))
    pygame.draw.ellipse(s, (160, 70, 10), (x - r * 1.15, y - r * 0.85, r * 2.3, r * 1.7), max(2, r // 14))
    pygame.draw.rect(s, (70, 110, 40), (x - r * 0.1, y - r * 1.15, r * 0.2, r * 0.35), border_radius=3)
    fl = 0.7 + 0.3 * math.sin(u * 9)
    fire = (255, int(200 * fl + 40), 60)
    for k in (-1, 1): pygame.draw.polygon(s, fire, [(x + k * r * 0.42, y - r * 0.38), (x + k * r * 0.2, y - r * 0.05), (x + k * r * 0.62, y - r * 0.05)])
    pygame.draw.polygon(s, fire, [(x - r * 0.6, y + r * 0.2), (x + r * 0.6, y + r * 0.2), (x + r * 0.35, y + r * 0.5), (x, y + r * 0.35), (x - r * 0.35, y + r * 0.5)])
def d_maple(s, x, y, r, u):       # MAPLE BLOSSOM
    sway = math.sin(u * 1.5) * 0.12
    pts = []
    for i in range(11):
        a = -math.pi / 2 + sway + i * 2 * math.pi / 11
        rr = r * (1.25 if i % 2 == 0 else 0.62)
        pts.append((x + math.cos(a) * rr, y + math.sin(a) * rr))
    glow(s, (235, 90, 30), x, y, int(r * 2), 40)
    pygame.draw.polygon(s, (230, 80, 30), pts); pygame.draw.polygon(s, (150, 40, 15), pts, max(2, r // 14))
    pygame.draw.line(s, (120, 50, 20), (x, y + r * 0.2), (x + math.sin(sway) * r * 0.3, y + r * 1.4), max(2, r // 12))
    eyes(s, x, y, r * 0.9, blink(u), math.sin(u))
def d_frost(s, x, y, r, u):       # FIRST FROST
    orb(s, x, y, r, (150, 215, 255), u, False)
    for i in range(6):
        a = -math.pi / 2 + (i - 2.5) * 0.32
        bx, by = x + math.cos(a) * r * 0.9, y + math.sin(a) * r * 0.9
        pygame.draw.polygon(s, (230, 248, 255), [(bx - r * 0.1, by + r * 0.05), (bx + r * 0.1, by + r * 0.05), (x + math.cos(a) * r * 1.5, y + math.sin(a) * r * 1.5)])
    for i in range(6):
        a = u * 0.5 + i * math.pi / 3; px_, py_ = x + math.cos(a) * r * 1.6, y + math.sin(a) * r * 1.2 + r * 0.3
        pygame.draw.line(s, WHITE, (px_ - 4, py_), (px_ + 4, py_), 1); pygame.draw.line(s, WHITE, (px_, py_ - 4), (px_, py_ + 4), 1)
    eyes(s, x, y, r, blink(u), math.sin(u), (255, 255, 255), (40, 120, 200))
def d_cake(s, x, y, r, u):        # HAPPY BIRTHDAY (Color Under Pressure turns 1)
    glow(s, (255, 150, 200), x, y, int(r * 2), 40)
    pygame.draw.rect(s, (255, 170, 200), (x - r, y - r * 0.2, r * 2, r * 1.0), border_radius=max(3, r // 6))
    pygame.draw.rect(s, (250, 240, 230), (x - r * 0.75, y - r * 0.8, r * 1.5, r * 0.62), border_radius=max(3, r // 6))
    for i in range(5): pygame.draw.circle(s, (250, 240, 230), (int(x - r + i * r * 0.5), int(y - r * 0.2)), max(2, int(r * 0.17)))
    for i, c in enumerate(CVALS[:6]): pygame.draw.circle(s, c, (int(x - r * 0.7 + i * r * 0.28), int(y + r * 0.45)), max(1, r // 14))
    pygame.draw.rect(s, (90, 160, 255), (x - r * 0.07, y - r * 1.25, r * 0.14, r * 0.45))
    fl = (u * 7) % 2 < 1
    pygame.draw.ellipse(s, (255, 210, 60) if fl else (255, 150, 40), (x - r * 0.1, y - r * 1.55, r * 0.2, r * 0.3))
    blit(s, txt("bungee", max(10, int(r * 0.5)), "1", (230, 60, 120)), (int(x), int(y - r * 0.5)))
    eyes(s, x, y + r * 0.3, r * 0.8, blink(u), 0, (40, 30, 40), WHITE)
def d_galaxy(s, x, y, r, u):      # SEASON 1 (the Galaxy skin was retired)
    glow(s, (140, 80, 255), x, y, int(r * 2.2), 55)
    rect = pygame.Rect(0, 0, int(r * 3.2), int(r * 0.9)); rect.center = (int(x), int(y))
    pygame.draw.arc(s, (200, 170, 255), rect, 0, math.pi, max(2, r // 10))
    pygame.draw.circle(s, (120, 70, 220), (int(x), int(y)), r)
    pygame.draw.circle(s, (170, 120, 255), (int(x - r * 0.3), int(y - r * 0.35)), max(1, int(r * 0.3)))
    for i in range(7):
        a = i * 0.9 + u * 0.2; pygame.draw.circle(s, WHITE, (int(x + math.cos(a) * r * 0.6), int(y + math.sin(a * 1.7) * r * 0.5)), 1)
    pygame.draw.arc(s, (230, 210, 255), rect, math.pi, 2 * math.pi, max(2, r // 10))
    eyes(s, x, y, r, blink(u), math.sin(u))
    for i in range(5):
        a = u * 0.7 + i * 1.256; sx, sy = x + math.cos(a) * r * 1.9, y + math.sin(a) * r * 1.4
        pygame.draw.circle(s, (255, 255, 200), (int(sx), int(sy)), max(1, r // 25))
def d_matic(s, x, y, r, u):       # SHADOW-MATIC 3000 (the machine in the factory, chapter 3)
    glow(s, (120, 120, 140), x, y, int(r * 2), 40)
    pygame.draw.polygon(s, (90, 90, 100), [(x - r * 0.9, y - r * 1.2), (x + r * 0.9, y - r * 1.2), (x + r * 0.35, y - r * 0.75), (x - r * 0.35, y - r * 0.75)])
    for i, c in enumerate(CVALS[:4]):
        pygame.draw.circle(s, c, (int(x - r * 0.45 + i * r * 0.3), int(y - r * 1.25 - abs(math.sin(u * 3 + i)) * r * 0.2)), max(2, r // 9))
    pygame.draw.rect(s, (70, 70, 80), (x - r * 1.0, y - r * 0.78, r * 2.0, r * 1.6), border_radius=max(3, r // 7))
    pygame.draw.rect(s, (40, 40, 48), (x - r * 1.0, y - r * 0.78, r * 2.0, r * 1.6), max(2, r // 14), border_radius=max(3, r // 7))
    for k in (-0.45, 0.45):
        cx_, cy_ = x + k * r, y - r * 0.25
        pygame.draw.circle(s, (230, 230, 230), (int(cx_), int(cy_)), int(r * 0.3)); pygame.draw.circle(s, (30, 30, 30), (int(cx_), int(cy_)), int(r * 0.3), 2)
        a = u * 2 + k * 3; pygame.draw.line(s, (220, 40, 50), (cx_, cy_), (cx_ + math.cos(a) * r * 0.24, cy_ + math.sin(a) * r * 0.24), max(1, r // 25))
    pygame.draw.rect(s, (30, 30, 34), (x - r * 0.75, y + r * 0.2, r * 1.5, r * 0.45), border_radius=4)
    blit(s, txt("bungee", max(8, int(r * 0.32)), "3000", (120, 120, 130)), (int(x), int(y + r * 0.43)))
    pygame.draw.rect(s, (20, 20, 24), (x - r * 1.3, y + r * 0.82, r * 2.6, r * 0.25))
    for i in range(3):
        gx = x - r * 1.1 + ((u * r * 0.8 + i * r * 0.9) % (r * 2.2))
        pygame.draw.circle(s, (110, 110, 110), (int(gx), int(y + r * 0.72)), max(2, r // 9))
def d_rewind(s, x, y, r, u):      # TAPE 001: the tape itself
    rnd = random.Random(int(u * 20))
    w, h = r * 2.2, r * 1.4; ox = rnd.randint(-2, 2)
    pygame.draw.rect(s, (25, 25, 30), (x - w / 2 + ox, y - h / 2, w, h), border_radius=max(3, r // 6))
    pygame.draw.rect(s, (230, 220, 200), (x - w / 2 + r * 0.15 + ox, y - h / 2 + r * 0.12, w - r * 0.3, r * 0.42), border_radius=3)
    blit(s, txt("bungee", max(8, int(r * 0.26)), "TAPE 001", (40, 40, 50)), (int(x + ox), int(y - h / 2 + r * 0.33)))
    for k in (-0.5, 0.5):
        cx_ = x + k * r + ox
        pygame.draw.circle(s, (230, 230, 230), (int(cx_), int(y + r * 0.2)), int(r * 0.3))
        pygame.draw.circle(s, (255, 40, 50), (int(cx_ + math.sin(u * 1.3) * r * 0.08), int(y + r * 0.2)), max(2, int(r * 0.12)))
        for j in range(3):
            a = -u * 4 + j * 2.09; pygame.draw.line(s, (40, 40, 40), (cx_, y + r * 0.2), (cx_ + math.cos(a) * r * 0.28, y + r * 0.2 + math.sin(a) * r * 0.28), 1)
    pygame.draw.line(s, (60, 40, 30), (x - w / 2, y + h / 2), (x - w / 2 - r * 0.3, y + h / 2 + r * 0.4 + math.sin(u * 3) * 4), max(1, r // 30))
    if rnd.random() < 0.4: pygame.draw.rect(s, (60, 255, 120), (x - w / 2 - 6, y - h / 2 + rnd.random() * h, w + 12, 2))
def d_glitch(s, x, y, r, u):      # THE GLITCH STORM
    rnd = random.Random(int(u * 14))
    glow(s, (80, 255, 200), x, y, int(r * 2.3), 55)
    for dx, col in ((-r * 0.08, (255, 40, 80)), (r * 0.08, (40, 220, 255))):
        pygame.draw.circle(s, col, (int(x + dx + rnd.randint(-2, 2)), int(y)), r)
    pygame.draw.circle(s, (20, 20, 30), (int(x), int(y)), int(r * 0.92))
    for i in range(10):
        bx, by = x + rnd.uniform(-1, 1) * r * 0.8, y + rnd.uniform(-1, 1) * r * 0.8
        pygame.draw.rect(s, rnd.choice(CVALS), (bx, by, r * 0.18, r * 0.12))
    sh = rnd.randint(-int(r * 0.15), int(r * 0.15)) if rnd.random() < 0.3 else 0
    for ex in (-0.32, 0.32): pygame.draw.rect(s, (80, 255, 200), (x + ex * r - r * 0.1 + sh, y - r * 0.25, r * 0.2, r * 0.28))
    pygame.draw.lines(s, (80, 255, 200), False, [(x - r * 0.4 + i * r * 0.1, y + r * 0.3 + (r * 0.08 if i % 2 else 0)) for i in range(9)], max(1, r // 25))
    for k in range(3):
        a = u * 3 + k * 2.1; pygame.draw.line(s, (255, 230, 80), (x + math.cos(a) * r * 1.2, y + math.sin(a) * r * 1.2), (x + math.cos(a + 0.3) * r * 1.6, y + math.sin(a + 0.3) * r * 1.6), max(2, r // 14))

RAR = {"COMMON": (180, 180, 200), "RARE": (60, 140, 255), "EPIC": (170, 90, 240), "LEGENDARY": (250, 190, 40),
       "CORRUPTED": (60, 255, 120), "MYTHIC": (235, 50, 70), "DEVELOPER": (255, 215, 90), "SECRET": (255, 255, 255)}
RAR_ORDER = ["COMMON", "RARE", "EPIC", "LEGENDARY", "CORRUPTED", "MYTHIC", "DEVELOPER", "SECRET"]
# ---- WINTER UPDATE characters (7/11/2026) ----
def d_burger(s, x, y, r, u):      # MR_BURGER - DEVELOPER 1/250,000
    glow(s, (255, 190, 80), x, y, int(r * 2.1), 45)
    # bottom bun
    pygame.draw.ellipse(s, (226, 150, 70), (x - r * 1.0, y + r * 0.42, r * 2.0, r * 0.62))
    pygame.draw.ellipse(s, (190, 115, 45), (x - r * 1.0, y + r * 0.42, r * 2.0, r * 0.62), max(1, r // 25))
    # patty
    pygame.draw.ellipse(s, (95, 52, 30), (x - r * 1.05, y + r * 0.12, r * 2.1, r * 0.5))
    for i in range(9):
        pygame.draw.circle(s, (70, 36, 20), (int(x - r * 0.8 + i * r * 0.2), int(y + r * 0.37 + (i % 2) * r * 0.06)), max(1, r // 22))
    # cheese with drips
    pts = [(x - r * 1.02, y + r * 0.08), (x + r * 1.02, y + r * 0.08)]
    drips = [(-0.6, 0.32), (-0.15, 0.4), (0.35, 0.3), (0.8, 0.26)]
    pygame.draw.polygon(s, (250, 200, 40), [(x - r * 1.02, y + r * 0.02), (x + r * 1.02, y + r * 0.02), (x + r * 0.95, y + r * 0.16), (x - r * 0.95, y + r * 0.16)])
    for dx, dl in drips:
        pygame.draw.polygon(s, (250, 200, 40), [(x + (dx - 0.12) * r, y + r * 0.14), (x + (dx + 0.12) * r, y + r * 0.14), (x + dx * r, y + (0.14 + dl) * r)])
    # tomato + lettuce
    pygame.draw.ellipse(s, (220, 60, 50), (x - r * 0.98, y - r * 0.14, r * 1.96, r * 0.26))
    for i in range(12):
        lx = x - r * 1.05 + i * r * 0.19
        pygame.draw.circle(s, (110, 190, 70), (int(lx), int(y - r * 0.16 + (i % 2) * r * 0.05)), max(2, int(r * 0.13)))
    # top bun
    pygame.draw.ellipse(s, (232, 160, 70), (x - r * 1.05, y - r * 1.05, r * 2.1, r * 1.0))
    pygame.draw.rect(s, (232, 160, 70), (x - r * 1.05, y - r * 0.55, r * 2.1, r * 0.4))
    pygame.draw.ellipse(s, (248, 196, 110), (x - r * 0.75, y - r * 0.98, r * 0.9, r * 0.32))
    rnd = random.Random(7)
    for i in range(18):
        sx_, sy_ = x + rnd.uniform(-0.85, 0.85) * r, y + rnd.uniform(-0.95, -0.35) * r
        pygame.draw.ellipse(s, (255, 245, 215), (sx_, sy_, max(2, r * 0.09), max(1, r * 0.05)))
    # eyebrows
    for k in (-1, 1):
        bx = x + k * r * 0.48
        pygame.draw.line(s, (20, 20, 22), (bx - r * 0.24, y - r * 0.72), (bx + r * 0.22, y - r * 0.74), max(3, int(r * 0.13)))
    # big googly eyes (they look around)
    look = math.sin(u * 1.3) * r * 0.08
    for k in (-1, 1):
        ex, ey = x + k * r * 0.4, y - r * 0.22
        pygame.draw.circle(s, (240, 242, 248), (int(ex), int(ey)), int(r * 0.36))
        pygame.draw.circle(s, (200, 204, 214), (int(ex), int(ey)), int(r * 0.36), max(1, r // 30))
        bl = blink(u, 3.4)
        if bl > 0.5: pygame.draw.circle(s, (18, 18, 20), (int(ex + look + k * r * 0.06), int(ey + r * 0.02)), int(r * 0.24))
        else: pygame.draw.line(s, (18, 18, 20), (ex - r * 0.25, ey), (ex + r * 0.25, ey), max(2, r // 12))
    # small smile
    pygame.draw.arc(s, (20, 20, 22), (x - r * 0.18, y + r * 0.0, r * 0.36, r * 0.24), math.pi + 0.3, 2 * math.pi - 0.3, max(3, int(r * 0.1)))
def d_penguin(s, x, y, r, u):        # PENGUIN — RARE 1/30
    glow(s, (120, 190, 255), x, y, int(r * 1.9), 40)
    wob = math.sin(u * 2.0) * r * 0.05
    pygame.draw.ellipse(s, (34, 36, 54), (x - r * 0.78 + wob, y - r * 0.82, r * 1.56, r * 1.78))
    pygame.draw.ellipse(s, (245, 247, 252), (x - r * 0.50 + wob, y - r * 0.40, r * 1.00, r * 1.32))
    for k in (-1, 1):                                       # flippers
        a = math.sin(u * 2.4 + (0 if k < 0 else 1.6)) * 0.35
        px, py = x + k * r * 0.76 + wob, y - r * 0.10
        pygame.draw.polygon(s, (26, 28, 44), [(px, py - r * 0.22),
                                              (px + k * r * (0.34 + a * 0.2), py + r * (0.26 + a * 0.2)),
                                              (px, py + r * 0.40)])
    for k in (-1, 1):                                       # feet
        pygame.draw.ellipse(s, (250, 170, 40), (x + k * r * 0.30 - r * 0.22 + wob, y + r * 0.84, r * 0.44, r * 0.20))
    bl = blink(u, 3.1)
    for k in (-1, 1):                                       # eyes
        ex, ey = x + k * r * 0.26 + wob, y - r * 0.42
        pygame.draw.circle(s, (250, 252, 255), (int(ex), int(ey)), int(r * 0.19))
        if bl > 0.5: pygame.draw.circle(s, (18, 18, 26), (int(ex + math.sin(u) * r * 0.03), int(ey + r * 0.02)), int(r * 0.10))
        else: pygame.draw.line(s, (18, 18, 26), (ex - r * 0.16, ey), (ex + r * 0.16, ey), max(2, int(r * 0.07)))
    pygame.draw.polygon(s, (250, 160, 35), [(x - r * 0.15 + wob, y - r * 0.22), (x + r * 0.15 + wob, y - r * 0.22), (x + wob, y - r * 0.02)])
    for k in (-1, 1):                                       # scarf
        pygame.draw.rect(s, (220, 60, 70), (x - r * 0.56 + wob, y - r * 0.14, r * 1.12, r * 0.22), border_radius=int(r * 0.08))
    pygame.draw.rect(s, (200, 45, 58), (x + r * 0.30 + wob, y + r * 0.02, r * 0.22, r * 0.52), border_radius=int(r * 0.07))
    for i in range(4):                                      # a little snow around it
        a = u * 0.8 + i * 1.57
        pygame.draw.circle(s, (235, 245, 255), (int(x + math.cos(a) * r * 1.25), int(y + ((u * 26 + i * 33) % (r * 2.2)) - r * 1.1)), max(1, int(r * 0.05)))

def d_snowman(s, x, y, r, u):        # SNOWMAN — EPIC 1/90
    glow(s, (190, 225, 255), x, y, int(r * 2.0), 46)
    sway = math.sin(u * 1.3) * r * 0.04
    pygame.draw.circle(s, (238, 246, 255), (int(x), int(y + r * 0.56)), int(r * 0.62))
    pygame.draw.circle(s, (246, 251, 255), (int(x + sway * 0.5), int(y - r * 0.02)), int(r * 0.46))
    pygame.draw.circle(s, (250, 253, 255), (int(x + sway), int(y - r * 0.52)), int(r * 0.34))
    for cx_, cy_, rr in ((0, 0.56, 0.62), (0.5, -0.02, 0.46), (1.0, -0.52, 0.34)):
        pygame.draw.circle(s, (205, 222, 242), (int(x + sway * cx_), int(y + r * cy_)), int(r * rr), max(1, int(r * 0.035)))
    for k in (-1, 1):                                       # stick arms
        bx, by = x + k * r * 0.40 + sway * 0.5, y - r * 0.06
        ax = math.sin(u * 1.8 + k) * 0.12
        ex_, ey_ = bx + k * r * 0.62, by - r * (0.30 + ax)
        pygame.draw.line(s, (120, 78, 44), (bx, by), (ex_, ey_), max(2, int(r * 0.08)))
        pygame.draw.line(s, (120, 78, 44), (ex_, ey_), (ex_ + k * r * 0.18, ey_ - r * 0.16), max(2, int(r * 0.06)))
        pygame.draw.line(s, (120, 78, 44), (ex_, ey_), (ex_ + k * r * 0.20, ey_ + r * 0.06), max(2, int(r * 0.06)))
    for i, dy in enumerate((0.18, 0.46, 0.74)):             # buttons
        pygame.draw.circle(s, (40, 40, 56), (int(x + sway * 0.4), int(y + r * dy)), max(1, int(r * 0.07)))
    pygame.draw.rect(s, (28, 28, 40), (x + sway - r * 0.40, y - r * 0.92, r * 0.80, r * 0.14), border_radius=int(r * 0.04))
    pygame.draw.rect(s, (28, 28, 40), (x + sway - r * 0.27, y - r * 1.26, r * 0.54, r * 0.36), border_radius=int(r * 0.05))
    pygame.draw.rect(s, (220, 60, 70), (x + sway - r * 0.27, y - r * 1.00, r * 0.54, r * 0.09))
    bl = blink(u, 2.8)
    for k in (-1, 1):
        ex, ey = x + sway + k * r * 0.14, y - r * 0.60
        if bl > 0.5: pygame.draw.circle(s, (34, 34, 48), (int(ex), int(ey)), max(1, int(r * 0.07)))
        else: pygame.draw.line(s, (34, 34, 48), (ex - r * 0.07, ey), (ex + r * 0.07, ey), max(2, int(r * 0.05)))
    pygame.draw.polygon(s, (250, 150, 40), [(x + sway, y - r * 0.50), (x + sway, y - r * 0.38), (x + sway + r * 0.42, y - r * 0.44)])
    for i in range(5):
        a = u * 1.1 + i * 1.25
        pygame.draw.circle(s, (240, 248, 255), (int(x + math.cos(a) * r * 1.3), int(y + ((u * 22 + i * 28) % (r * 2.4)) - r * 1.2)), max(1, int(r * 0.05)))

def d_reindeer(s, x, y, r, u):       # REINDEER — EPIC 1/180
    glow(s, (255, 120, 90), x, y, int(r * 2.0), 48)
    bob = math.sin(u * 1.7) * r * 0.05
    for k in (-1, 1):                                        # antlers
        bx, by = x + k * r * 0.34, y - r * 0.62 + bob
        pygame.draw.line(s, (150, 104, 56), (bx, by), (bx + k * r * 0.30, by - r * 0.52), max(2, int(r * 0.09)))
        pygame.draw.line(s, (150, 104, 56), (bx + k * r * 0.12, by - r * 0.22), (bx + k * r * 0.46, by - r * 0.30), max(2, int(r * 0.07)))
        pygame.draw.line(s, (150, 104, 56), (bx + k * r * 0.24, by - r * 0.42), (bx + k * r * 0.10, by - r * 0.78), max(2, int(r * 0.07)))
        pygame.draw.line(s, (150, 104, 56), (bx + k * r * 0.30, by - r * 0.52), (bx + k * r * 0.56, by - r * 0.70), max(2, int(r * 0.07)))
    pygame.draw.ellipse(s, (150, 96, 56), (x - r * 0.66, y - r * 0.62 + bob, r * 1.32, r * 1.26))
    for k in (-1, 1):                                        # ears
        pygame.draw.ellipse(s, (128, 80, 46), (x + k * r * 0.56 - r * 0.20, y - r * 0.44 + bob, r * 0.40, r * 0.24))
    pygame.draw.ellipse(s, (196, 146, 96), (x - r * 0.38, y + r * 0.04 + bob, r * 0.76, r * 0.56))
    bl = blink(u, 3.3)
    for k in (-1, 1):
        ex, ey = x + k * r * 0.26, y - r * 0.22 + bob
        pygame.draw.circle(s, (250, 250, 255), (int(ex), int(ey)), int(r * 0.15))
        if bl > 0.5: pygame.draw.circle(s, (24, 20, 26), (int(ex), int(ey + r * 0.02)), int(r * 0.08))
        else: pygame.draw.line(s, (24, 20, 26), (ex - r * 0.12, ey), (ex + r * 0.12, ey), max(2, int(r * 0.06)))
    pr = r * (0.21 + 0.02 * math.sin(u * 4.0))               # the famous red nose
    glow(s, (255, 60, 60), int(x), int(y + r * 0.30 + bob), int(r * 0.8), 70)
    pygame.draw.circle(s, (240, 50, 55), (int(x), int(y + r * 0.30 + bob)), int(pr))
    pygame.draw.circle(s, (255, 150, 150), (int(x - pr * 0.3), int(y + r * 0.30 - pr * 0.3 + bob)), max(1, int(pr * 0.3)))
    pygame.draw.arc(s, (70, 44, 28), (x - r * 0.22, y + r * 0.40 + bob, r * 0.44, r * 0.30), math.pi, 2 * math.pi, max(2, int(r * 0.05)))
    for i in range(3):                                       # jingle bell collar
        pygame.draw.circle(s, (250, 205, 60), (int(x - r * 0.3 + i * r * 0.3), int(y + r * 0.74 + bob)), max(2, int(r * 0.09)))

def d_gingerbread(s, x, y, r, u):    # GINGERBREAD — LEGENDARY 1/1,200
    glow(s, (255, 190, 110), x, y, int(r * 2.1), 55)
    sw = math.sin(u * 2.2) * r * 0.05
    body = (196, 126, 62); icing = (252, 250, 245)
    pygame.draw.circle(s, body, (int(x + sw), int(y - r * 0.56)), int(r * 0.38))
    pygame.draw.rect(s, body, (x - r * 0.36 + sw * 0.6, y - r * 0.26, r * 0.72, r * 0.86), border_radius=int(r * 0.18))
    for k in (-1, 1):
        a = math.sin(u * 2.2 + k) * 0.22
        pygame.draw.line(s, body, (x + k * r * 0.30 + sw * 0.6, y - r * 0.12),
                         (x + k * r * (0.82 + a * 0.2), y - r * (0.34 + a)), max(3, int(r * 0.26)))
        pygame.draw.line(s, body, (x + k * r * 0.22, y + r * 0.50),
                         (x + k * r * (0.46 - a * 0.1), y + r * 1.16), max(3, int(r * 0.28)))
    for k in (-1, 1):                                        # icing trim
        pygame.draw.line(s, icing, (x + k * r * 0.34 + sw * 0.6, y - r * 0.14),
                         (x + k * r * 0.74, y - r * 0.32), max(1, int(r * 0.07)))
        pygame.draw.line(s, icing, (x + k * r * 0.26, y + r * 0.74), (x + k * r * 0.40, y + r * 1.04), max(1, int(r * 0.07)))
    for i in range(3):
        pygame.draw.line(s, icing, (x - r * 0.28 + sw * 0.6, y + r * (0.02 + i * 0.18)),
                         (x + r * 0.28 + sw * 0.6, y + r * (0.02 + i * 0.18)), max(1, int(r * 0.05)))
    for i, c in enumerate(((235, 70, 80), (70, 190, 110), (250, 215, 70))):
        pygame.draw.circle(s, c, (int(x + sw * 0.6), int(y + r * (0.10 + i * 0.22))), max(1, int(r * 0.08)))
    bl = blink(u, 3.6)
    for k in (-1, 1):
        ex, ey = x + sw + k * r * 0.14, y - r * 0.64
        if bl > 0.5: pygame.draw.circle(s, (46, 26, 16), (int(ex), int(ey)), max(1, int(r * 0.08)))
        else: pygame.draw.line(s, (46, 26, 16), (ex - r * 0.08, ey), (ex + r * 0.08, ey), max(2, int(r * 0.05)))
    pygame.draw.arc(s, (252, 250, 245), (x + sw - r * 0.20, y - r * 0.58, r * 0.40, r * 0.32), math.pi, 2 * math.pi, max(2, int(r * 0.06)))
    pygame.draw.circle(s, (240, 90, 100), (int(x + sw - r * 0.26), int(y - r * 0.50)), max(1, int(r * 0.06)))
    pygame.draw.circle(s, (240, 90, 100), (int(x + sw + r * 0.26), int(y - r * 0.50)), max(1, int(r * 0.06)))

def d_frozen(s, x, y, r, u):         # FROZEN SHADOW — MYTHIC 1/40,000
    glow(s, (120, 220, 255), x, y, int(r * 2.5), 70)
    ic = (150, 225, 255)
    pts = []                                                  # jagged ice body
    rnd = random.Random(21)
    for i in range(14):
        a = i / 14 * math.tau
        rad = r * (0.78 + 0.26 * rnd.random() + 0.05 * math.sin(u * 2 + i))
        pts.append((x + math.cos(a) * rad, y + math.sin(a) * rad * 1.08))
    pygame.draw.polygon(s, (24, 40, 64), pts)
    pygame.draw.polygon(s, ic, pts, max(2, int(r * 0.06)))
    for i in range(7):                                        # cracks
        a = u * 0.2 + i * 0.9
        pygame.draw.line(s, (200, 245, 255), (x, y), (x + math.cos(a) * r * 0.8, y + math.sin(a) * r * 0.8), max(1, int(r * 0.03)))
    for i in range(6):                                        # frozen spikes
        a = i / 6 * math.tau + u * 0.25
        tipx, tipy = x + math.cos(a) * r * 1.42, y + math.sin(a) * r * 1.42
        b1 = (x + math.cos(a + 0.16) * r * 0.9, y + math.sin(a + 0.16) * r * 0.9)
        b2 = (x + math.cos(a - 0.16) * r * 0.9, y + math.sin(a - 0.16) * r * 0.9)
        pygame.draw.polygon(s, mix(ic, (255, 255, 255), 0.25), [b1, b2, (tipx, tipy)])
    sh = 0.5 + 0.5 * math.sin(u * 2.6)
    for k in (-1, 1):                                         # the two frozen eyes
        ex, ey = x + k * r * 0.30, y - r * 0.12
        glow(s, (190, 250, 255), int(ex), int(ey), int(r * 0.5), int(60 + 50 * sh))
        pygame.draw.circle(s, (235, 252, 255), (int(ex), int(ey)), max(2, int(r * 0.13)))
    for i in range(8):                                        # falling frost
        a = i * 0.9
        fy = (u * 38 + i * 31) % (r * 2.8) - r * 1.4
        pygame.draw.circle(s, (210, 245, 255), (int(x + math.cos(a) * r * 1.15), int(y + fy)), max(1, int(r * 0.045)))

def d_manger(s, x, y, r, u):         # MANGER — the old manager of the factory (STORY ch.3) — EPIC 1/225
    glow(s, (190, 190, 210), x, y, int(r * 1.9), 40)
    sway = math.sin(u * 1.1) * r * 0.03
    pygame.draw.polygon(s, (72, 74, 92), [(x - r * 0.78 + sway, y + r * 1.02), (x - r * 0.52 + sway, y + r * 0.02),
                                          (x + r * 0.52 + sway, y + r * 0.02), (x + r * 0.78 + sway, y + r * 1.02)])
    pygame.draw.polygon(s, (226, 228, 238), [(x - r * 0.22 + sway, y + r * 0.04), (x + r * 0.22 + sway, y + r * 0.04),
                                             (x + r * 0.14 + sway, y + r * 1.02), (x - r * 0.14 + sway, y + r * 1.02)])
    pygame.draw.polygon(s, (190, 60, 70), [(x - r * 0.12 + sway, y + r * 0.08), (x + r * 0.12 + sway, y + r * 0.08),
                                           (x + r * 0.07 + sway, y + r * 0.62), (x - r * 0.07 + sway, y + r * 0.62)])
    pygame.draw.circle(s, (214, 180, 150), (int(x + sway), int(y - r * 0.40)), int(r * 0.44))
    pygame.draw.ellipse(s, (170, 172, 184), (x - r * 0.48 + sway, y - r * 0.92, r * 0.96, r * 0.52))   # grey hair
    pygame.draw.rect(s, (170, 172, 184), (x - r * 0.48 + sway, y - r * 0.70, r * 0.16, r * 0.34), border_radius=int(r * 0.06))
    pygame.draw.rect(s, (170, 172, 184), (x + r * 0.32 + sway, y - r * 0.70, r * 0.16, r * 0.34), border_radius=int(r * 0.06))
    bl = blink(u, 4.0)
    for k in (-1, 1):                                         # tired eyes behind glasses
        ex, ey = x + sway + k * r * 0.18, y - r * 0.44
        pygame.draw.circle(s, (248, 248, 252), (int(ex), int(ey)), int(r * 0.13))
        if bl > 0.5: pygame.draw.circle(s, (40, 38, 50), (int(ex), int(ey)), max(1, int(r * 0.065)))
        else: pygame.draw.line(s, (40, 38, 50), (ex - r * 0.11, ey), (ex + r * 0.11, ey), max(2, int(r * 0.05)))
        pygame.draw.circle(s, (120, 124, 150), (int(ex), int(ey)), int(r * 0.19), max(1, int(r * 0.035)))
    pygame.draw.line(s, (120, 124, 150), (x + sway - r * 0.05, y - r * 0.44), (x + sway + r * 0.05, y - r * 0.44), max(1, int(r * 0.035)))
    pygame.draw.ellipse(s, (160, 162, 176), (x - r * 0.30 + sway, y - r * 0.18, r * 0.60, r * 0.22))   # moustache
    pygame.draw.arc(s, (120, 80, 70), (x + sway - r * 0.16, y - r * 0.18, r * 0.32, r * 0.22), math.pi, 2 * math.pi, max(1, int(r * 0.04)))
    bx = x + r * 0.62 + sway                                   # the clipboard he never puts down
    pygame.draw.rect(s, (150, 110, 60), (bx - r * 0.18, y + r * 0.18, r * 0.42, r * 0.56), border_radius=int(r * 0.05))
    pygame.draw.rect(s, (245, 245, 250), (bx - r * 0.13, y + r * 0.24, r * 0.32, r * 0.44))
    for i in range(3):
        pygame.draw.line(s, (150, 150, 165), (bx - r * 0.09, y + r * (0.30 + i * 0.10)), (bx + r * 0.15, y + r * (0.30 + i * 0.10)), max(1, int(r * 0.025)))

def d_lia(s, x, y, r, u):            # LIA SAID — MYTHIC 1/10,000  (Man Studio friend)
    glow(s, (255, 150, 220), x, y, int(r * 2.3), 60)
    sway = math.sin(u * 1.4) * r * 0.04
    for i in range(10):                                        # sparkles around her
        a = u * 0.8 + i * 0.63
        rr = r * (1.25 + 0.12 * math.sin(u * 2 + i))
        pygame.draw.circle(s, (255, 210, 245), (int(x + math.cos(a) * rr), int(y + math.sin(a) * rr * 0.9)), max(1, int(r * 0.05)))
    pygame.draw.polygon(s, (120, 60, 160), [(x - r * 0.70 + sway, y + r * 1.04), (x - r * 0.46 + sway, y + r * 0.06),
                                            (x + r * 0.46 + sway, y + r * 0.06), (x + r * 0.70 + sway, y + r * 1.04)])
    pygame.draw.circle(s, (238, 196, 170), (int(x + sway), int(y - r * 0.34)), int(r * 0.46))
    hair = (62, 40, 32)
    pygame.draw.ellipse(s, hair, (x - r * 0.56 + sway, y - r * 0.92, r * 1.12, r * 0.78))
    for k in (-1, 1):                                          # long hair down the sides
        pygame.draw.ellipse(s, hair, (x + k * r * 0.40 - r * 0.20 + sway, y - r * 0.62, r * 0.40, r * 1.16))
    bl = blink(u, 3.0)
    for k in (-1, 1):
        ex, ey = x + sway + k * r * 0.19, y - r * 0.36
        pygame.draw.circle(s, (250, 250, 255), (int(ex), int(ey)), int(r * 0.15))
        if bl > 0.5:
            pygame.draw.circle(s, (64, 40, 28), (int(ex + math.sin(u * 0.9) * r * 0.03), int(ey)), int(r * 0.085))
            pygame.draw.circle(s, (255, 255, 255), (int(ex - r * 0.04), int(ey - r * 0.04)), max(1, int(r * 0.03)))
        else:
            pygame.draw.line(s, (64, 40, 28), (ex - r * 0.13, ey), (ex + r * 0.13, ey), max(2, int(r * 0.05)))
        pygame.draw.line(s, (40, 26, 20), (ex - r * 0.14, ey - r * 0.22), (ex + r * 0.14, ey - r * 0.24), max(1, int(r * 0.045)))
    pygame.draw.arc(s, (190, 90, 110), (x + sway - r * 0.17, y - r * 0.26, r * 0.34, r * 0.26), math.pi, 2 * math.pi, max(2, int(r * 0.055)))
    hy = y - r * 0.86                                           # a little star clip
    pts = []
    for i in range(10):
        a = -math.pi / 2 + i * math.pi / 5
        rad = r * (0.17 if i % 2 == 0 else 0.07)
        pts.append((x + sway - r * 0.40 + math.cos(a) * rad, hy + math.sin(a) * rad))
    pygame.draw.polygon(s, (255, 210, 70), pts)

def d_sos(s, x, y, r, u):            # SOS — SECRET (flash the light switch: ... --- ...)
    ph = u * 0.9 % 3.0
    bright = 1.0 if ph < 1.9 else max(0.0, 1.0 - (ph - 1.9) * 1.2)
    glow(s, (255, 90, 70), x, y, int(r * 2.6 * (0.7 + 0.5 * bright)), int(40 + 60 * bright))
    glow(s, (255, 230, 170), x, y, int(r * 1.3), int(50 + 70 * bright))
    pygame.draw.line(s, (90, 90, 110), (x - r * 0.1, y + r * 1.3), (x + r * 0.05, y + r * 0.35), max(2, int(r * 0.09)))
    for i in range(16):                                         # smoke trail
        a = -math.pi / 2 + math.sin(u * 1.2 + i * 0.4) * 0.5
        d = r * (0.4 + i * 0.09)
        pygame.draw.circle(s, (70, 64, 84), (int(x + math.cos(a) * d * 0.25), int(y + r * 0.5 + d * 0.55)), max(1, int(r * (0.05 + i * 0.006))))
    core = r * (0.26 + 0.05 * math.sin(u * 7))
    pygame.draw.circle(s, (255, 250, 230), (int(x), int(y)), int(core * (0.8 + 0.5 * bright)))
    pygame.draw.circle(s, (255, 170, 80), (int(x), int(y)), int(core * 1.5 * (0.8 + 0.4 * bright)), max(1, int(r * 0.05)))
    rnd = random.Random(5)
    for i in range(22):                                         # sparks shooting out
        a = rnd.uniform(0, math.tau) + u * 0.4
        d = r * (0.5 + ((u * 1.6 + i * 0.37) % 1.0) * 1.5)
        fade = 1.0 - ((u * 1.6 + i * 0.37) % 1.0)
        col = mix((255, 240, 180), (255, 70, 50), 1 - fade)
        pygame.draw.circle(s, col, (int(x + math.cos(a) * d), int(y + math.sin(a) * d)), max(1, int(r * 0.07 * fade)))
    seq = [1, 1, 1, 0, 2, 2, 2, 0, 1, 1, 1]                     # ... --- ...  written in light
    bw = r * 0.16; total = sum((bw * (0.5 if q == 1 else 1.2) + bw * 0.32) if q else bw * 0.5 for q in seq)
    px = x - total / 2; by = y + r * 1.02
    step = int(u * 3.2) % len(seq)
    for i, q in enumerate(seq):
        if q == 0: px += bw * 0.5; continue
        w_ = bw * (0.5 if q == 1 else 1.2)
        on = 1.0 if i <= step else 0.22
        pygame.draw.rect(s, mix((60, 50, 60), (255, 220, 120), on), (px, by, w_, bw * 0.34), border_radius=int(bw * 0.15))
        px += w_ + bw * 0.32

def C(key, name, rar, odds, src, fn, hint="", season=None):
    return {"key": key, "name": name, "rar": rar, "odds": odds, "src": src, "fn": fn, "hint": hint, "season": season}
CHARS = [
    C("red", "RED", "COMMON", 2, "THE COLORS", d_color((235, 64, 64))),
    C("blue", "BLUE", "COMMON", 2, "THE COLORS", d_color((60, 120, 255))),
    C("green", "GREEN", "COMMON", 3, "THE COLORS", d_color((60, 200, 100))),
    C("yellow", "YELLOW", "COMMON", 3, "THE COLORS", d_color((250, 210, 50))),
    C("purple", "PURPLE", "COMMON", 4, "THE COLORS", d_color((170, 90, 240))),
    C("orange", "ORANGE", "COMMON", 4, "THE COLORS", d_color((255, 140, 40))),
    C("pink", "PINK", "COMMON", 5, "THE COLORS", d_color((255, 105, 180))),
    C("cyan", "CYAN", "COMMON", 6, "THE COLORS", d_color((60, 220, 230))),
    C("crimson", "CRIMSON KING", "RARE", 8, "STORY  CH.1", d_crimson),
    C("ocean", "OCEAN LORD", "RARE", 10, "STORY  CH.1", d_ocean),
    C("gray", "GRAY WORKER", "RARE", 15, "STORY  CH.3", d_gray),
    C("candy", "CANDY GHOST", "RARE", 25, "THE HAUNT", d_candy),
    C("pumpkin", "PUMPKIN", "RARE", 20, "THE HAUNT", d_pumpkin),
    C("maple", "MAPLE LEAF", "RARE", 30, "MAPLE BLOSSOM", d_maple),
    C("sun", "SUN THIEF", "EPIC", 40, "STORY  CH.1", d_sun),
    C("earth", "SHADOW OF EARTH", "EPIC", 60, "STORY  CH.2", d_earth),
    C("life", "SHADOW OF LIFE", "EPIC", 80, "STORY  CH.2", d_life),
    C("fire", "SHADOW OF FIRE", "EPIC", 100, "STORY  CH.2", d_fire),
    C("chroma", "CHROMA", "EPIC", 150, "STORY", d_chroma),
    C("frost", "FROST BORN", "EPIC", 120, "FIRST FROST", d_frost),
    C("cake", "BIRTHDAY CAKE", "EPIC", 200, "HAPPY BIRTHDAY", d_cake),
    C("galaxy", "GALAXY", "EPIC", 250, "SEASON 1", d_galaxy),
    C("white", "WHITE", "LEGENDARY", 400, "STORY  CH.4", d_white),
    C("black", "BLACK", "LEGENDARY", 400, "STORY  CH.4", d_black),
    C("complete", "COMPLETE SHADOW", "LEGENDARY", 1000, "STORY  CH.2", d_complete),
    C("matic", "SHADOW-MATIC 3000", "LEGENDARY", 1500, "STORY  CH.3", d_matic),
    C("shadow3", "SHADOW", "LEGENDARY", 2500, "STORY  CH.3", d_shadow3),
    C("watcher", "THE WATCHER", "CORRUPTED", 6666, "TAPE 001", d_watcher),
    C("rewind", "REWIND", "CORRUPTED", 8888, "TAPE 001", d_rewind),
    C("static", "STATIC", "CORRUPTED", 9999, "TAPE 002", d_static),
    C("theshadow", "THE SHADOW", "MYTHIC", 25000, "STORY", d_theshadow),
    C("glitch", "THE GLITCH", "MYTHIC", 33333, "THE GLITCH STORM", d_glitch),
    C("pixel", "PIXEL MANOR", "MYTHIC", 50000, "THE MUSIC", d_pixel),
    C("luna", "LUNAVR_TESTER", "DEVELOPER", 500000, "MAN STUDIO TEAM", d_luna),
    C("man", "MAN STUDIO", "DEVELOPER", 1000000, "THE DEVS", d_man),
    C("penguin", "PENGUIN", "RARE", 30, "WINTER", d_penguin, season="winter"),
    C("snowman", "SNOWMAN", "EPIC", 90, "WINTER", d_snowman, season="winter"),
    C("reindeer", "REINDEER", "EPIC", 180, "WINTER", d_reindeer, season="winter"),
    C("manger", "MANGER", "EPIC", 225, "STORY  CH.3", d_manger),
    C("gingerbread", "GINGERBREAD", "LEGENDARY", 1200, "WINTER", d_gingerbread, season="winter"),
    C("lia", "LIA SAID", "MYTHIC", 10000, "MAN STUDIO FRIEND", d_lia),
    C("frozen", "FROZEN SHADOW", "MYTHIC", 40000, "WINTER", d_frozen, season="winter"),
    C("burger", "MR_BURGER", "DEVELOPER", 250000, "MAN STUDIO FRIEND", d_burger),
    C("dobe", "DOBE", "SECRET", 0, "DOBE'S WORKSHOP", d_dobe, "38 years later, the gears still turn..."),
    C("skeleton", "SKELETON", "SECRET", 0, "THE MANSION", d_skeleton, "Turn off the lights. Spell what's left of him."),
    C("sos", "SOS", "SECRET", 0, "THE SIGNAL", d_sos, "Three short. Three long. Three short. Make them see you."),
]
if not NEW_CHARS_ENABLED:                       # not released yet -> not in the game at all
    CHARS = [c for c in CHARS if c["key"] not in NEW_CHAR_KEYS]
CH = {c["key"]: c for c in CHARS}
def _clean_save():
    """A save can come from the cloud or from a newer build and name characters this
    build does not have. Never let that break a roll."""
    try:
        if S.get("best") not in CH:
            ks = [k for k in S.get("found", {}) if k in CH and CH[k]["odds"]]
            S["best"] = max(ks, key=lambda k: CH[k]["odds"]) if ks else None
        if S.get("companion") not in CH: S["companion"] = None
        S["history"] = [h for h in S.get("history", []) if isinstance(h, (list, tuple)) and h and h[0] in CH]
    except Exception as e:
        print("clean save:", e); S["best"] = None; S["companion"] = None; S["history"] = []
_ROLLABLE_CACHE = {}
def rollable():
    """The characters you can roll right now (the winter ones only during the event)."""
    k = (today() + ("|p" if (today() < WINTER_FROM and winter_now()) else "")) if winter_now() else "off"
    if k not in _ROLLABLE_CACHE:
        _ROLLABLE_CACHE.clear()
        _ROLLABLE_CACHE[k] = sorted([c for c in CHARS if c["odds"] and (not c["season"] or winter_now())],
                                    key=lambda c: -c["odds"])
    return _ROLLABLE_CACHE[k]
ROLLABLE = rollable()
def odds_text(c): return tr("SECRET") if not c["odds"] else L("1 in {0}", f"{c['odds']:,}")

def roll(luck=1.0, force=None):
    if force: return CH[force]
    for c in rollable():
        if random.random() < min(1.0, luck / c["odds"]): return c
    return CH["red"]

_thumb = {}
def thumb(key, r, dark=False):
    k = (key, r, dark)
    if k not in _thumb:
        sz = int(r * 4.2); s = pygame.Surface((sz, sz), pygame.SRCALPHA)
        CH[key]["fn"](s, sz // 2, sz // 2, r, 0.5)
        if dark:
            m = pygame.mask.from_surface(s); s = m.to_surface(setcolor=(18, 16, 30, 255), unsetcolor=(0, 0, 0, 0))
        _thumb[k] = s
    return _thumb[k]

# ---------------------------------------------------------------------------
#  badges (inside RNG)
# ---------------------------------------------------------------------------
BADGES = [
    ("first_roll", "FIRST ROLL", "Roll for the first time", (60, 200, 100)),
    ("rolls_100", "ROLLER", "Roll 100 times", (60, 140, 255)),
    ("rolls_1000", "DICE MASTER", "Roll 1,000 times", (170, 90, 240)),
    ("legendary", "LEGENDARY PULL", "Find a LEGENDARY character", (250, 190, 40)),
    ("corrupted", "HE IS COMING", "Find a character from the TAPES", (60, 255, 120)),
    ("mythic", "MYTHIC", "Find a MYTHIC character", (235, 50, 70)),
    ("luna", "TESTED BY LUNA", "Roll LUNAVR_TESTER", (150, 120, 255)),
    ("dev", "YOU ROLLED THE DEVS", "Roll MAN STUDIO (1 in 1,000,000)", (255, 215, 90)),
    ("secret", "EGG HUNTER", "Find a SECRET character", WHITE),
    ("both_secrets", "NOTHING STAYS HIDDEN", "Find both SECRET characters", (255, 170, 60)),
    ("index_full", "COMPLETE INDEX", f"Find all {len(CHARS)} characters", (255, 105, 180)),
    ("shiny", "SHINY!", "Roll a SHINY character (1 in 50)", (255, 240, 160)),
    ("shiny10", "SPARKLE COLLECTOR", "Find 10 different SHINY characters", (255, 200, 240)),
    ("streak7", "EVERY DAY", "Claim the daily gift 7 days in a row", (60, 220, 230)),
    ("tester", "TESTER.COM", "Man Studio team only", (120, 230, 255)),
    ("winter", "SNOW DAY", "Find a WINTER character", (150, 225, 255)),
    ("winter_all", "WINTER COMPLETE", "Find all 5 WINTER characters", (120, 200, 255)),
    ("gingerbread", "FRESH FROM THE OVEN", "Roll GINGERBREAD", (230, 150, 70)),
    ("frozen", "FROZEN IN TIME", "Roll FROZEN SHADOW", (120, 220, 255)),
    ("sos", "DISTRESS SIGNAL", "Send SOS with the lights", (255, 120, 80)),
    ("friends", "GOOD COMPANY", "Find MR_BURGER and LIA SAID", (255, 180, 120)),
    ("boxes10", "GIFT OPENER", "Open 10 winter boxes", (120, 190, 255)),
]
WINTER_KEYS = ("penguin", "snowman", "reindeer", "gingerbread", "frozen")
NEW_BADGE_IDS = ("winter", "winter_all", "gingerbread", "frozen", "sos", "friends", "boxes10")
if not NEW_CHARS_ENABLED:
    BADGES = [b for b in BADGES if b[0] not in NEW_BADGE_IDS]
BADGE = {b[0]: b for b in BADGES}
_clean_save()
TOASTS = []
def award(bid):
    if bid in S["badges"] or bid not in BADGE: return
    S["badges"].append(bid); TOASTS.append([bid, time.time()]); play("badge"); NET["dirty"] = True; save_local()
def check_badges(c):
    award("first_roll")
    if S["rolls"] >= 100: award("rolls_100")
    if S["rolls"] >= 1000: award("rolls_1000")
    r = c["rar"]
    if r == "LEGENDARY": award("legendary")
    if r == "CORRUPTED": award("corrupted")
    if r == "MYTHIC": award("mythic")
    if c["key"] == "luna": award("luna")
    if c["key"] == "man": award("dev")
    if r == "SECRET": award("secret")
    if "dobe" in S["found"] and "skeleton" in S["found"]: award("both_secrets")
    if all(k in S["found"] for k in CH): award("index_full")
    if c["key"] in WINTER_KEYS: award("winter")
    if all(k in S["found"] for k in WINTER_KEYS): award("winter_all")
    if c["key"] == "gingerbread": award("gingerbread")
    if c["key"] == "frozen": award("frozen")
    if c["key"] == "sos": award("sos")
    if "burger" in S["found"] and "lia" in S["found"]: award("friends")
    if S.get("stats", {}).get("boxes", 0) >= 10: award("boxes10")

SHINY_ODDS = 50          # 1 in 50 rolls comes out SHINY
def give(c, shiny=False):
    k = c["key"]; new = k not in S["found"]; S["found"][k] = S["found"].get(k, 0) + 1
    if new:
        earn(NEW_CHAR_BONUS, "new"); G["new_bonus"] = time.time()
        flash(L("NEW CHARACTER!  +{0} coins", NEW_CHAR_BONUS), (255, 220, 90))
    if shiny:
        S["shiny"][k] = S["shiny"].get(k, 0) + 1; award("shiny")
        if len(S["shiny"]) >= 10: award("shiny10")
    S["history"] = (S.get("history", []) + [[k, 1 if shiny else 0]])[-10:]
    st = S.setdefault("stats", {})
    if c["odds"]:
        if c["rar"] in ("LEGENDARY", "CORRUPTED", "MYTHIC", "DEVELOPER"): st["since_legendary"] = 0
        else:
            st["since_legendary"] = st.get("since_legendary", 0) + 1
            st["longest_dry"] = max(st.get("longest_dry", 0), st["since_legendary"])
        if c["odds"] > st.get("luckiest", 0): st["luckiest"] = c["odds"]
    if k not in S["first"]: S["first"][k] = today()
    if S.get("best") not in CH or (c["odds"] or 10 ** 9) > (CH[S["best"]]["odds"] or 10 ** 9): S["best"] = k
    check_badges(c); NET["dirty"] = True; save_local()
    if c["rar"] in ("LEGENDARY", "CORRUPTED", "MYTHIC", "DEVELOPER", "SECRET"): post_feed(c)
    FX["shake"] = {"LEGENDARY": 8, "CORRUPTED": 12, "MYTHIC": 16, "DEVELOPER": 22, "SECRET": 14}.get(c["rar"], 0)

FX = {"shake": 0.0, "parts": []}
def burst(x, y, col, n=24, speed=380):
    for _ in range(n):
        a = random.random() * 6.283; v = random.uniform(0.3, 1.0) * speed
        FX["parts"].append([x, y, math.cos(a) * v, math.sin(a) * v - 120, random.uniform(0.5, 1.0), col if col else random.choice(CVALS)])
def draw_parts(surf, dt):
    keep = []
    for p in FX["parts"]:
        p[0] += p[2] * dt; p[1] += p[3] * dt; p[3] += 700 * dt; p[4] -= dt
        if p[4] > 0:
            keep.append(p); sz = max(2, int(8 * p[4]))
            pygame.draw.rect(surf, p[5], (int(p[0]), int(p[1]), sz, sz))
    FX["parts"] = keep[-400:]

# ---------------------------------------------------------------------------
#  UI helpers
# ---------------------------------------------------------------------------
HOVER = {}
MOUSE = (0, 0); CLICK = None
# ---- REDESIGN (v1.0.5): jelly style, like the Color Under Pressure logo ----
OUTLINE = (16, 12, 30)                       # the dark outline around everything
_OL_DIRS = [(math.cos(a * math.pi / 8), math.sin(a * math.pi / 8)) for a in range(16)]
_otc = {}
def otxt(name, size, text, col=WHITE, ol=OUTLINE, w=None, depth=0):
    """Text with a thick dark outline (and an optional 3D drop)."""
    w = max(2, size // 12) if w is None else w
    k = (name, size, text, col, ol, w, depth, S.get("lang"))
    if k not in _otc:
        if len(_otc) > 1500: _otc.clear()
        a = txt(name, size, text, col); o = txt(name, size, text, ol)
        sf = pygame.Surface((a.get_width() + w * 2, a.get_height() + w * 2 + depth), pygame.SRCALPHA)
        for dd in range(0, depth + 1):
            for dx, dy in _OL_DIRS: sf.blit(o, (w + round(dx * w), w + round(dy * w) + dd))
        if depth: sf.blit(txt(name, size, text, mix(col, (0, 0, 0), 0.5)), (w, w + depth))
        sf.blit(a, (w, w)); _otc[k] = sf
    return _otc[k]
def ofit(name, size, text, maxw, col=WHITE, ol=OUTLINE):
    while size > 8:
        fn, sz, t_ = _prep(name, size, text)
        if font(fn, sz).size(t_)[0] + 6 <= maxw: break
        size -= 2
    return otxt(name, size, text, col, ol)

def _vgrad(w, h, top, bot, a=255):
    g = pygame.Surface((w, h), pygame.SRCALPHA)
    for y in range(h): pygame.draw.line(g, mix(top, bot, y / max(1, h - 1)) + (a,), (0, y), (w, y))
    return g
def _rr_mask(sf, rad):
    """Cut a surface to a rounded rectangle."""
    m = pygame.Surface(sf.get_size(), pygame.SRCALPHA)
    pygame.draw.rect(m, (255, 255, 255, 255), m.get_rect(), border_radius=rad)
    sf.blit(m, (0, 0), special_flags=pygame.BLEND_RGBA_MULT); return sf

_jel = {}
def jelly(text, size, col, name="bungee"):
    """Big shiny letters with a dark outline and a 3D bottom - the logo style."""
    k = (text, size, col, name, S.get("lang"))
    if k not in _jel:
        if len(_jel) > 300: _jel.clear()
        g = txt(name, size, text, WHITE); gw, gh = g.get_size()
        face = _vgrad(gw, gh, mix(col, WHITE, 0.38), mix(col, (0, 0, 0), 0.10))
        face.blit(g, (0, 0), special_flags=pygame.BLEND_RGBA_MULT)
        gl = pygame.Surface((gw, gh), pygame.SRCALPHA)
        pygame.draw.ellipse(gl, (255, 255, 255, 95), (int(gw * 0.10), int(gh * 0.22), int(gw * 0.62), max(4, int(gh * 0.16))))
        gl.blit(g, (0, 0), special_flags=pygame.BLEND_RGBA_MULT); face.blit(gl, (0, 0))
        w = max(3, size // 13); d = max(3, size // 11)
        ol = txt(name, size, text, OUTLINE); dk = txt(name, size, text, mix(col, (0, 0, 0), 0.48))
        sf = pygame.Surface((gw + w * 2, gh + w * 2 + d), pygame.SRCALPHA)
        for dd in range(0, d + 1, 2):
            for dx, dy in _OL_DIRS: sf.blit(ol, (w + round(dx * w), w + round(dy * w) + dd))
        sf.blit(dk, (w, w + d)); sf.blit(face, (w, w)); _jel[k] = sf
    return _jel[k]

def title(surf, text, col=WHITE, y=46, size=44):
    """Screen title in the logo style."""
    im = jelly(text, size, col)
    if im.get_width() > W - 120: im = pygame.transform.smoothscale(im, (W - 120, int(im.get_height() * (W - 120) / im.get_width())))
    blit(surf, im, (W // 2, y))

def _snowcap(sf, x, y, w, seed):
    """A little snow on top of a button / panel (winter event)."""
    rr = random.Random(seed)
    pygame.draw.rect(sf, (240, 248, 255), (x + 10, y - 2, w - 20, 7), border_radius=4)
    for _ in range(max(3, w // 26)):
        cx = x + 12 + rr.random() * (w - 24); r_ = rr.randint(4, 8)
        pygame.draw.circle(sf, (240, 248, 255), (int(cx), y + 2), r_)
        pygame.draw.circle(sf, (200, 220, 245), (int(cx), y + 2), r_, 1)

_btc = {}
def _btn_surf(w, h, base, k, rad, snow):
    kk = (w, h, base, k, rad, snow)
    if kk not in _btc:
        if len(_btc) > 600: _btc.clear()
        face_c = mix(base, WHITE, 0.07 * k)
        sf = pygame.Surface((w + 8, h + 12), pygame.SRCALPHA)
        pygame.draw.rect(sf, OUTLINE, (0, 0, w + 8, h + 12), border_radius=rad + 4)
        pygame.draw.rect(sf, mix(base, (0, 0, 0), 0.48), (4, 8, w, h), border_radius=rad)
        face = _rr_mask(_vgrad(w, h, mix(face_c, WHITE, 0.30), mix(face_c, (0, 0, 0), 0.08)), rad)
        sf.blit(face, (4, 4))
        gl = pygame.Surface((w, h), pygame.SRCALPHA)
        pygame.draw.rect(gl, (255, 255, 255, 70), (int(w * 0.05), int(h * 0.10), int(w * 0.90), max(3, int(h * 0.26))), border_radius=max(2, rad // 2))
        sf.blit(gl, (4, 4))
        pygame.draw.rect(sf, mix(face_c, WHITE, 0.45), (4, 4, w, h), 2, border_radius=rad)
        if snow: _snowcap(sf, 4, 4, w, w * 7 + h)
        _btc[kk] = sf
    return _btc[kk]

def button(surf, key, rect, label, col, enabled=True, size=26, icon=None):
    r = pygame.Rect(rect); hv = enabled and r.collidepoint(MOUSE)
    k = HOVER.get(key, 0.0); k += ((1.0 if hv else 0.0) - k) * 0.25; HOVER[key] = k
    base = col if enabled else (70, 70, 85)
    lift = int(round(3 * k)); rad = min(16, r.h // 3)
    pressed = enabled and hv and pygame.mouse.get_pressed()[0]
    if pressed: lift = -3
    sf = _btn_surf(r.w, r.h, base, int(round(k * 4)), rad, _winter_ui())
    surf.blit(sf, (r.x - 4, r.y - 4 - lift))
    lab = ofit("bungee", size, label, r.w - 18, WHITE if enabled else (165, 165, 180))
    blit(surf, lab, (r.centerx, r.centery - lift))
    return enabled and CLICK is not None and r.collidepoint(CLICK)

_pnc = {}
def panel(surf, rect, col=(20, 16, 38), border=(90, 80, 140), a=235):
    x, y, w, h = [int(v) for v in rect]
    kk = (w, h, col, border, a, _winter_ui() and w >= 300 and h >= 200)
    if kk not in _pnc:
        if len(_pnc) > 500: _pnc.clear()
        sf = pygame.Surface((w + 6, h + 6), pygame.SRCALPHA)
        pygame.draw.rect(sf, OUTLINE + (min(255, a + 15),), (0, 0, w + 6, h + 6), border_radius=21)
        inner = _rr_mask(_vgrad(w, h, mix(col, border, 0.16), col, a), 18)
        sf.blit(inner, (3, 3))
        pygame.draw.rect(sf, border + (255,), (3, 3, w, h), 2, border_radius=18)
        hl = pygame.Surface((w, h), pygame.SRCALPHA)
        pygame.draw.line(hl, mix(border, WHITE, 0.5) + (110,), (18, 6), (w - 18, 6), 2)
        sf.blit(hl, (3, 3))
        if kk[5]: _snowcap(sf, 3, 3, w, w + h)
        _pnc[kk] = sf
    surf.blit(_pnc[kk], (x - 3, y - 3))

def _winter_ui():
    try: return winter_now()
    except Exception: return False

_bgc = {}
_VIG = []
def _vignette():
    if not _VIG:
        sm = pygame.Surface((96, 54), pygame.SRCALPHA)
        for yy in range(54):
            for xx in range(96):
                d = math.hypot((xx - 47.5) / 48, (yy - 26.5) / 30)
                sm.set_at((xx, yy), (0, 0, 0, int(min(200, max(0, (d - 0.55) * 260)))))
        _VIG.append(pygame.transform.smoothscale(sm, (W, H)))
    return _VIG[0]
def background(surf, t, top=(26, 16, 58), bot=(6, 4, 16)):
    win = _winter_ui()
    if win: top, bot = mix(top, (28, 58, 108), 0.45), mix(bot, (4, 10, 26), 0.45)
    k = (top, bot)
    if k not in _bgc:
        if len(_bgc) > 40: _bgc.clear()
        g = pygame.Surface((W, H))
        for y in range(H): pygame.draw.line(g, mix(top, bot, y / H), (0, y), (W, y))
        _bgc[k] = g
    surf.blit(_bgc[k], (0, 0))
    # two big soft lights that drift slowly
    l1 = mix(top, (120, 90, 255) if not win else (140, 200, 255), 0.55)
    l2 = mix(top, (255, 90, 160) if not win else (200, 230, 255), 0.45)
    glow(surf, l1, W * 0.22 + math.sin(t * 0.21) * 90, H * 0.30 + math.cos(t * 0.17) * 50, 300, 34, 6)
    glow(surf, l2, W * 0.80 + math.cos(t * 0.19) * 90, H * 0.72 + math.sin(t * 0.23) * 50, 280, 28, 6)
    # floating colour pieces (little gems)
    for i in range(40):
        rr = random.Random(i); x = (rr.random() * W + t * rr.uniform(8, 30)) % W; y = (rr.random() * H - t * rr.uniform(10, 40)) % H
        c = mix(rr.choice(CVALS), top, 0.40); sz = rr.choice((4, 5, 6, 7))
        if i % 3 == 0:
            pygame.draw.polygon(surf, c, [(x, y - sz), (x + sz * 0.7, y), (x, y + sz), (x - sz * 0.7, y)])
        else:
            pygame.draw.rect(surf, c, (x, y, sz, sz), border_radius=2)
    if win:                                   # winter event: snow behind every screen
        for i in range(70):
            rr = random.Random(500 + i); sp = rr.uniform(14, 40); r_ = rr.uniform(1.0, 3.0)
            y = (rr.random() * (H + 20) + t * sp) % (H + 20) - 10
            x = (rr.random() * W + math.sin(t * 0.7 + i) * 14) % W
            pygame.draw.circle(surf, (215, 232, 255) if not G.get("dark") else (90, 100, 130), (int(x), int(y)), max(1, int(r_)))
    surf.blit(_vignette(), (0, 0))

def draw_card(surf, c, cx, cy, scale, t, reveal=1.0, shiny=False):
    col = RAR[c["rar"]]; cw, ch = 300, 400
    cs = pygame.Surface((cw, ch), pygame.SRCALPHA)
    if shiny:
        hue = [(255, 120, 120), (255, 230, 120), (120, 255, 160), (120, 200, 255), (220, 140, 255)]
        col = hue[int(t * 6) % 5]
    pygame.draw.rect(cs, mix((16, 14, 26), col, 0.12) + (255,), (0, 0, cw, ch), border_radius=22)
    pygame.draw.rect(cs, col, (0, 0, cw, ch), 6, border_radius=22)
    pygame.draw.rect(cs, col, (0, 0, cw, 52), border_top_left_radius=22, border_top_right_radius=22)
    _g = pygame.Surface((cw - 40, 12), pygame.SRCALPHA); pygame.draw.rect(_g, (255, 255, 255, 80), _g.get_rect(), border_radius=6); cs.blit(_g, (20, 7))
    pygame.draw.rect(cs, OUTLINE, (0, 0, cw, ch), 4, border_radius=22)
    blit(cs, fit("bungee", 30, c["rar"], cw - 30, (15, 10, 20) if c["rar"] != "SECRET" else (40, 40, 60)), (cw // 2, 27))
    c["fn"](cs, cw // 2, 180, 66, t)
    blit(cs, fit("bungee", 32, c["name"], cw - 30), (cw // 2, 300))
    blit(cs, txt("russo", 17, c["src"], mix(col, WHITE, 0.4)), (cw // 2, 336))
    blit(cs, txt("bungee", 20, odds_text(c), col), (cw // 2, 370))
    if shiny:
        for i in range(14):
            rr = random.Random(i); a = t * 2 + rr.random() * 6.28; tw = abs(math.sin(t * 4 + i))
            sx, sy = 20 + rr.random() * (cw - 40), 60 + rr.random() * 220
            if tw > 0.5:
                pygame.draw.line(cs, WHITE, (sx - 6 * tw, sy), (sx + 6 * tw, sy), 2); pygame.draw.line(cs, WHITE, (sx, sy - 6 * tw), (sx, sy + 6 * tw), 2)
        pygame.draw.rect(cs, (255, 250, 220), (cw - 96, 60, 84, 28), border_radius=8)
        blit(cs, txt("bungee", 18, "SHINY", (160, 110, 20)), (cw - 54, 74))
    if scale != 1.0: cs = pygame.transform.smoothscale(cs, (max(1, int(cw * scale)), max(1, int(ch * scale))))
    surf.blit(cs, cs.get_rect(center=(int(cx), int(cy))))

def rays(surf, x, y, col, t, a=60, n=14, L=900):
    lay = pygame.Surface((W, H), pygame.SRCALPHA)
    for i in range(n):
        ang = t * 0.4 + i * 2 * math.pi / n
        p = [(x, y), (x + math.cos(ang - 0.07) * L, y + math.sin(ang - 0.07) * L), (x + math.cos(ang + 0.07) * L, y + math.sin(ang + 0.07) * L)]
        pygame.draw.polygon(lay, col + (int(a),), p)
    surf.blit(lay, (0, 0))

# ---------------------------------------------------------------------------
#  game state
# ---------------------------------------------------------------------------
G = {"state": "main", "t": 0.0, "cool": 0.0, "roll": None, "luck_next": 1.0, "boost_until": 0.0,
     "msg": None, "msg_t": 0.0, "sel": None, "gear": 0, "gear_spin": 0.0, "dark": False, "typed": "",
     "force": None, "login_name": "", "login_pw": "", "login_field": 0, "egg": None, "confirm": None, "shop_busy": False, "wbox": None}
if S.get("login"):
    G["login_name"] = S["login"].get("name", "")
    sign_in(S["login"]["name"], silent=True)

def flash(msg, col=(255, 140, 120)):
    G["msg"] = (msg, col); G["msg_t"] = time.time()

def current_luck():
    L = 1.0
    if time.time() < G["boost_until"]: L *= 2
    if time.time() < G.get("mega_until", 0): L *= G.get("mega_mult", 100)   # MEGA BOOST (from codes)
    L *= G["luck_next"]
    if (S["rolls"] + 1) % BONUS_EVERY == 0: L *= 2
    return L

def demo_left(): return max(0, DEMO_ROLLS - int(S.get("demo_rolls", 0) or 0))
def demo_over(): return not AUTH["user"] and demo_left() <= 0
def start_roll():
    if G["roll"] or G["cool"] > 0: return
    if demo_over():
        G["demo_box"] = True; G["demo_seen"] = True; S["auto"] = False
        flash("Sign in to keep playing", (255, 180, 150)); play("error"); return
    if not AUTH["user"]: S["demo_rolls"] = int(S.get("demo_rolls", 0) or 0) + 1
    luck = current_luck(); c = roll(luck, G["force"]); G["force"] = None
    st = S.setdefault("stats", {})
    if G["luck_next"] > 1: st["lucky_rolls"] = st.get("lucky_rolls", 0) + 1
    if (S["rolls"] + 1) % BONUS_EVERY == 0: st["bonus_rolls"] = st.get("bonus_rolls", 0) + 1
    if S.get("auto"): st["auto_rolls"] = st.get("auto_rolls", 0) + 1
    st["best_luck"] = max(st.get("best_luck", 1), luck)
    d = st.setdefault("days", [])
    if today() not in d: d.append(today())
    G["luck_next"] = 1.0; S["rolls"] += 1
    big = c["rar"] in ("LEGENDARY", "CORRUPTED", "MYTHIC", "DEVELOPER")
    shiny = random.random() < 1 / SHINY_ODDS or G.pop("force_shiny", False)
    new = c["key"] not in S["found"]
    G["cool"] = FREE_COOLDOWN
    burst(W // 2, 400, None, 30, 420)
    if not (big or new or shiny or (c["rar"] == "EPIC" and not S.get("auto"))):
        # QUICK roll: a little reel above the button, the game keeps going
        G["quick"] = {"c": c, "t": 0.0, "shiny": False, "luck": luck,
                      "reel": [random.choice(ROLLABLE[-12:])["key"] for _ in range(8)] + [c["key"]]}
        give(c); return
    dur = 5.2 if c["key"] == "man" else (3.8 if big else 1.6)
    reel = [random.choice(ROLLABLE)["key"] if random.random() < 0.3 else random.choice(ROLLABLE[-14:])["key"] for _ in range(22)]
    G["roll"] = {"c": c, "t": 0.0, "dur": dur, "big": big, "luck": luck, "given": False, "snd": 0, "shiny": shiny, "reel": reel + [c["key"]]}
    play("rise") if big else None

def finish_roll():
    r = G["roll"]
    if r and not r["given"]: give(r["c"], r.get("shiny")); r["given"] = True
    G["roll"] = None

def fmt_luck(x):
    """x2, x100, x100,000 (no 1e+07)"""
    return f"{int(x):,}" if x >= 1000 or float(x).is_integer() else f"{x:g}"
def item_name(k):
    if k.startswith("mega"): return f"{tr('MEGA BOOST')} x{fmt_luck(int(k[4:] or 100))}"
    return tr({"lucky": "LUCKY ROLL", "super": "SUPER LUCKY ROLL", "boost": "LUCK BOOST"}[k])
def inv_keys():
    ks = ["lucky", "super", "boost"] + sorted([k for k in S["inv_got"] if k.startswith("mega")], key=lambda k: int(k[4:] or 100))
    return [k for k in ks if inv_have(k) > 0]
def inv_have(k): return max(0, int(S["inv_got"].get(k, 0)) - int(S["inv_used"].get(k, 0)))
def use_item(k):
    if inv_have(k) <= 0: return
    S["inv_used"][k] = int(S["inv_used"].get(k, 0)) + 1
    if k == "lucky": G["luck_next"] = max(G["luck_next"], 10.0)
    elif k == "super": G["luck_next"] = max(G["luck_next"], 100.0)
    elif k.startswith("mega"):               # MEGA BOOST: x(100 x mega) luck for 5 minutes
        mult = int(k[4:] or 100); now = time.time()
        if now < G.get("mega_until", 0) and G.get("mega_mult", 0) == mult: G["mega_until"] += 300
        else: G["mega_mult"] = max(mult, G.get("mega_mult", 0) if now < G.get("mega_until", 0) else 0); G["mega_until"] = now + 300
    else: G["boost_until"] = max(time.time(), G["boost_until"]) + 300
    NET["dirty"] = True; save_local(); play("epic")
    flash(L("{0} is ON!", item_name(k)), (120, 255, 160))

def redeem(code):
    """Codes live in Firebase /rng_codes/<CODE> = {lucky, super, boost, starts, expires, active}.
    Used codes: /rng_codes_used/<uid>/<CODE> (the rules let you write it only once)."""
    code = re.sub(r"[^A-Z0-9_-]", "", code.upper())
    if not code: return
    if not AUTH["user"]: flash("Sign in to use codes"); play("error"); return
    G["code_busy"] = True
    def run():
        try:
            uid = AUTH["user"]["uid"]
            c = fb("GET", f"/rng_codes/{code}")
            if c is FBERR: return flash("No connection")
            if not isinstance(c, dict) or c.get("active") is False: play("error"); return flash("This code doesn't exist")
            if c.get("starts") and today() < c["starts"]: play("error"); return flash("This code isn't active yet")
            if c.get("expires") and today() > c["expires"]: play("error"); return flash("This code expired")
            if code in S["codes"] or fb("GET", f"/rng_codes_used/{uid}/{code}") not in (None, FBERR):
                play("error"); return flash("You already used this code")
            if fb("PUT", f"/rng_codes_used/{uid}/{code}", int(time.time())) in (None, FBERR):
                play("error"); return flash("You already used this code")
            got = []
            for k, nm in (("lucky", "LUCKY ROLL"), ("super", "SUPER LUCKY ROLL"), ("boost", "LUCK BOOST")):
                n = int(c.get(k, 0) or 0)
                if n > 0: S["inv_got"][k] = int(S["inv_got"].get(k, 0)) + n; got.append(f"{n}x {tr(nm)}")
            m = int(c.get("mega", 0) or 0)          # mega 1 = x100 luck, mega 1000 = x100,000 luck (5 minutes)
            if m > 0:
                mk = f"mega{100 * m}"; S["inv_got"][mk] = int(S["inv_got"].get(mk, 0)) + 1; got.append(item_name(mk))
            S["codes"].append(code); G["code"] = ""; NET["dirty"] = True; save_local(); cloud_push()
            play("legendary"); flash(L("CODE ACCEPTED!  {0}", ", ".join(got) if got else ""), (120, 255, 160))
        finally:
            G["code_busy"] = False
    bg(run)

# shop items: (key, name, desc, price)
SHOP = [("lucky", "LUCKY ROLL", "Next roll: x10 luck", 100),
        ("super", "SUPER LUCKY ROLL", "Next roll: x100 luck", 500),
        ("boost", "LUCK BOOST", "x2 luck for 5 minutes", 300)]
def buy(item):
    if not AUTH["user"]: flash("Sign in with your Color Under Pressure account to use coins"); play("error"); return
    if G["shop_busy"]: return
    G["shop_busy"] = True
    def run():
        refresh_coins(); have = coins()
        if have is None: flash("No connection"); play("error")
        elif have < item[3]: flash(L("Not enough coins ({0})", have)); play("error")
        else:
            S["spent"] += item[3]; st = S.setdefault("stats", {}); st["coins_spent"] = st.get("coins_spent", 0) + item[3]
            save_local(); cloud_push()
            if item[0] == "lucky": G["luck_next"] = max(G["luck_next"], 10.0)
            elif item[0] == "super": G["luck_next"] = max(G["luck_next"], 100.0)
            else: G["boost_until"] = max(time.time(), G["boost_until"]) + 300
            flash(L("{0}!  -{1} coins", tr(item[1]), item[3]), (120, 255, 160)); play("epic")
        G["shop_busy"] = False
    bg(run)

# ---------------------------------------------------------------------------
#  screens
# ---------------------------------------------------------------------------
_LOGO = {}
def draw_logo(surf, t, cx, cy, sc=1.0):
    """COLOR UNDER PRESSURE: RNG - big jelly R N G + the orange banner (like the main game's logo)."""
    for i, (ch, col) in enumerate(zip("RNG", [(240, 72, 90), (70, 215, 120), (70, 145, 245)])):
        im = jelly(ch, int(84 * sc), col)
        ang = math.sin(t * 1.6 + i * 1.3) * 4 + (-6, 0, 6)[i]
        bob = math.sin(t * 2.2 + i * 1.1) * 4 * sc
        im = pygame.transform.rotozoom(im, ang, 1.0)
        surf.blit(im, im.get_rect(center=(int(cx + (i - 1) * 104 * sc), int(cy - 14 * sc + bob))))
    k = ("ban", sc, S.get("lang"))
    if k not in _LOGO:
        bw, bh = int(420 * sc), int(40 * sc); sk = int(16 * sc)
        b = pygame.Surface((bw + 12, bh + 16), pygame.SRCALPHA)
        poly = lambda dx, dy: [(sk + dx, dy), (bw + dx, dy + 4 * sc), (bw - sk + dx, bh + dy), (dx, bh + dy - 4 * sc)]
        pygame.draw.polygon(b, OUTLINE, poly(6, 10)); pygame.draw.polygon(b, OUTLINE, [(x_ - 0, y_) for x_, y_ in poly(4, 4)], 0)
        g = _vgrad(bw + 12, bh + 16, (255, 132, 40), (232, 52, 92))
        m = pygame.Surface((bw + 12, bh + 16), pygame.SRCALPHA); pygame.draw.polygon(m, (255, 255, 255, 255), poly(6, 4))
        g.blit(m, (0, 0), special_flags=pygame.BLEND_RGBA_MULT); b.blit(g, (0, 0))
        pygame.draw.polygon(b, OUTLINE, poly(6, 4), max(2, int(3 * sc)))
        lab = ofit("bungee", int(23 * sc), "COLOR UNDER PRESSURE", bw - 40)
        b.blit(lab, lab.get_rect(center=((bw + 12) // 2 + 2, (bh + 8) // 2 + 4)))
        _LOGO[k] = pygame.transform.rotozoom(b, 1.5, 1.0)
    ban = _LOGO[k]
    surf.blit(ban, ban.get_rect(center=(int(cx), int(cy + 48 * sc))))

_MCH = {}
def draw_machine(surf, t, r, ready):
    """The gold frame of a lucky machine around ROLL, with lights running around it."""
    fr = r.inflate(50, 36)
    if "frame" not in _MCH:
        sf = pygame.Surface((fr.w + 8, fr.h + 14), pygame.SRCALPHA)
        pygame.draw.rect(sf, OUTLINE, (0, 0, fr.w + 8, fr.h + 14), border_radius=48)
        pygame.draw.rect(sf, (150, 96, 20), (4, 10, fr.w, fr.h), border_radius=44)
        face = _rr_mask(_vgrad(fr.w, fr.h, (255, 226, 120), (214, 140, 30)), 44); sf.blit(face, (4, 4))
        pygame.draw.rect(sf, (255, 240, 180), (4, 4, fr.w, fr.h), 2, border_radius=44)
        hole = pygame.Rect(4 + 18, 4 + 13, fr.w - 36, fr.h - 26)
        pygame.draw.rect(sf, OUTLINE, hole.inflate(6, 6), border_radius=40)
        pygame.draw.rect(sf, (30, 16, 50), hole, border_radius=38)
        _MCH["frame"] = sf
    surf.blit(_MCH["frame"], (fr.x - 4, fr.y - 4))
    # the lights: a chase that runs faster when AUTO is on
    n = 22; per = fr.w * 2 + fr.h * 2; sp = 9 if S.get("auto") else 5
    for i in range(n):
        d = (i / n) * per
        if d < fr.w: x, y = fr.x + d, fr.y + 8
        elif d < fr.w + fr.h: x, y = fr.right - 9, fr.y + (d - fr.w)
        elif d < fr.w * 2 + fr.h: x, y = fr.right - (d - fr.w - fr.h), fr.bottom - 8
        else: x, y = fr.x + 9, fr.bottom - (d - fr.w * 2 - fr.h)
        x = min(max(x, fr.x + 26), fr.right - 26) if y in (fr.y + 8, fr.bottom - 8) else x
        y = min(max(y, fr.y + 22), fr.bottom - 22) if x in (fr.x + 9, fr.right - 9) else y
        on = ((int(t * sp) - i) % 3 == 0) if ready else (i % 2 == int(t * 2) % 2)
        c = (255, 250, 200) if on else (150, 90, 30)
        if on: glow(surf, (255, 230, 120), x, y, 14, 70, 3)
        pygame.draw.circle(surf, OUTLINE, (int(x), int(y)), 6); pygame.draw.circle(surf, c, (int(x), int(y)), 4)

def top_bar(surf):
    # coins + account
    panel(surf, (16, 12, 330, 56))
    if AUTH["user"]:
        co = coins()
        pygame.draw.circle(surf, (255, 205, 60), (46, 40), 15); pygame.draw.circle(surf, (200, 150, 30), (46, 40), 15, 3)
        blit(surf, txt("bungee", 24, "..." if co is None else f"{co:,}", (255, 220, 120)), (72, 40), "midleft")
        blit(surf, fit("russo", 18, AUTH["user"]["name"] + ("  [DEV]" if is_dev() else ""), 150, (190, 190, 220)), (330, 40), "midright")
    else:
        blit(surf, fit("russo", 18, L("DEMO  -  {0} rolls left", demo_left()), 300, (255, 215, 90) if demo_left() else (255, 140, 120)), (32, 40), "midleft")
    blit(surf, txt("russo", 16, L("ROLLS: {0}", f"{S['rolls']:,}"), (170, 170, 200)), (W - 20, 24), "topright")

def draw_main(surf, t, dt, events):
    background(surf, t)
    found = [k for k in CH if k in S["found"] and CH[k]["rar"] != "SECRET"]
    if found:                      # the characters you found float in the back
        for i in range(min(10, len(found))):
            rr = random.Random(i * 7 + 3); key = found[(i * 5) % len(found)]
            x = (rr.random() * W + t * rr.uniform(10, 25) * (1 if i % 2 else -1)) % (W + 120) - 60
            y = 160 + rr.random() * (H - 260) + math.sin(t * 0.8 + i) * 14
            im = thumb(key, 16); im2 = im.copy(); im2.set_alpha(55); surf.blit(im2, im2.get_rect(center=(int(x), int(y))))
    if G["dark"]:
        dk = pygame.Surface((W, H), pygame.SRCALPHA); dk.fill((0, 0, 0, 215)); surf.blit(dk, (0, 0))
    top_bar(surf)
    # title
    draw_logo(surf, t, W // 2, 92)
    # last rolls
    hist = S.get("history", [])[-10:]
    if hist:
        x0 = W // 2 - (len(hist) - 1) * 21
        for i, (k, sh) in enumerate(hist):
            if k not in CH: continue
            x = x0 + i * 42; rc = RAR[CH[k]["rar"]]
            pygame.draw.circle(surf, OUTLINE, (x, 186), 21); pygame.draw.circle(surf, mix((14, 12, 26), rc, 0.3), (x, 186), 18)
            pygame.draw.circle(surf, (255, 240, 160) if sh else rc, (x, 186), 18, 3 if sh else 2)
            im = thumb(k, 9); surf.blit(im, im.get_rect(center=(x, 186)))
    # daily gift
    if S.get("daily") != today() and game_open() and AUTH["user"]:
        gb = pygame.Rect(26, 82, 250, 50); pulse = 0.5 + 0.5 * math.sin(t * 5)
        glow(surf, (255, 215, 90), gb.centerx, gb.centery, 110, int(25 + 30 * pulse))
        if button(surf, "daily", gb, "DAILY GIFT!", (230, 150, 30), size=20): claim_daily()
    # companion
    comp = S.get("companion")
    if comp in CH and comp in S["found"]:
        bob = math.sin(t * 2) * 8; rc_ = RAR[CH[comp]["rar"]]
        glow(surf, rc_, 250, 400, 120, 40)
        sh_ = pygame.Surface((170, 34), pygame.SRCALPHA); pygame.draw.ellipse(sh_, (0, 0, 0, 110), sh_.get_rect()); surf.blit(sh_, (165, 466))
        pygame.draw.ellipse(surf, OUTLINE, (172, 462, 156, 30)); pygame.draw.ellipse(surf, mix(rc_, (20, 16, 40), 0.55), (176, 464, 148, 24))
        pygame.draw.ellipse(surf, mix(rc_, WHITE, 0.3), (176, 464, 148, 24), 2)
        CH[comp]["fn"](surf, 250, 400 + bob, 64, t)
        blit(surf, ofit("bungee", 20, CH[comp]["name"], 300, mix(rc_, WHITE, 0.4)), (250, 512))
    else:
        blit(surf, txt("russo", 18, "No companion yet", (130, 130, 160)), (250, 400))
        blit(surf, txt("russo", 15, "Pick one in the INDEX", (110, 110, 140)), (250, 424))
    # roll button
    cx, cy = W // 2, 400
    cool = G["cool"]; ready = cool <= 0 and not G["roll"]
    if demo_over() and not G["roll"] and not G.get("quick") and not G.get("demo_seen"): G["demo_box"] = True; G["demo_seen"] = True
    glow(surf, (60, 200, 100), cx, cy, 190 + int(10 * math.sin(t * 4)), 45 if ready else 15)
    r = pygame.Rect(0, 0, 300, 120); r.center = (cx, cy)
    hv = r.collidepoint(MOUSE) and ready
    draw_machine(surf, t, r, ready)
    hk = HOVER.get("roll", 0.0); hk += ((1.0 if hv else 0.0) - hk) * 0.25; HOVER["roll"] = hk
    lift = int(round(3 * hk))
    if hv and pygame.mouse.get_pressed()[0]: lift = -3
    if ready:
        surf.blit(_btn_surf(r.w, r.h, (50, 195, 95), int(round(hk * 4)), 34, False), (r.x - 4, r.y - 4 - lift))
    else:
        surf.blit(_btn_surf(r.w, r.h, (48, 82, 62), 0, 34, False), (r.x - 4, r.y - 4))
        if cool > 0:
            fw = int((r.w + 8) * (1 - cool / FREE_COOLDOWN))
            surf.set_clip(pygame.Rect(r.x - 4, r.y - 4, fw, r.h + 16))
            surf.blit(_btn_surf(r.w, r.h, (60, 150, 92), 0, 34, False), (r.x - 4, r.y - 4))
            surf.set_clip(None)
    blit(surf, otxt("bungee", 64, "ROLL", WHITE if ready else (200, 220, 205), OUTLINE, 5, 3), (r.centerx, r.centery - lift))
    luck_now = current_luck()
    lt = L("LUCK  x{0}", fmt_luck(luck_now))
    blit(surf, otxt("bungee", 24, lt, (255, 215, 90) if luck_now > 1 else (200, 200, 230)), (cx, cy + 104))
    sub = []
    if (S["rolls"] + 1) % BONUS_EVERY == 0: sub.append(tr("BONUS ROLL x2"))
    if G["luck_next"] > 1: sub.append(L("LUCKY ROLL x{0}", fmt_luck(G['luck_next'])))
    if time.time() < G["boost_until"]: sub.append(L("BOOST x2  {0}s", int(G['boost_until'] - time.time())))
    if time.time() < G.get("mega_until", 0): sub.append(L("MEGA x{0}  {1}s", fmt_luck(G.get("mega_mult", 100)), int(G['mega_until'] - time.time())))
    if sub: blit(surf, txt("russo", 18, "  •  ".join(sub), (120, 255, 160)), (cx, cy + 130))
    else: blit(surf, txt("russo", 16, L("Next BONUS ROLL in {0} rolls", BONUS_EVERY - (S['rolls'] % BONUS_EVERY) - 1), (160, 160, 195)), (cx, cy + 130))
    if CLICK and r.collidepoint(CLICK) and ready: start_roll(); play("click")
    draw_quick(surf, t, dt)
    # auto roll
    if button(surf, "auto", (cx - 110, cy + 150, 220, 44), "AUTO: ON" if S.get("auto") else "AUTO: OFF", (60, 140, 255) if S.get("auto") else (80, 80, 110), size=20):
        S["auto"] = not S.get("auto"); save_local()
    # right menu
    x0 = W - 300; y0 = 192; bh, gap = 42, 54
    if button(surf, "index", (x0, y0, 250, bh), "INDEX", (170, 90, 240), size=24): G["state"] = "index"; G["sel"] = None
    if button(surf, "collection", (x0, y0 + gap, 250, bh), "MY CHARACTERS", (235, 120, 50), size=20): G["state"] = "collection"; G["csel"] = None; bg(refresh_coins)
    if button(surf, "badges", (x0, y0 + gap * 2, 250, bh), "BADGES", (250, 170, 40), size=24): G["state"] = "badges"
    if button(surf, "stats", (x0, y0 + gap * 3, 250, bh), "STATS", (60, 190, 210), size=24): G["state"] = "stats"
    if button(surf, "leader", (x0, y0 + gap * 4, 250, bh), "LEADERBOARD", (235, 80, 120), size=22):
        G["state"] = "leader"
        if time.time() - LB["t"] > 30 and not LB["busy"]: bg(pull_leader)
    if button(surf, "shop", (x0, y0 + gap * 5, 250, bh), "LUCK SHOP", (60, 200, 100), size=24): G["state"] = "shop"; bg(refresh_coins)
    if button(surf, "settings", (x0, y0 + gap * 6, 250, bh), "SETTINGS", (90, 90, 130), size=24): G["state"] = "settings"
    _row = 7
    if winter_now():
        if button(surf, "wshop", (x0, y0 + gap * 7, 250, bh), "WINTER SHOP", (120, 205, 255), size=22):
            G["state"] = "wshop"; bg(refresh_coins)
        _row = 8
    if not AUTH["user"]:
        if button(surf, "signin", (x0, y0 + gap * _row, 250, bh), "SIGN IN", (60, 140, 255), size=24): G["state"] = "login"
    if S.get("auto"):                                                   # the AFK rule, said at the top
        left = AFK_LIMIT - (time.time() - G.get("last_input", time.time()))
        if left < 600: blit(surf, txt("russo", 16, L("Move the mouse!  Disconnect in {0}", f"{int(max(0, left)) // 60}:{int(max(0, left)) % 60:02d}"), (255, 110, 110)), (W // 2, 14))
        else: blit(surf, txt("russo", 14, "AUTO ROLL: no mouse or keys for 2 hours = disconnected", (150, 150, 185)), (W // 2, 14))
    # best
    if S.get("best") in CH:
        b = CH[S["best"]]; blit(surf, txt("russo", 16, "YOUR RAREST", (150, 150, 180)), (250, 560))
        blit(surf, fit("bungee", 22, f"{b['name']}  ({odds_text(b)})", 380, RAR[b["rar"]]), (250, 586))
    # secret 1: the old gear (DOBE). 38 clicks.
    gx, gy = 46, H - 46
    G["gear_spin"] *= 0.92
    ang = t * 0.15 + G["gear_spin"]
    gc = (70, 66, 90) if not G["dark"] else (40, 38, 52)
    for i in range(8):
        a = ang + i * math.pi / 4; pygame.draw.circle(surf, gc, (int(gx + math.cos(a) * 17), int(gy + math.sin(a) * 17)), 6)
    pygame.draw.circle(surf, gc, (gx, gy), 16); pygame.draw.circle(surf, mix(gc, (0, 0, 0), 0.5), (gx, gy), 6)
    if CLICK and math.hypot(CLICK[0] - gx, CLICK[1] - gy) < 26 and not G["roll"]:
        G["gear"] += 1; G["gear_spin"] += 1.2; play("tick")
        if G["gear"] >= 38: G["gear"] = 0; secret_found("dobe")
    # secret 2: the light switch (SKELETON). Dark + type BONES.
    lx, ly = W - 40, H - 52
    pygame.draw.rect(surf, (200, 200, 210) if not G["dark"] else (60, 60, 70), (lx - 14, ly - 22, 28, 44), border_radius=6)
    pygame.draw.rect(surf, (90, 90, 100), (lx - 6, ly - (14 if not G["dark"] else -2), 12, 14), border_radius=3)
    if CLICK and abs(CLICK[0] - lx) < 20 and abs(CLICK[1] - ly) < 28:
        G["dark"] = not G["dark"]; G["typed"] = ""; play("click")
        now = time.time()
        if "sos" not in CH: pass                        # SOS is part of a future update -> no morse at all
        elif G["dark"]:                                 # light just went OFF -> how long was it on?
            on = now - G.get("lit_at", now)
            if on < 2.5: G["morse"] = (G.get("morse", "") + ("." if on < 0.40 else "-"))[-9:]
            else: G["morse"] = ""
            if G.get("morse") == "...---...":
                G["morse"] = ""; G["dark"] = False; secret_found("sos")
        else:                                           # light went ON
            if now - G.get("off_at", 0) > 3.0: G["morse"] = ""
            G["lit_at"] = now
        G["off_at"] = now
        if "sos" not in CH: G["morse"] = ""
    if G.get("morse"):
        blit(surf, txt("russo", 20, G["morse"], (255, 210, 120)), (lx - 70, ly), "midright")
    if G["dark"]:
        for e in events:
            if e.type == pygame.TEXTINPUT:
                G["typed"] = (G["typed"] + e.text.upper())[-5:]
                if G["typed"] == "BONES": G["typed"] = ""; secret_found("skeleton")
    if winter_now():
        d1, d2 = WINTER_TO.split("-")[2], WINTER_TO.split("-")[1]
        if today() < WINTER_FROM:
            f1, f2 = WINTER_FROM.split("-")[2], WINTER_FROM.split("-")[1]
            blit(surf, txt("russo", 16, L("DEV PREVIEW  -  WINTER EVENT starts {0}", f1 + "/" + f2), (255, 190, 120)), (W // 2, 24))
        else:
            blit(surf, txt("russo", 16, L("WINTER EVENT  -  until {0}", d1 + "/" + d2), (150, 225, 255)), (W // 2, 24))
    # global feed (bottom)
    feed = NET["feed"][-3:]
    if feed:
        panel(surf, (W // 2 - 330, H - 112, 660, 96), (14, 12, 28), (60, 55, 100))
        blit(surf, txt("russo", 14, "GLOBAL  -  RARE ROLLS", (140, 140, 180)), (W // 2, H - 100))
        for i, f in enumerate(reversed(feed)):
            col = RAR.get(f.get("rar"), WHITE)
            line = L("{0} rolled {1}  ({2})", f.get('name', '?'), f.get('char', '?'), tr('SECRET') if not f.get('odds') else L("1 in {0}", format(int(f.get('odds')), ',')))
            blit(surf, fit("russo", 17, line, 630, col), (W // 2, H - 76 + i * 22))
    # keys
    for e in events:
        if e.type == pygame.KEYDOWN and e.key == pygame.K_SPACE and not G["dark"]: start_roll()
        if e.type == pygame.KEYDOWN and e.key == pygame.K_F2 and is_dev(): G["state"] = "dev"

def draw_quick(surf, t, dt):
    q = G.get("quick")
    if not q: return
    q["t"] += dt; u = q["t"]; c = q["c"]; col = RAR[c["rar"]]
    cx, cy = W // 2, 252
    a = 255 * clamp((1.5 - u) / 0.3) if u > 1.2 else 255
    if u > 1.5: G["quick"] = None; return
    spin = 0.45
    box = pygame.Surface((300, 92), pygame.SRCALPHA)
    pygame.draw.rect(box, (10, 8, 20, 220), (0, 0, 300, 92), border_radius=16)
    pygame.draw.rect(box, col + (255,), (0, 0, 300, 92), 3, border_radius=16)
    if u < spin:
        k = eo(u / spin); reel = q["reel"]; step = 74; pos = k * (len(reel) - 1) * step
        for i, key in enumerate(reel):
            x = 150 + i * step - pos
            if -40 < x < 340: im = thumb(key, 14, True); box.blit(im, im.get_rect(center=(int(x), 46)))
        n = int(pos / step)
        if n != q.get("snd"): q["snd"] = n; play("tick")
    else:
        if not q.get("rev"):
            q["rev"] = True; play({"COMMON": "common", "RARE": "rare"}.get(c["rar"], "epic"))
            burst(cx, cy, col, 14, 260)
        c["fn"](box, 46, 46, 22, t)
        blit(box, fit("bungee", 22, c["name"], 200), (92, 32), "midleft")
        blit(box, txt("russo", 15, c["rar"] + "  •  " + odds_text(c), col), (92, 62), "midleft")
    box.set_alpha(int(a)); surf.blit(box, box.get_rect(center=(cx, cy)))

def claim_daily():
    if S.get("daily") == today(): return
    y = (datetime.date.today() - datetime.timedelta(days=1)).isoformat()
    S["streak"] = (S.get("streak", 0) + 1) if S.get("daily") == y else 1
    S["daily"] = today()
    S["inv_got"]["lucky"] = int(S["inv_got"].get("lucky", 0)) + 1
    msg = L("DAILY GIFT: {0}", "1x " + tr("LUCKY ROLL"))
    if S["streak"] % 7 == 0:
        S["inv_got"]["super"] = int(S["inv_got"].get("super", 0)) + 1; award("streak7")
        msg += "  +  1x " + tr("SUPER LUCKY ROLL")
    NET["dirty"] = True; save_local(); play("legendary"); burst(150, 120, None, 50, 420)
    flash(msg + "   " + L("(day {0})", S["streak"]), (120, 255, 160))

def draw_demo_box(surf, t, dt, events):
    """Shown to guests after the 5 demo rolls."""
    dk = pygame.Surface((W, H), pygame.SRCALPHA); dk.fill((0, 0, 0, 200)); surf.blit(dk, (0, 0))
    panel(surf, (W // 2 - 380, 120, 760, 470), (24, 16, 44), (255, 215, 90))
    blit(surf, txt("bungee", 48, "THE DEMO IS OVER!", (255, 215, 90)), (W // 2, 180))
    have = [k for k in CH if k in S["found"]]
    for i, k in enumerate(have[:6]):   # only characters this build knows
        CH[k]["fn"](surf, W // 2 - (min(6, len(have)) - 1) * 55 + i * 110, 275, 34, t)
    blit(surf, fit("russo", 22, L("You found {0} characters. Want to keep rolling?", len(have)), 700, WHITE), (W // 2, 350))
    blit(surf, fit("russo", 19, "Sign in with your Color Under Pressure account. Your characters come with you!", 700, (200, 200, 230)), (W // 2, 388))
    blit(surf, fit("russo", 17, "No account? Make one for free in Color Under Pressure.", 700, (160, 160, 190)), (W // 2, 420))
    if button(surf, "demosign", (W // 2 - 140, 460, 280, 64), "SIGN IN", (60, 140, 255), size=28):
        G["demo_box"] = False; G["state"] = "login"
    if button(surf, "demolater", (W // 2 - 90, 538, 180, 40), "LATER", (80, 80, 110), size=16):
        G["demo_box"] = False

def secret_found(key):
    if key not in CH: return          # not in this build (a future update) -> nothing happens
    c = CH[key]
    G["egg"] = {"c": c, "t": 0.0}; play("glitch")

def draw_roll_overlay(surf, t, dt):
    r = G["roll"]; r["t"] += dt; u = r["t"]; c = r["c"]; col = RAR[c["rar"]]
    dk = pygame.Surface((W, H), pygame.SRCALPHA); dk.fill((0, 0, 0, 170 if not r["big"] else 235)); surf.blit(dk, (0, 0))
    spin = 0.55 if not r["big"] else (3.4 if c["key"] == "man" else 2.0)
    cx, cy = W // 2, H // 2 + 10
    if u < spin:
        k = u / spin
        if r["big"]:
            glow(surf, col if k > 0.6 else (180, 180, 220), cx, cy, int(160 + 260 * k), int(30 + 70 * k))
            if c["key"] == "man":
                blit(surf, txt("bungee", 34, "1 in 1,000,000...?", (255, 215, 90)), (cx, 70), alpha=255 * clamp(k * 2))
            elif k > 0.4:
                blit(surf, fit("bungee", 30, "SOMETHING RARE IS COMING...", W - 200, col), (cx, 70), alpha=255 * clamp((k - 0.4) * 3))
            if k > 0.7:
                for i in range(int(40 * k)):
                    rr = random.Random(i + int(u * 20)); pygame.draw.line(surf, mix(col, WHITE, 0.4), (cx, cy), (cx + rr.uniform(-1, 1) * W, cy + rr.uniform(-1, 1) * H), 2)
        # the REEL: cards slide by and slow down; the last one is yours
        reel = r["reel"]; step = 190; N = len(reel) - 1
        kk = eo(k) if not r["big"] else (1 - (1 - k) ** 4)
        pos = kk * N * step
        pygame.draw.rect(surf, (10, 8, 18), (0, cy - 150, W, 300))
        pygame.draw.line(surf, (60, 55, 90), (0, cy - 150), (W, cy - 150), 2); pygame.draw.line(surf, (60, 55, 90), (0, cy + 150), (W, cy + 150), 2)
        for i, key in enumerate(reel):
            x = cx + i * step - pos
            if x < -120 or x > W + 120: continue
            cc_ = CH[key]; rc = RAR[cc_["rar"]]
            card = pygame.Rect(0, 0, 160, 230); card.center = (int(x), cy)
            near = 1 - clamp(abs(x - cx) / 400)
            pygame.draw.rect(surf, mix((16, 14, 26), rc, 0.15), card, border_radius=14)
            pygame.draw.rect(surf, mix((60, 60, 80), rc, near), card, 4, border_radius=14)
            im = thumb(key, 34, True); surf.blit(im, im.get_rect(center=card.center))
            blit(surf, txt("bungee", 40, "?", mix((70, 70, 100), rc, near)), card.center)
        pygame.draw.polygon(surf, (255, 215, 90), [(cx - 16, cy - 172), (cx + 16, cy - 172), (cx, cy - 150)])
        pygame.draw.polygon(surf, (255, 215, 90), [(cx - 16, cy + 172), (cx + 16, cy + 172), (cx, cy + 150)])
        n = int(pos / step)
        if n != r["snd"]: r["snd"] = n; play("tick")
        return
    v = u - spin
    if not r.get("rev"):
        r["rev"] = True
        rk = c["rar"]
        play("boom") if r["big"] else None
        play({"COMMON": "common", "RARE": "rare", "EPIC": "epic"}.get(rk, "legendary"))
        if rk == "CORRUPTED": play("glitch")
        if not r["given"]: give(c, r.get("shiny")); r["given"] = True
        burst(cx, cy, col, 60 if r["big"] else 30, 600 if r["big"] else 400)
        if r.get("shiny"): burst(cx, cy, (255, 250, 220), 50, 500); play("badge")
    rays(surf, cx, cy, col, t, 40 + 50 * clamp(1 - v / 1.2), 14 if not r["big"] else 22)
    if r["big"]:
        for i in range(80 if c["key"] == "man" else 40):
            rr = random.Random(i); x = cx + rr.uniform(-1, 1) * 700 * eo(v / 1.5); y = cy - 200 + rr.uniform(-1, 0.3) * 400 * eo(v / 1.5) + 260 * v * v * 0.3
            pygame.draw.rect(surf, rr.choice(CVALS), (x, y, 10, 6))
    if c["rar"] == "MYTHIC" and v < 1.2:      # red lightning
        rr = random.Random(int(v * 12))
        for b in range(3):
            x0 = rr.uniform(100, W - 100); pts = [(x0, 0)]
            for j in range(8): pts.append((pts[-1][0] + rr.uniform(-60, 60), (j + 1) * H / 8))
            pygame.draw.lines(surf, (255, 80, 90), False, pts, 3)
    draw_card(surf, c, cx, cy, eob(v / 0.25) * (1.0 if not r["big"] else 1.1), t, shiny=r.get("shiny"))
    if c["rar"] == "CORRUPTED" and v < 0.9:   # VHS static + colour split
        rr = random.Random(int(v * 30))
        for j in range(26):
            y = rr.randrange(H); pygame.draw.rect(surf, (rr.randint(40, 220),) * 3, (0, y, W, rr.randint(1, 4)))
        for j in range(4):
            y = rr.randrange(H); pygame.draw.rect(surf, (60, 255, 120), (0, y, W, 2))
    if r.get("shiny") and v < 2:
        blit(surf, txt("bungee", 34, "✦ SHINY ✦" if False else "* SHINY *", (255, 240, 160)), (cx, cy + 250), alpha=255 * eo(v / 0.3))
    if v < 0.18:
        fl = pygame.Surface((W, H)); fl.fill(col); fl.set_alpha(int(200 * (1 - v / 0.18))); surf.blit(fl, (0, 0))
    if r["big"]:
        head = {"man": tr("YOU ROLLED THE DEVS!"), "luna": tr("A DEVELOPER APPEARED!")}.get(c["key"], c["rar"] + "!")
        blit(surf, txt("bungee", 46, head, col), (cx, 64), alpha=255 * eo(v / 0.4))
    new = S["found"].get(c["key"], 0) <= 1
    if new: blit(surf, txt("bungee", 26, "NEW!", (120, 255, 160)), (cx + 170, cy - 190), alpha=255 * eo((v - 0.2) / 0.3))
    if r["luck"] > 1: blit(surf, txt("russo", 18, L("luck x{0}", fmt_luck(r['luck'])), (200, 200, 230)), (cx, cy + 228))
    if u > r["dur"] or (CLICK and v > 0.3): finish_roll()

def draw_egg_overlay(surf, t, dt):
    e = G["egg"]; e["t"] += dt; u = e["t"]; c = e["c"]
    dk = pygame.Surface((W, H), pygame.SRCALPHA); dk.fill((0, 0, 0, 240)); surf.blit(dk, (0, 0))
    cx, cy = W // 2, H // 2 + 20
    if u < 1.6:
        lines = {"dobe": ["CLICK... CLICK... CLICK...", "38 YEARS LATER...", "SOMETHING WOKE UP."],
                 "skeleton": ["...", "BONES.", "HE HEARD YOU."],
                 "sos": ["...", "- - -", "SOMEONE ANSWERED."]}[c["key"]]
        lines = [tr(x) for x in lines]
        i = min(2, int(u / 0.55))
        rnd = random.Random(int(u * 30))
        blit(surf, txt("bungee", 44, lines[i], (255, 170, 60) if c["key"] == "dobe" else (120, 220, 255)), (cx + rnd.randint(-4, 4), cy + rnd.randint(-3, 3)))
        return
    v = u - 1.6
    if not e.get("rev"):
        e["rev"] = True; play("boom"); play("legendary")
        if c["key"] not in S["found"]: blit_new = True
        give(c)
    rays(surf, cx, cy, (255, 170, 60) if c["key"] == "dobe" else (120, 220, 255), t, 50, 18)
    draw_card(surf, c, cx, cy, eob(v / 0.3) * 1.1, t)
    blit(surf, txt("bungee", 46, "SECRET FOUND!", WHITE), (cx, 64), alpha=255 * eo(v / 0.4))
    blit(surf, txt("russo", 18, "click to continue", (170, 170, 200)), (cx, H - 30), alpha=255 * eo((v - 1) / 0.5))
    if v > 1.0 and CLICK: G["egg"] = None

def draw_index(surf, t, dt, events):
    background(surf, t, (30, 14, 50), (6, 4, 14))
    title(surf, "INDEX", (170, 90, 240), 46)
    have = sum(1 for k in CH if k in S["found"])
    blit(surf, txt("russo", 20, L("{0} / {1} FOUND", have, len(CHARS)), (200, 200, 230)), (W // 2, 86))
    cols = 8; gx0 = 40; gy0 = 116
    rows = (len(CHARS) + cols - 1) // cols
    chh = max(56, min(92, (H - 90 - gy0 - (rows - 1) * 8) // rows)); cw = min(92, chh)
    for i, c in enumerate(CHARS):
        x = gx0 + (i % cols) * (cw + 8); y = gy0 + (i // cols) * (chh + 8)
        rect = pygame.Rect(x, y, cw, chh); found = c["key"] in S["found"]; col = RAR[c["rar"]]
        sel = G["sel"] == c["key"]; hv = rect.collidepoint(MOUSE)
        pygame.draw.rect(surf, mix((18, 16, 32), col, 0.18 if found else 0.04), rect, border_radius=12)
        pygame.draw.rect(surf, col if (found or sel) else (60, 60, 80), rect, 3 if sel else (2 if hv else 1), border_radius=12)
        im = thumb(c["key"], max(13, int(chh * 0.20)), not found); surf.blit(im, im.get_rect(center=(rect.centerx, rect.y + int(chh * 0.41))))
        if S["shiny"].get(c["key"]):
            pygame.draw.circle(surf, (255, 240, 160), (rect.right - 11, rect.y + 11), 7)
            blit(surf, txt("bungee", 11, "S", (150, 100, 20)), (rect.right - 11, rect.y + 11))
        blit(surf, fit("russo", 12, c["name"] if found else "???", cw - 8, WHITE if found else (120, 120, 150)), (rect.centerx, rect.bottom - 12))
        if CLICK and rect.collidepoint(CLICK): G["sel"] = c["key"]; play("click")
    # detail
    px = 860; panel(surf, (px, 110, 390, 520))
    k = G["sel"]
    if k:
        c = CH[k]; found = k in S["found"]; col = RAR[c["rar"]]
        if found: c["fn"](surf, px + 195, 240, 70, t)
        else:
            im = thumb(k, 70, True); surf.blit(im, im.get_rect(center=(px + 195, 240)))
            blit(surf, txt("bungee", 80, "?", (90, 90, 120)), (px + 195, 240))
        blit(surf, fit("bungee", 32, c["name"] if found else "???", 360), (px + 195, 360))
        blit(surf, txt("bungee", 22, c["rar"], col), (px + 195, 396))
        blit(surf, txt("russo", 20, odds_text(c) + "   •   " + (c["src"] if found else "???"), (200, 200, 230)), (px + 195, 428))
        if found:
            blit(surf, txt("russo", 18, L("Found {0} times  •  first: {1}" if S['found'][k] != 1 else "Found {0} time  •  first: {1}", f"{S['found'][k]:,}", S['first'].get(k, '?')), (170, 170, 200)), (px + 195, 460))
            if S["shiny"].get(k):
                blit(surf, txt("bungee", 16, L("SHINY x{0}", S["shiny"][k]), (255, 230, 140)), (px + 195, 484))
            is_c = S.get("companion") == k
            if button(surf, "equip", (px + 75, 508, 240, 54), "COMPANION" if is_c else "SET COMPANION", (60, 200, 100) if is_c else (60, 140, 255), not is_c, 20):
                S["companion"] = k; NET["dirty"] = True; save_local(); play("rare")
        elif c["rar"] == "SECRET":
            blit(surf, fit("russo", 18, tr("HINT: ") + tr(c["hint"]), 360, (255, 220, 150)), (px + 195, 470))
        else:
            blit(surf, txt("russo", 18, "Keep rolling...", (150, 150, 180)), (px + 195, 470))
    else:
        blit(surf, txt("russo", 20, "Pick a character", (160, 160, 190)), (px + 195, 360))
    if button(surf, "back", (40, H - 74, 180, 52), "BACK", (90, 90, 130)) or any(e.type == pygame.KEYDOWN and e.key == pygame.K_ESCAPE for e in events):
        G["state"] = "main"

def _sell(k, n):
    c = CH[k]; n = max(0, min(n, owned(k)))
    if n <= 0 or not sell_price(c): return
    got = sell_price(c) * n
    S["sold"][k] = S["sold"].get(k, 0) + n; earn(got)
    st = S.setdefault("stats", {}); st["sold_total"] = st.get("sold_total", 0) + n
    burst(1055, 600, (255, 205, 60), 30, 420); play("rare")
    flash(L("Sold {0}x {1}  +{2} coins", n, c["name"], f"{got:,}"), (255, 220, 120))

def draw_collection(surf, t, dt, events):
    """MY CHARACTERS: everything you own, how many, what it's worth. SELL."""
    background(surf, t, (40, 22, 14), (8, 4, 4)); top_bar(surf)
    title(surf, "MY CHARACTERS", (235, 120, 50), 48)
    mine = [c for c in sorted(CHARS, key=lambda c: (RAR_ORDER.index(c["rar"]), c["odds"]), reverse=True) if owned(c["key"]) > 0]
    worth = sum(sell_price(c) * owned(c["key"]) for c in mine)
    blit(surf, txt("russo", 18, L("{0} characters  •  {1} in total  •  worth {2} coins", len(mine), f"{sum(owned(c['key']) for c in mine):,}", f"{worth:,}"), (230, 210, 170)), (W // 2, 86))
    if G.get("sell_ask"):                                               # are you sure?
        k, n = G["sell_ask"]; c = CH[k]
        dk = pygame.Surface((W, H), pygame.SRCALPHA); dk.fill((0, 0, 0, 200)); surf.blit(dk, (0, 0))
        panel(surf, (W // 2 - 300, 230, 600, 260), (30, 18, 14), RAR[c["rar"]])
        c["fn"](surf, W // 2, 300, 40, t)
        blit(surf, fit("bungee", 26, L("Sell {0}x {1}?", n, c["name"]), 560), (W // 2, 372))
        blit(surf, txt("russo", 20, L("+{0} coins", f"{sell_price(c) * n:,}"), (255, 220, 120)), (W // 2, 406))
        if button(surf, "sell_yes", (W // 2 - 250, 430, 230, 50), "YES, SELL", (220, 90, 60), size=22): _sell(k, n); G["sell_ask"] = None
        if button(surf, "sell_no", (W // 2 + 20, 430, 230, 50), "NO", (90, 90, 130), size=22): G["sell_ask"] = None
        return
    cols = 8; cw, chh = 92, 92; gx0 = 40; gy0 = 116
    if not mine: blit(surf, txt("russo", 22, "Roll to get characters!", (180, 170, 150)), (440, 330))
    for i, c in enumerate(mine[:40]):
        x = gx0 + (i % cols) * (cw + 8); y = gy0 + (i // cols) * (chh + 8)
        rect = pygame.Rect(x, y, cw, chh); col = RAR[c["rar"]]; sel = G.get("csel") == c["key"]; hv = rect.collidepoint(MOUSE)
        pygame.draw.rect(surf, mix((18, 16, 32), col, 0.2), rect, border_radius=12)
        pygame.draw.rect(surf, col, rect, 3 if sel else (2 if hv else 1), border_radius=12)
        im = thumb(c["key"], 17); surf.blit(im, im.get_rect(center=(rect.centerx, rect.y + 36)))
        n = owned(c["key"]); nb = txt("bungee", 14, f"x{n:,}", WHITE); r_ = nb.get_rect(topright=(rect.right - 5, rect.y + 4)).inflate(8, 2)
        pygame.draw.rect(surf, (0, 0, 0), r_, border_radius=8); surf.blit(nb, nb.get_rect(center=r_.center))
        p = sell_price(c)
        blit(surf, fit("russo", 12, f"{p:,}" if p else "-", cw - 10, (255, 215, 90) if p else (140, 140, 160)), (rect.centerx, rect.bottom - 12))
        if CLICK and rect.collidepoint(CLICK): G["csel"] = c["key"]; play("click")
    px = 860; panel(surf, (px, 110, 390, 520))
    k = G.get("csel")
    if k and owned(k) > 0:
        c = CH[k]; col = RAR[c["rar"]]; n = owned(k); p = sell_price(c)
        c["fn"](surf, px + 195, 220, 64, t)
        blit(surf, fit("bungee", 30, c["name"], 360), (px + 195, 320))
        blit(surf, txt("bungee", 20, c["rar"], col), (px + 195, 352))
        blit(surf, txt("russo", 20, L("You have {0}", f"{n:,}"), (220, 220, 240)), (px + 195, 386))
        if not p:
            blit(surf, fit("russo", 18, "Secret characters can't be sold", 360, (255, 200, 150)), (px + 195, 430))
        elif not AUTH["user"]:
            blit(surf, fit("russo", 18, "Sign in to sell characters", 360, (255, 200, 150)), (px + 195, 430))
        else:
            blit(surf, txt("russo", 18, L("Worth {0} coins each", f"{p:,}"), (255, 215, 90)), (px + 195, 414))
            keep1 = max(0, n - 1)
            comp = S.get("companion") == k
            opts = [("s1", L("SELL 1   +{0}", f"{p:,}"), 1, True),
                    ("s2", L("SELL ALL BUT 1   +{0}", f"{p * keep1:,}"), keep1, keep1 > 0),
                    ("s3", L("SELL ALL   +{0}", f"{p * n:,}"), n, not comp)]
            for j, (bk, lab, cnt, ok) in enumerate(opts):
                if button(surf, "sell_" + bk, (px + 35, 448 + j * 58, 320, 48), lab, (220, 110, 50) if j < 2 else (200, 60, 60), ok, 18):
                    if cnt * p >= 1000 or c["rar"] in ("MYTHIC", "DEVELOPER") or cnt == n: G["sell_ask"] = (k, cnt)
                    else: _sell(k, cnt)
            if comp: blit(surf, txt("russo", 13, "This is your companion: you can't sell the last one", (170, 160, 150)), (px + 195, 618))
    else:
        blit(surf, txt("russo", 20, "Pick a character", (160, 160, 190)), (px + 195, 300))
        blit(surf, fit("russo", 16, L("Every NEW character = +{0} coins", NEW_CHAR_BONUS), 360, (255, 215, 90)), (px + 195, 340))
    if button(surf, "back", (40, H - 74, 180, 52), "BACK", (90, 90, 130)) or any(e.type == pygame.KEYDOWN and e.key == pygame.K_ESCAPE for e in events):
        G["state"] = "main"

def draw_afk(surf, t):
    dk = pygame.Surface((W, H), pygame.SRCALPHA); dk.fill((0, 0, 0, 225)); surf.blit(dk, (0, 0))
    blit(surf, txt("bungee", 48, "DISCONNECTED", (255, 110, 110)), (W // 2, 270))
    blit(surf, txt("russo", 22, "You didn't move the mouse or press a key for 2 hours.", (220, 220, 240)), (W // 2, 330))
    blit(surf, txt("russo", 22, "AUTO ROLL was stopped.", (220, 220, 240)), (W // 2, 362))
    blit(surf, txt("russo", 18, "Click to continue", (160, 160, 190)), (W // 2, 430))

def draw_badges(surf, t, dt, events):
    background(surf, t, (40, 26, 10), (8, 5, 2))
    title(surf, "BADGES", (250, 170, 40), 46)
    shown = [b for b in BADGES if b[0] != "tester" or "tester" in S["badges"]]
    blit(surf, txt("russo", 20, f"{sum(1 for b in shown if b[0] in S['badges'])} / {len(shown)}", (220, 210, 190)), (W // 2, 86))
    for i, (bid, name, desc, col) in enumerate(shown):
        x = 44 + (i % 4) * 300; y = 112 + (i // 4) * 88
        got = bid in S["badges"]
        panel(surf, (x, y, 288, 78), (26, 20, 14) if got else (18, 16, 20), col if got else (70, 65, 60))
        cc = col if got else (70, 70, 80); bx, by = x + 40, y + 39
        if got: glow(surf, col, bx, by, 44, 50)
        pygame.draw.circle(surf, OUTLINE, (bx, by), 29); pygame.draw.circle(surf, cc, (bx, by), 26); pygame.draw.circle(surf, mix(cc, (0, 0, 0), 0.4), (bx, by), 26, 4)
        pygame.draw.ellipse(surf, mix(cc, WHITE, 0.45), (bx - 14, by - 21, 28, 9))
        pts = []
        for j in range(10):
            rr = 15 if j % 2 == 0 else 7; a = j * math.pi / 5 - math.pi / 2; pts.append((bx + rr * math.cos(a), by + 2 + rr * math.sin(a)))
        pygame.draw.polygon(surf, ((WHITE if col != WHITE else (40, 40, 60)) if got else (40, 40, 50)), pts)
        blit(surf, fit("bungee", 20, name if got or bid not in ("both_secrets",) else "???", 208, WHITE if got else (150, 150, 160)), (x + 76, y + 27), "midleft")
        blit(surf, fit("russo", 14, desc, 204, (200, 190, 170) if got else (120, 120, 130)), (x + 76, y + 55), "midleft")
    if button(surf, "back", (40, H - 74, 180, 52), "BACK", (90, 90, 130)) or any(e.type == pygame.KEYDOWN and e.key == pygame.K_ESCAPE for e in events):
        G["state"] = "main"


# ---------------------------------------------------------------------------
#  WINTER SHOP — boxes that only give winter characters
# ---------------------------------------------------------------------------
WINTER_BOXES = [
    # key, name, what it says, price, weights per winter character, shiny chance
    ("wbox",  "WINTER BOX",  "One winter character, for sure",
     250,  {"penguin": 58, "snowman": 25, "reindeer": 12, "gingerbread": 4.6, "frozen": 0.4}, 1 / 40),
    ("wbox3", "WINTER BOX x3", "Three winter characters",
     650,  {"penguin": 58, "snowman": 25, "reindeer": 12, "gingerbread": 4.6, "frozen": 0.4}, 1 / 40),
    ("gbox",  "GOLDEN WINTER BOX", "Much better odds - never a PENGUIN",
     1500, {"snowman": 44, "reindeer": 34, "gingerbread": 19, "frozen": 3.0}, 1 / 12),
]
WBOX = {b[0]: b for b in WINTER_BOXES}
def box_pick(bx):
    w = {k: v for k, v in bx[4].items() if k in CH}
    if not w: return None
    tot = sum(w.values()); r = random.uniform(0, tot)
    for k, v in w.items():
        r -= v
        if r <= 0: return CH[k]
    return CH[list(w)[0]]
def open_box(key):
    """Buy a box and open it. The characters come out one by one."""
    bx = WBOX[key]
    if not winter_now(): return                     # the event is off -> the shop does not work
    if not AUTH["user"]: flash("Sign in with your Color Under Pressure account to use coins"); play("error"); return
    if G["shop_busy"] or G.get("wbox"): return
    G["shop_busy"] = True
    def run():
        refresh_coins(); have = coins()
        if have is None: flash("No connection"); play("error")
        elif have < bx[3]: flash(L("Not enough coins ({0})", have)); play("error")
        else:
            S["spent"] += bx[3]; st = S.setdefault("stats", {})
            st["coins_spent"] = st.get("coins_spent", 0) + bx[3]
            st["boxes"] = st.get("boxes", 0) + 1
            n = 3 if key == "wbox3" else 1
            got = []
            for _ in range(n):
                c = box_pick(bx)
                if c is None: break
                sh = random.random() < bx[5]
                give(c, sh); check_badges(c); got.append((c, sh))
                if c["rar"] in ("LEGENDARY", "MYTHIC"): post_feed(c)
            save_local(); cloud_push()
            G["wbox"] = {"t": 0.0, "got": got, "i": 0, "name": bx[1]}
            play("epic")
        G["shop_busy"] = False
    bg(run)

def draw_wbox(surf, t, dt):
    """The opening animation: the present shakes, then the characters jump out."""
    b = G["wbox"]
    if not b or not b.get("got"): G["wbox"] = None; return; b["t"] += dt; u = b["t"]
    dk = pygame.Surface((W, H), pygame.SRCALPHA); dk.fill((4, 10, 20, 225)); surf.blit(dk, (0, 0))
    cx, cy = W // 2, H // 2 - 20
    SHAKE = 1.15
    if u < SHAKE:                                           # the box is shaking
        k = u / SHAKE
        ox = math.sin(u * 34) * 9 * k; oy = -abs(math.sin(u * 7)) * 16 * k
        sz = int(118 + 18 * k)
        glow(surf, (120, 210, 255), int(cx + ox), int(cy + oy), int(sz * 2.1), int(30 + 60 * k))
        bx_ = pygame.Rect(0, 0, sz * 2, int(sz * 1.6)); bx_.center = (int(cx + ox), int(cy + oy + 20))
        pygame.draw.rect(surf, (40, 92, 150), bx_, border_radius=12)
        pygame.draw.rect(surf, (150, 215, 255), bx_, 4, border_radius=12)
        pygame.draw.rect(surf, (235, 70, 85), (bx_.centerx - 14, bx_.y, 28, bx_.h))      # ribbon
        lid = pygame.Rect(0, 0, int(sz * 2.3), int(sz * 0.42)); lid.center = (int(cx + ox), bx_.y - int(10 * k * 4))
        pygame.draw.rect(surf, (52, 110, 175), lid, border_radius=10)
        pygame.draw.rect(surf, (170, 225, 255), lid, 4, border_radius=10)
        pygame.draw.rect(surf, (235, 70, 85), (lid.centerx - 14, lid.y, 28, lid.h))
        blit(surf, txt("bungee", 30, tr(b["name"]), (190, 230, 255)), (cx, cy + 150))
        for i in range(int(26 * k)):                        # snow bursting out
            a = i * 0.7 + u * 3
            d = sz * (0.6 + (i % 7) * 0.12)
            pygame.draw.circle(surf, (225, 240, 255), (int(cx + math.cos(a) * d), int(cy + math.sin(a) * d * 0.7)), 3)
        return
    idx = min(len(b["got"]) - 1, int((u - SHAKE) / 1.25))
    if idx != b["i"]:
        b["i"] = idx; play("rare")
    c, sh = b["got"][idx]
    k = min(1.0, ((u - SHAKE) - idx * 1.25) / 0.35)
    col = RAR[c["rar"]]
    glow(surf, col, cx, cy, int(230 * (0.5 + k)), int(50 + 40 * k))
    c["fn"](surf, cx, cy, int(60 + 58 * k), t)
    if sh:
        for i in range(14):
            a = t * 2 + i * 0.45; d = 110 + 26 * math.sin(t * 3 + i)
            pygame.draw.circle(surf, (255, 240, 170), (int(cx + math.cos(a) * d), int(cy + math.sin(a) * d)), 4)
    blit(surf, fit("bungee", 40, ("SHINY  " if sh else "") + c["name"], 620, col), (cx, cy + 150))
    blit(surf, txt("russo", 22, odds_text(c), (205, 215, 240)), (cx, cy + 192))
    if len(b["got"]) > 1:
        blit(surf, txt("russo", 18, f"{idx + 1} / {len(b['got'])}", (150, 160, 190)), (cx, cy + 228))
    if u > SHAKE + len(b["got"]) * 1.25:
        G["wbox"] = None

def draw_winter_shop(surf, t, dt, events):
    if not winter_now(): G["state"] = "main"; return
    background(surf, t, (12, 32, 62), (3, 6, 14))
    title(surf, "WINTER SHOP", (150, 215, 255))
    co = coins()
    if AUTH["user"]:
        blit(surf, txt("russo", 20, tr("Coins from Color Under Pressure: ") + ("..." if co is None else f"{co:,}"), (255, 220, 120)), (W // 2, 86))
    else:
        blit(surf, txt("russo", 20, "Sign in with your Color Under Pressure account to use your coins", (255, 180, 150)), (W // 2, 86))
    for i, bx in enumerate(WINTER_BOXES):
        x = 86 + i * 372; y = 118
        col = [(90, 180, 255), (120, 210, 255), (255, 205, 80)][i]
        panel(surf, (x, y, 330, 352), (10, 20, 36), col)
        bob = math.sin(t * 2 + i) * 5
        bw, bh2 = 120, 96
        r_ = pygame.Rect(x + 165 - bw // 2, int(y + 118 + bob), bw, bh2)
        pygame.draw.rect(surf, OUTLINE, r_.inflate(8, 8), border_radius=13); pygame.draw.rect(surf, mix(col, (10, 20, 40), 0.55), r_, border_radius=10)
        pygame.draw.rect(surf, col, r_, 3, border_radius=10)
        pygame.draw.rect(surf, (235, 70, 85), (r_.centerx - 10, r_.y, 20, r_.h))
        lid = pygame.Rect(r_.x - 10, r_.y - 20, bw + 20, 24)
        pygame.draw.rect(surf, OUTLINE, lid.inflate(8, 8), border_radius=11); pygame.draw.rect(surf, mix(col, WHITE, 0.25), lid, border_radius=8)
        pygame.draw.rect(surf, (235, 70, 85), (lid.centerx - 10, lid.y, 20, lid.h))
        if i == 2:
            for q in range(7):
                a = t * 1.6 + q * 0.9
                pygame.draw.circle(surf, (255, 230, 140), (int(r_.centerx + math.cos(a) * 92), int(r_.centery + math.sin(a) * 62)), 3)
        blit(surf, ofit("bungee", 25, bx[1], 300, col), (x + 165, y + 36))
        blit(surf, fit("russo", 16, bx[2], 300, (195, 210, 235)), (x + 165, y + 66))
        best = max(bx[4], key=lambda k: CH[k]["odds"])
        blit(surf, txt("russo", 15, L("Best: {0}", CH[best]["name"]), (170, 200, 235)), (x + 165, y + 240))
        pct = bx[4].get("frozen", 0) / sum(bx[4].values()) * 100
        blit(surf, txt("russo", 15, L("FROZEN SHADOW: {0}%", f"{pct:.1f}"), (150, 225, 255)), (x + 165, y + 262))
        on = AUTH["user"] is not None and not G["shop_busy"] and not G.get("wbox")
        if button(surf, "box" + bx[0], (x + 55, y + 284, 220, 52), L("{0} COINS", bx[3]), col, on, 21):
            open_box(bx[0])
    # which winter characters you already have
    blit(surf, otxt("bungee", 20, "WINTER CHARACTERS", (190, 225, 255)), (W // 2, 502))
    for i, k in enumerate(WINTER_KEYS):
        c = CH[k]; have = k in S["found"]; x = W // 2 - 270 + i * 135
        r_ = pygame.Rect(x - 52, 524, 104, 104)
        pygame.draw.rect(surf, mix((14, 24, 42), RAR[c["rar"]], 0.20 if have else 0.05), r_, border_radius=12)
        pygame.draw.rect(surf, RAR[c["rar"]] if have else (54, 66, 90), r_, 2, border_radius=12)
        im = thumb(k, 21, not have); surf.blit(im, im.get_rect(center=(r_.centerx, r_.y + 40)))
        blit(surf, fit("russo", 12, c["name"] if have else "???", 96, WHITE if have else (120, 130, 160)), (r_.centerx, r_.bottom - 14))
        if have: blit(surf, txt("russo", 12, f"x{S['found'][k]}", (180, 220, 255)), (r_.centerx, r_.y + 14))
    d1, d2 = WINTER_TO.split("-")[2], WINTER_TO.split("-")[1]
    if today() < WINTER_FROM:
        f1, f2 = WINTER_FROM.split("-")[2], WINTER_FROM.split("-")[1]
        blit(surf, txt("russo", 17, L("DEV PREVIEW  -  WINTER EVENT starts {0}", f1 + "/" + f2), (255, 190, 120)), (W // 2, 652))
    else:
        blit(surf, txt("russo", 17, L("WINTER EVENT  -  until {0}", d1 + "/" + d2), (150, 225, 255)), (W // 2, 652))
    if button(surf, "back", (40, H - 74, 180, 52), "BACK", (90, 90, 130)) or any(e.type == pygame.KEYDOWN and e.key == pygame.K_ESCAPE for e in events):
        G["state"] = "main"

def draw_shop(surf, t, dt, events):
    background(surf, t, (10, 40, 24), (2, 8, 5))
    title(surf, "LUCK SHOP", (60, 200, 100), 46)
    co = coins()
    if AUTH["user"]:
        blit(surf, txt("russo", 20, tr("Coins from Color Under Pressure: ") + ("..." if co is None else f"{co:,}"), (255, 220, 120)), (W // 2, 88))
    else:
        blit(surf, txt("russo", 20, "Sign in with your Color Under Pressure account to use your coins", (255, 180, 150)), (W // 2, 88))
    for i, it in enumerate(SHOP):
        x = 120 + i * 360; y = 120
        col = [(60, 200, 100), (250, 190, 40), (60, 140, 255)][i]
        panel(surf, (x, y, 320, 390), (16, 22, 20), col)
        for k in range(6 + i * 4):
            a = t * (1 + i) + k * 2 * math.pi / (6 + i * 4)
            pygame.draw.circle(surf, mix(col, WHITE, 0.4), (int(x + 160 + math.cos(a) * 70), int(y + 120 + math.sin(a) * 70)), 4)
        blit(surf, txt("bungee", 60, ["x10", "x100", "x2"][i], col), (x + 160, y + 120))
        blit(surf, fit("bungee", 28, it[1], 290), (x + 160, y + 226))
        blit(surf, txt("russo", 18, it[2], (200, 210, 200)), (x + 160, y + 262))
        if button(surf, "buy" + it[0], (x + 50, y + 300, 220, 56), L("{0} COINS", it[3]), col, AUTH["user"] is not None and not G["shop_busy"], 22):
            buy(it)
    # your items (from codes)
    inv = [(k, inv_have(k)) for k in inv_keys()][:4]
    if inv:
        blit(surf, txt("bungee", 18, "YOUR ITEMS", (200, 230, 210)), (120, 556), "midleft")
        for i, (k, n) in enumerate(inv):
            if button(surf, "use" + k, (290 + i * 250, 534, 236, 44), L("USE {0} x{1}", item_name(k), n), (230, 90, 200) if k.startswith("mega") else (60, 140, 255), True, 15):
                use_item(k)
    # codes
    r = pygame.Rect(W // 2 - 60, 600, 330, 46)
    blit(surf, txt("bungee", 20, "HAVE A CODE?", (255, 220, 120)), (r.x - 20, r.centery), "midright")
    act = G.get("code_on")
    pygame.draw.rect(surf, (10, 16, 14), r, border_radius=10); pygame.draw.rect(surf, (60, 200, 100) if act else (60, 80, 70), r, 2, border_radius=10)
    shown = G.get("code", "") + ("|" if act and (t % 1) < 0.5 else "")
    if shown: blit(surf, fit("bungee", 22, shown, r.w - 20), (r.x + 12, r.centery), "midleft")
    else: blit(surf, txt("russo", 16, "type it here", (90, 110, 100)), (r.x + 12, r.centery), "midleft")
    if CLICK: G["code_on"] = r.collidepoint(CLICK)
    go = button(surf, "redeem", (r.right + 12, 600, 150, 46), "..." if G.get("code_busy") else "REDEEM", (250, 170, 40), not G.get("code_busy"), 18)
    for e in events:
        if G.get("code_on") and e.type == pygame.TEXTINPUT and len(G.get("code", "")) < 20:
            G["code"] = G.get("code", "") + e.text.upper().strip()
        if G.get("code_on") and e.type == pygame.KEYDOWN:
            if e.key == pygame.K_BACKSPACE: G["code"] = G.get("code", "")[:-1]
            if e.key in (pygame.K_RETURN, pygame.K_KP_ENTER): go = True
    if go and G.get("code"): redeem(G["code"])
    blit(surf, txt("russo", 15, "Free rolls never cost anything. Coins only make you luckier.", (150, 170, 160)), (W // 2, 668))
    if button(surf, "back", (40, H - 74, 180, 52), "BACK", (90, 90, 130)) or any(e.type == pygame.KEYDOWN and e.key == pygame.K_ESCAPE for e in events):
        G["state"] = "main"

def _fmt_time(sec):
    sec = int(sec); h, m = sec // 3600, (sec % 3600) // 60
    return f"{h}h {m:02d}m" if h else f"{m}m {sec % 60:02d}s"
def draw_stats(surf, t, dt, events):
    background(surf, t, (8, 34, 44), (2, 6, 10))
    title(surf, "STATS", (60, 190, 210), 46)
    st = S.get("stats", {}) or {}
    total = sum(S["found"].values()) or 0
    uniq = sum(1 for k in CH if k in S["found"])
    # --- left: big numbers ---
    tiles = [("TOTAL ROLLS", f"{S['rolls']:,}", (60, 200, 100)),
             ("CHARACTERS", f"{uniq} / {len(CHARS)}", (170, 90, 240)),
             ("TIME PLAYED", _fmt_time(st.get("play_time", 0)), (60, 190, 210)),
             ("DAYS PLAYED", f"{len(st.get('days', []))}", (250, 190, 40)),
             ("LUCKIEST ROLL", L("1 in {0}", f"{st.get('luckiest', 0):,}") if st.get("luckiest") else "-", (235, 50, 70)),
             ("BEST LUCK", "x" + fmt_luck(st.get('best_luck', 1)), (255, 215, 90)),
             ("LUCKY ROLLS", f"{st.get('lucky_rolls', 0):,}", (60, 200, 100)),
             ("BONUS ROLLS", f"{st.get('bonus_rolls', 0):,}", (60, 140, 255)),
             ("SHINIES", f"{sum(S['shiny'].values()):,}", (255, 230, 140)),
             ("COINS SPENT / EARNED", f"{st.get('coins_spent', 0):,} / {st.get('coins_earned', 0):,}", (255, 205, 60)),
             ("SINCE LEGENDARY+", L("{0} rolls", f"{st.get('since_legendary', 0):,}"), (250, 190, 40)),
             ("LONGEST DRY RUN", L("{0} rolls", f"{st.get('longest_dry', 0):,}"), (180, 180, 200))]
    for i, (lab, val, col) in enumerate(tiles):
        x = 40 + (i % 3) * 200; y = 100 + (i // 3) * 118
        panel(surf, (x, y, 188, 106), (12, 22, 30), mix(col, (0, 0, 0), 0.3))
        blit(surf, txt("russo", 14, lab, mix(col, WHITE, 0.3)), (x + 94, y + 24))
        blit(surf, fit("bungee", 30, val, 170, WHITE), (x + 94, y + 66))
    # --- right: rarity bars ---
    px = 660; panel(surf, (px, 100, 580, 466), (12, 22, 30), (60, 120, 140))
    blit(surf, txt("bungee", 22, "ROLLS BY RARITY"), (px + 290, 128))
    by = {r: 0 for r in RAR_ORDER}
    for k, n in S["found"].items():
        if k in CH: by[CH[k]["rar"]] += n
    mx = max(1, max(by.values()))
    for i, r in enumerate(RAR_ORDER):
        y = 156 + i * 44; col = RAR[r]; n = by[r]
        blit(surf, txt("bungee", 17, r, col), (px + 24, y + 16), "midleft")
        bw = int(250 * (n / mx) * eo(min(1.0, t * 1.5)))
        pygame.draw.rect(surf, (30, 40, 50), (px + 170, y + 4, 250, 24), border_radius=8)
        if n: pygame.draw.rect(surf, col, (px + 170, y + 4, max(8, bw), 24), border_radius=8)
        pct = f"{n / total * 100:.1f}%" if total else "0%"
        blit(surf, txt("russo", 17, f"{n:,}  ({pct})", (210, 220, 230)), (px + 432, y + 16), "midleft")
    # rarest + most common found
    if S["found"]:
        _mine = {k: v for k, v in S["found"].items() if k in CH}
        if _mine:
            most = max(_mine, key=lambda k: _mine[k])
            blit(surf, fit("russo", 18, L("MOST FOUND: {0} x{1}", CH[most]['name'], f"{_mine[most]:,}"), 540, (200, 210, 220)), (px + 290, 520))
    if S.get("best") in CH:
        b = CH[S["best"]]
        blit(surf, fit("bungee", 20, L("RAREST: {0}  ({1})", b['name'], odds_text(b)), 540, RAR[b["rar"]]), (px + 290, 548))
    if button(surf, "back", (40, H - 74, 180, 52), "BACK", (90, 90, 130)) or any(e.type == pygame.KEYDOWN and e.key == pygame.K_ESCAPE for e in events):
        G["state"] = "main"

def slider(surf, key, x, y, w, val):
    pygame.draw.rect(surf, (40, 40, 60), (x, y - 5, w, 10), border_radius=5)
    pygame.draw.rect(surf, (60, 200, 100), (x, y - 5, int(w * val), 10), border_radius=5)
    pygame.draw.circle(surf, WHITE, (int(x + w * val), y), 13)
    if pygame.mouse.get_pressed()[0]:
        mx, my = MOUSE
        if x - 10 <= mx <= x + w + 10 and abs(my - y) < 20: return clamp((mx - x) / w)
    return val

def draw_settings(surf, t, dt, events):
    background(surf, t, (20, 20, 40), (5, 5, 12))
    title(surf, "SETTINGS", (150, 150, 200), 46)
    panel(surf, (W // 2 - 330, 92, 660, 536))
    lx = W // 2 - 290; vx = W // 2 - 60
    blit(surf, txt("bungee", 22, "MUSIC"), (lx, 130), "midleft")
    m = slider(surf, "music", vx, 130, 330, S["music"])
    if m != S["music"]: S["music"] = m; set_music_vol()
    blit(surf, txt("bungee", 22, "SOUNDS"), (lx, 190), "midleft")
    S["sfx"] = slider(surf, "sfx", vx, 190, 330, S["sfx"])
    blit(surf, txt("bungee", 22, "LANGUAGE"), (lx, 252), "midleft")
    for i, (code, name) in enumerate(LANGS):
        on = S.get("lang", "EN") == code
        if button(surf, "lang" + code, (vx + i * 115, 228, 105, 46), name, (60, 140, 255) if on else (70, 70, 100), size=16):
            S["lang"] = code; save_local(); play("click")
    blit(surf, txt("bungee", 22, "SCREEN"), (lx, 314), "midleft")
    if button(surf, "fs", (vx, 290, 220, 46), "FULLSCREEN: ON" if S.get("fullscreen") else "FULLSCREEN: OFF",
              (60, 200, 100) if S.get("fullscreen") else (70, 70, 100), size=16):
        set_fullscreen(not S.get("fullscreen"))
    blit(surf, txt("russo", 15, "F11", (150, 150, 180)), (vx + 236, 314), "midleft")
    blit(surf, txt("bungee", 22, "ACCOUNT"), (lx, 376), "midleft")
    if AUTH["user"]:
        blit(surf, fit("russo", 20, AUTH["user"]["name"], 170, (200, 200, 230)), (vx, 376), "midleft")
        if button(surf, "signout", (vx + 180, 352, 180, 46), "SIGN OUT", (200, 70, 70), size=18):
            sign_out(); flash("Signed out", (200, 200, 230))
    else:
        if button(surf, "signin2", (vx, 352, 220, 46), "SIGN IN", (60, 140, 255), size=18): G["state"] = "login"
    blit(surf, txt("bungee", 22, "HELP"), (lx, 438), "midleft")
    if button(surf, "tut", (vx, 414, 220, 46), "TUTORIAL", (250, 170, 40), size=18): G["state"] = "tutorial"; G["tut"] = 0
    blit(surf, fit("russo", 16, "Your coins and account are the same as in Color Under Pressure.", 620, (160, 160, 190)), (W // 2, 520))
    blit(surf, txt("russo", 16, f"Color Under Pressure: RNG  v{VERSION}   •   © 2026 Man Studio", (130, 130, 160)), (W // 2, 556))
    blit(surf, txt("russo", 14, "Fonts: Bungee, Russo One, Rubik (SIL Open Font License)", (110, 110, 140)), (W // 2, 590))
    if button(surf, "back", (40, H - 74, 180, 52), "BACK", (90, 90, 130)) or any(e.type == pygame.KEYDOWN and e.key == pygame.K_ESCAPE for e in events):
        save_local(); G["state"] = "main"

def draw_login(surf, t, dt, events, back_to="main"):
    background(surf, t)
    title(surf, "SIGN IN", (60, 140, 255), 70)
    blit(surf, txt("russo", 19, "Use your Color Under Pressure account (same name + password)", (190, 190, 220)), (W // 2, 118))
    panel(surf, (W // 2 - 300, 160, 600, 330))
    fields = [("NAME", "login_name", False), ("PASSWORD", "login_pw", True)]
    for i, (lab, key, hide) in enumerate(fields):
        y = 210 + i * 100; r = pygame.Rect(W // 2 - 250, y + 14, 500, 52)
        blit(surf, txt("russo", 18, lab, (170, 170, 200)), (r.x, y), "midleft")
        act = G["login_field"] == i
        pygame.draw.rect(surf, (12, 10, 24), r, border_radius=10); pygame.draw.rect(surf, (60, 140, 255) if act else (70, 70, 100), r, 2, border_radius=10)
        val = G[key]; shown = "•" * len(val) if hide else val
        cur = "|" if act and (t % 1) < 0.5 else ""
        blit(surf, fit("russo", 24, shown + cur, 480), (r.x + 14, r.centery), "midleft")
        if CLICK and r.collidepoint(CLICK): G["login_field"] = i
    go = button(surf, "go", (W // 2 - 110, 410, 220, 56), "..." if AUTH["loading"] else "SIGN IN", (60, 140, 255), not AUTH["loading"], 24)
    for e in events:
        if e.type == pygame.TEXTINPUT:
            key = fields[G["login_field"]][1]
            if len(G[key]) < 24: G[key] += e.text
        if e.type == pygame.KEYDOWN:
            key = fields[G["login_field"]][1]
            if e.key == pygame.K_BACKSPACE: G[key] = G[key][:-1]
            elif e.key == pygame.K_TAB: G["login_field"] = 1 - G["login_field"]
            elif e.key in (pygame.K_RETURN, pygame.K_KP_ENTER): go = True
            elif e.key == pygame.K_ESCAPE: G["state"] = back_to
    if go and not AUTH["loading"]:
        if len(G["login_name"].strip()) < 2 or not G["login_pw"]: flash("Write your name and password")
        else: sign_in(G["login_name"], G["login_pw"])
    if AUTH["error"]: blit(surf, fit("russo", 20, AUTH["error"], 700, (255, 140, 120)), (W // 2, 520))
    if AUTH["user"] and not AUTH["loading"]:
        G["login_pw"] = ""; G["state"] = back_to; flash(L("Welcome, {0}!", AUTH['user']['name']), (120, 255, 160))
    if button(surf, "back", (40, H - 74, 180, 52), "BACK", (90, 90, 130)): G["state"] = back_to

def draw_dev(surf, t, dt, events):
    background(surf, t, (40, 10, 10), (8, 2, 2))
    blit(surf, txt("bungee", 40, "DEV  -  FORCE NEXT ROLL"), (W // 2, 46))
    for i, c in enumerate(CHARS):
        x = 30 + (i % 7) * 175; y = 96 + (i // 7) * 82
        if button(surf, "dv" + c["key"], (x, y, 165, 66), c["name"], RAR[c["rar"]] if c["rar"] != "SECRET" else (120, 120, 140), size=16):
            if c["rar"] == "SECRET": G["state"] = "main"; secret_found(c["key"])
            else:
                G["force"] = c["key"]; G["state"] = "main"
                if pygame.key.get_mods() & pygame.KMOD_SHIFT: G["force_shiny"] = True
                flash("Next roll: " + c['name'] + ("  (SHINY)" if G.get("force_shiny") else ""), (255, 215, 90))
    if button(surf, "dvreset", (W - 360, H - 74, 320, 52), "RESET MY PROGRESS", (200, 60, 60), size=18):
        for k in ("found", "first", "badges"): S[k] = {} if k != "badges" else []
        S["rolls"] = 0; S["best"] = None; S["companion"] = None; S["shiny"] = {}; S["history"] = []; award("tester"); NET["dirty"] = True; save_local(); flash("Progress reset", (255, 215, 90))
    if button(surf, "back", (40, H - 74, 180, 52), "BACK", (90, 90, 130)) or any(e.type == pygame.KEYDOWN and e.key == pygame.K_ESCAPE for e in events):
        G["state"] = "main"

TUT = [
    ("WELCOME TO RNG!", ["One button. One roll. Who will you get?", "Pick your language:"]),
    ("PRESS ROLL", ["Every roll gives you a random character.", "Free roll every 2 seconds. SPACE also rolls.", "Turn on AUTO and just watch."]),
    ("RARITY & LUCK", ["Every character has odds, like 1 in 400.", "More LUCK = rare characters show up more.", "Every 10th roll = BONUS ROLL x2.", "Coins from Color Under Pressure buy more luck."]),
    ("COLLECT THEM ALL", ["INDEX: every character you found.", "Pick a COMPANION to stand next to you.", "BADGES, STATS and the LEADERBOARD.", "2 SECRET characters are hidden. Look carefully..."]),
]
SAMPLE = ["red", "crimson", "sun", "white", "watcher", "theshadow", "man"]
def draw_tutorial(surf, t, dt, events):
    background(surf, t)
    i = G.get("tut", 0); title, lines = TUT[i]
    panel(surf, (W // 2 - 420, 80, 840, 520))
    for k in range(len(TUT)):
        pygame.draw.circle(surf, (255, 215, 90) if k == i else (70, 70, 100), (W // 2 - 45 + k * 30, 110), 8)
    blit(surf, fit("bungee", 46, title, 780, (255, 215, 90)), (W // 2, 170))
    for j, ln in enumerate(lines): blit(surf, fit("russo", 24, ln, 760, (220, 220, 240)), (W // 2, 236 + j * 40))
    if i == 0:
        for k, (code, name) in enumerate(LANGS):
            on = S.get("lang", "EN") == code
            if button(surf, "tl" + code, (W // 2 - 260 + k * 180, 340, 160, 60), name, (60, 140, 255) if on else (70, 70, 100), size=20):
                S["lang"] = code; save_local(); play("click")
        draw_logo(surf, t, W // 2, 488, 0.8)
    elif i == 1:
        c = CH[SAMPLE[int(t / 1.2) % len(SAMPLE)]]
        draw_card(surf, c, W // 2, 470, 0.55, t)
    elif i == 2:
        for k, key in enumerate(["red", "sun", "white", "theshadow", "man"]):
            c = CH[key]; x = W // 2 - 300 + k * 150
            c["fn"](surf, x, 450, 34, t)
            blit(surf, fit("bungee", 15, c["rar"], 140, RAR[c["rar"]]), (x, 512))
            blit(surf, fit("russo", 15, odds_text(c), 140, (200, 200, 220)), (x, 536))
    else:
        for k, key in enumerate(["chroma", "black", "static", "luna"]):
            CH[key]["fn"](surf, W // 2 - 225 + k * 150, 470, 36, t)
        im = thumb("dobe", 30, True); surf.blit(im, im.get_rect(center=(W // 2 + 380, 470)))
        blit(surf, txt("bungee", 40, "?", (120, 120, 150)), (W // 2 + 380, 470))
    last = i == len(TUT) - 1
    if i > 0 and button(surf, "tprev", (W // 2 - 300, 620, 180, 56), "BACK", (90, 90, 130), size=22): G["tut"] = i - 1
    if button(surf, "tnext", (W // 2 + 120, 620, 220, 56), "LET'S ROLL!" if last else "NEXT", (60, 200, 100), size=22) or \
            any(e.type == pygame.KEYDOWN and e.key in (pygame.K_RETURN, pygame.K_RIGHT) for e in events):
        if last: S["tut_done"] = True; save_local(); G["state"] = "main"
        else: G["tut"] = i + 1
    if not last and button(surf, "tskip", (W - 200, 20, 170, 44), "SKIP", (70, 70, 100), size=18):
        S["tut_done"] = True; save_local(); G["state"] = "main"

def draw_leader(surf, t, dt, events):
    background(surf, t, (50, 12, 30), (8, 2, 6))
    title(surf, "LEADERBOARD", (235, 80, 120), 46)
    tabs = [("best", "RAREST ROLL"), ("uniq", "MOST CHARACTERS"), ("rolls", "MOST ROLLS")]
    for i, (k, nm) in enumerate(tabs):
        if button(surf, "lbt" + k, (W // 2 - 390 + i * 265, 86, 250, 46), nm, (235, 80, 120) if LB["tab"] == k else (70, 60, 90), size=17):
            LB["tab"] = k
    panel(surf, (W // 2 - 400, 148, 800, 470), (20, 10, 20), (120, 50, 80))
    rows = LB["rows"].get(LB["tab"])
    me = AUTH["user"]["name"] if AUTH["user"] else None
    if LB["busy"] and not rows: blit(surf, txt("russo", 22, "Loading...", (200, 200, 220)), (W // 2, 380))
    elif rows is None: blit(surf, txt("russo", 22, "No connection", (255, 160, 140)), (W // 2, 380))
    elif not rows: blit(surf, txt("russo", 22, "Nobody here yet. Be the first!", (200, 200, 220)), (W // 2, 380))
    else:
        for i, r in enumerate(rows[:10]):
            y = 172 + i * 44; mine = r.get("name") == me
            if mine: pygame.draw.rect(surf, (90, 40, 70), (W // 2 - 390, y - 4, 780, 40), border_radius=10)
            medal = [(255, 215, 90), (200, 205, 215), (215, 140, 70)][i] if i < 3 else (90, 80, 110)
            pygame.draw.circle(surf, medal, (W // 2 - 360, y + 16), 16)
            blit(surf, txt("bungee", 16, str(i + 1), (30, 20, 30) if i < 3 else WHITE), (W // 2 - 360, y + 16))
            blit(surf, fit("russo", 22, r.get("name", "?"), 280), (W // 2 - 330, y + 16), "midleft")
            if LB["tab"] == "best":
                val = L("1 in {0}", f"{int(r.get('best', 0)):,}"); sub = r.get("best_char", "")
            elif LB["tab"] == "uniq": val = f"{int(r.get('uniq', 0))} / {len(CHARS)}"; sub = ""
            else: val = f"{int(r.get('rolls', 0)):,}"; sub = ""
            if sub: blit(surf, fit("russo", 16, sub, 200, (200, 170, 190)), (W // 2 + 40, y + 16), "midleft")
            blit(surf, txt("bungee", 22, val, (255, 215, 90)), (W // 2 + 380, y + 16), "midright")
    if is_dev(): blit(surf, txt("russo", 15, "DEV accounts are not on the leaderboard (they can force rolls).", (170, 150, 160)), (W // 2, 640))
    elif not AUTH["user"]: blit(surf, txt("russo", 15, "Sign in to get on the leaderboard!", (170, 150, 160)), (W // 2, 640))
    if button(surf, "lbref", (W - 220, H - 74, 180, 52), "REFRESH", (235, 80, 120), not LB["busy"], 20): bg(pull_leader)
    if button(surf, "back", (40, H - 74, 180, 52), "BACK", (90, 90, 130)) or any(e.type == pygame.KEYDOWN and e.key == pygame.K_ESCAPE for e in events):
        G["state"] = "main"

def draw_locked(surf, t, dt, events):
    background(surf, t)
    draw_logo(surf, t, W // 2, 250, 1.9)
    blit(surf, jelly("COMING OCTOBER 13, 2026", 40, (250, 200, 50)), (W // 2, 460))
    d = (datetime.date.fromisoformat(RNG_OPEN) - datetime.date.today()).days
    if d > 0: blit(surf, txt("russo", 24, L("{0} days to go", d), (200, 200, 230)), (W // 2, 500))
    if not AUTH["user"]:
        if button(surf, "devin", (W - 220, H - 70, 190, 46), "SIGN IN", (70, 70, 110), size=18): G["state"] = "login_locked"

def draw_toasts(surf):
    now = time.time(); y = 76
    for n, item in enumerate(list(TOASTS)):
        if n >= 2: item[1] = now; continue          # max 2 at a time, the rest wait
        bid, t0 = item; age = now - t0
        if age > 4.5: TOASTS.remove(item); continue
        b = BADGE[bid]; k = eo(age / 0.35) if age < 4 else 1 - eo((age - 4) / 0.5)
        x = W - 20 - int(360 * k)
        panel(surf, (x, y, 340, 74), (24, 20, 14), b[3])
        pygame.draw.circle(surf, b[3], (x + 38, y + 37), 22)
        blit(surf, txt("russo", 14, "BADGE UNLOCKED", (220, 210, 170)), (x + 72, y + 22), "midleft")
        blit(surf, fit("bungee", 22, b[1], 255), (x + 72, y + 48), "midleft")
        y += 84
    if G["msg"] and now - G["msg_t"] < 3.0:
        m, col = G["msg"]; a = 255 * clamp((3.0 - (now - G["msg_t"])) / 0.4)
        im = fit("russo", 22, m, W - 200, col); r = im.get_rect(center=(W // 2, 118)).inflate(30, 14)
        p = pygame.Surface(r.size, pygame.SRCALPHA); pygame.draw.rect(p, (0, 0, 0, int(a * 0.85)), (0, 0, r.w, r.h), border_radius=10); surf.blit(p, r)
        blit(surf, im, (W // 2, 118), alpha=a)
    tk = NET["ticker"]
    if tk and now - NET["ticker_t"] < 6:
        col = RAR.get(tk.get("rar"), WHITE)
        s = f"★ {tk.get('name','?')} just rolled {tk.get('char','?')}! ★"
        im = fit("bungee", 22, s, W - 300, col); r = im.get_rect(center=(W // 2, 232)).inflate(30, 14)
        p = pygame.Surface(r.size, pygame.SRCALPHA); pygame.draw.rect(p, (0, 0, 0, 190), (0, 0, r.w, r.h), border_radius=10); surf.blit(p, r)
        surf.blit(im, im.get_rect(center=(W // 2, 232)))

# ---------------------------------------------------------------------------
#  window icon
# ---------------------------------------------------------------------------
try:
    ic = pygame.Surface((64, 64), pygame.SRCALPHA); pygame.draw.rect(ic, (30, 18, 60), (0, 0, 64, 64), border_radius=14)
    for i, (ch, col) in enumerate(zip("RNG", [(235, 64, 64), (60, 200, 100), (60, 120, 255)])): blit(ic, txt("bungee", 26, ch, col), (12 + i * 20, 34))
    pygame.display.set_icon(ic)
except Exception: pass

# ---------------------------------------------------------------------------
#  main loop
# ---------------------------------------------------------------------------
def main():
    global MOUSE, CLICK
    pygame.key.start_text_input()
    if S.get("fullscreen"): set_fullscreen(True)
    running = True; t = 0.0
    while running:
        dt = min(0.05, clock.tick(FPS) / 1000.0); t += dt
        if game_open(): S.setdefault("stats", {})["play_time"] = S["stats"].get("play_time", 0) + dt
        sw, sh = screen.get_size(); sc = min(sw / W, sh / H); ox, oy = (sw - W * sc) / 2, (sh - H * sc) / 2
        def to_canvas(p): return (int((p[0] - ox) / sc), int((p[1] - oy) / sc))
        MOUSE = to_canvas(pygame.mouse.get_pos()); CLICK = None
        events = pygame.event.get()
        for e in events:
            if e.type == pygame.QUIT: running = False
            if e.type == pygame.MOUSEBUTTONDOWN and e.button == 1: CLICK = to_canvas(e.pos)
            if e.type in (pygame.MOUSEBUTTONDOWN, pygame.MOUSEMOTION, pygame.KEYDOWN, pygame.TEXTINPUT, pygame.MOUSEWHEEL): G["last_input"] = time.time()
        if "last_input" not in G: G["last_input"] = time.time()
        if S.get("auto") and time.time() - G["last_input"] > AFK_LIMIT and not G.get("afk"):       # AFK: disconnected
            S["auto"] = False; G["afk"] = True; save_local(); NET["dirty"] = True
        if G.get("afk"):
            if CLICK: G["afk"] = False; G["last_input"] = time.time(); CLICK = None; events = []
            else: CLICK = None; events = [e for e in events if e.type == pygame.QUIT]
            if any(ev.type == pygame.KEYDOWN and ev.key == pygame.K_F11 for ev in events):
                set_fullscreen(not S.get("fullscreen"))
        G["cool"] = max(0.0, G["cool"] - dt)
        # safety net: if a roll / easter-egg screen ever gets stuck, ROLL would stay dead forever
        if G["roll"] and G["roll"].get("t", 0) > 15: G["roll"] = None; G["cool"] = 0.0
        if G["egg"] and G["egg"].get("t", 0) > 20: G["egg"] = None
        if G["cool"] > FREE_COOLDOWN + 1: G["cool"] = 0.0        # a clock jump must not freeze the button
        st = G["state"]
        if not game_open() and st not in ("login_locked",): st = G["state"] = "locked"
        if game_open() and st in ("locked", "login_locked"): st = G["state"] = "main"
        if game_open() and st == "main" and not S.get("tut_done"): st = G["state"] = "tutorial"; G["tut"] = 0
        busy = G["roll"] is not None or G["egg"] is not None
        if busy:
            ev2 = [e for e in events if e.type not in (pygame.TEXTINPUT, pygame.KEYDOWN)]
            c0 = CLICK; CLICK = None
            if st == "main": draw_main(canvas, t, dt, ev2)
            CLICK = c0
            if G["egg"]: draw_egg_overlay(canvas, t, dt)
            else: draw_roll_overlay(canvas, t, dt)
        else:
            if st == "main":
                if G.get("demo_box") and not AUTH["user"]:
                    c0 = CLICK; CLICK = None; draw_main(canvas, t, dt, []); CLICK = c0
                else: draw_main(canvas, t, dt, events)
                if S.get("auto") and G["cool"] <= 0 and not G["roll"] and not G["egg"]: start_roll()
            elif st == "index": draw_index(canvas, t, dt, events)
            elif st == "collection": draw_collection(canvas, t, dt, events)
            elif st == "badges": draw_badges(canvas, t, dt, events)
            elif st == "shop": draw_shop(canvas, t, dt, events)
            elif st == "wshop":
                if winter_now(): draw_winter_shop(canvas, t, dt, events)
                else: G["state"] = "main"            # the event is off -> no way in
            elif st == "settings": draw_settings(canvas, t, dt, events)
            elif st == "stats": draw_stats(canvas, t, dt, events)
            elif st == "leader": draw_leader(canvas, t, dt, events)
            elif st == "tutorial": draw_tutorial(canvas, t, dt, events)
            elif st == "login": draw_login(canvas, t, dt, events)
            elif st == "login_locked": draw_login(canvas, t, dt, events, "locked")
            elif st == "dev": draw_dev(canvas, t, dt, events)
            elif st == "locked": draw_locked(canvas, t, dt, events)
        if G.get("demo_box") and G["state"] == "main" and not busy:
            if AUTH["user"]: G["demo_box"] = False
            else:
                c0 = CLICK; draw_demo_box(canvas, t, dt, events)
        if G.get("wbox"): draw_wbox(canvas, t, dt)
        draw_parts(canvas, dt)
        draw_toasts(canvas)
        if G.get("afk"): draw_afk(canvas, t)
        net_tick()
        screen.fill((0, 0, 0))
        sx = sy = 0
        if FX["shake"] > 0.5:
            sx, sy = random.uniform(-1, 1) * FX["shake"], random.uniform(-1, 1) * FX["shake"]; FX["shake"] *= 0.88
        else: FX["shake"] = 0
        if sc == 1.0: screen.blit(canvas, (int(sx), int(sy)))
        else: screen.blit(pygame.transform.smoothscale(canvas, (int(W * sc), int(H * sc))), (int(ox + sx), int(oy + sy)))
        pygame.display.flip()
    if G["roll"]: finish_roll()            # closing in the middle of a roll still gives the character
    save_local()
    if AUTH["user"]: cloud_push()
    pygame.quit()

if __name__ == "__main__":
    main()
