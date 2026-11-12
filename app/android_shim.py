"""Color Under Pressure: RNG on Android: the game runs as is; this layer makes a phone feel right.

- the screen: full screen, landscape, scaled (the game keeps drawing its 1280x720 picture;
  SDL scales it to the phone and adds thin black bars on wide phones)
- touch: taps are already mouse clicks (SDL does that, in the game's own pixels)
- the phone's Back button = ESC (every RNG screen goes back on ESC)
- the phone keyboard: opens by itself on the sign-in screen and when the code box is tapped;
  a small keyboard button next to a text box opens / closes it. The game reads TEXTINPUT,
  so what the keyboard types is passed through unchanged.
- links open in the phone's browser, HTTPS works (certifi), saves live outside the app folder

On a computer, CUP_FAKE_ANDROID=1 turns the same layer on (the mouse plays the finger) for testing.
"""
import os, time, math, glob

REAL = 'ANDROID_ARGUMENT' in os.environ or 'ANDROID_PRIVATE' in os.environ
ANDROID = REAL or bool(os.environ.get('CUP_FAKE_ANDROID'))


class _State:
    kb_open = False
    net_err = ''
    net_err_t = 0.0
    field_t = 0.0           # last time the game drew a text box
    auto_t = 0.0            # last time it drew a text box that should open the keyboard by itself
    field_rect = None
    auto_gone_since = 1.0
    field_gone_since = 1.0
    size = (1280, 720)      # the game's own size (the last real size it asked for)
    on_button = False       # the finger that is down started on the keyboard button


S = _State()


def install():
    global _start_text, _stop_text
    if not ANDROID:
        return
    os.environ.setdefault('SDL_ANDROID_TRAP_BACK_BUTTON', '1')
    import pygame

    # HTTPS: Python on Android has no system certificate store, so every HTTPS request uses certifi's
    try:
        import certifi, ssl
        ca = certifi.where()
        os.environ['SSL_CERT_FILE'] = ca
        ssl._create_default_https_context = lambda *a, **k: ssl.create_default_context(cafile=ca)
    except Exception as ex:
        S.net_err = 'certifi: %r' % (ex,)
        S.net_err_t = time.time()

    # network errors: keep the real reason and show it for a few seconds (for fixing problems)
    import urllib.request
    _urlopen = urllib.request.urlopen

    def urlopen(*a, **k):
        try:
            return _urlopen(*a, **k)
        except Exception as ex:
            import urllib.error
            if not isinstance(ex, urllib.error.HTTPError):    # HTTP errors are normal answers (wrong password...)
                S.net_err = '%s: %s' % (type(ex).__name__, str(ex)[:160])
                S.net_err_t = time.time()
                print('network error:', S.net_err)
            raise
    urllib.request.urlopen = urlopen

    # ---- the screen: always the game's size, scaled to the whole phone ----
    _set_mode = pygame.display.set_mode

    def set_mode(size=(0, 0), flags=0, *a, **k):
        try:
            w, h = size
        except Exception:
            w = h = 0
        if w > 0 and h > 0:
            S.size = (w, h)
        flags = (flags & ~pygame.RESIZABLE) | pygame.SCALED
        if REAL:
            flags |= pygame.FULLSCREEN
        else:
            flags &= ~pygame.FULLSCREEN
        surf = _set_mode(S.size, flags, *a, **k)
        if REAL:
            try:
                _stop_text()                   # the keyboard opens only when needed
            except Exception:
                pass
        return surf
    pygame.display.set_mode = set_mode
    pygame.display.toggle_fullscreen = lambda *a: 0

    # the game turns text input on at start (on a computer that is harmless; on a phone it would
    # open the keyboard over the game). Only this layer opens and closes it.
    _start_text, _stop_text = pygame.key.start_text_input, pygame.key.stop_text_input
    pygame.key.start_text_input = lambda *a, **k: None
    pygame.key.stop_text_input = lambda *a, **k: None

    # ---- events: Back, keyboard button ----
    _get = pygame.event.get

    def get(*a, **k):
        evs = _get(*a, **k)
        if a or k:
            return evs
        out = []
        for e in evs:
            r = _handle(e)
            out.extend([e] if r is None else r)
        return out
    pygame.event.get = get

    # ---- the keyboard button is drawn on top of every frame ----
    _flip, _update = pygame.display.flip, pygame.display.update

    def flip(*a, **k):
        _draw_overlay()
        return _flip(*a, **k)

    def update(*a, **k):
        _draw_overlay()
        return _update(*a, **k)
    pygame.display.flip = flip
    pygame.display.update = update

    # ---- Hebrew: the phone's Noto Sans Hebrew (the game's own fonts come first) ----
    _match = pygame.font.match_font
    he = sorted(glob.glob('/system/fonts/NotoSansHebrew*.ttf'))
    he_bold = [f for f in he if 'Bold' in f]
    he_reg = [f for f in he if 'Regular' in f] or he

    def match_font(name, bold=False, italic=False):
        try:
            p = _match(name, bold, italic)
        except Exception:
            p = None
        if p or not he:
            return p
        n = (name if isinstance(name, str) else ','.join(name)).lower()
        if any(x in n for x in ('arial', 'segoe', 'tahoma', 'calibri', 'david', 'gisha', 'hebrew', 'dejavu',
                                'freesans', 'liberation', 'miriam', 'microsoft')):
            return (he_bold or he_reg)[0] if bold else he_reg[0]
        return None
    pygame.font.match_font = match_font

    # ---- music files (if a future version adds them): if an mp3 can't play here, its .ogg twin can ----
    try:
        _load = pygame.mixer.music.load

        def music_load(f, *a, **k):
            try:
                return _load(f, *a, **k)
            except Exception:
                if isinstance(f, str) and f.lower().endswith('.mp3') and os.path.exists(f[:-4] + '.ogg'):
                    return _load(f[:-4] + '.ogg', *a, **k)
                raise
        pygame.mixer.music.load = music_load
    except Exception:
        pass

    # ---- links open in the phone's browser ----
    if REAL:
        import webbrowser

        def open_url(url, *a, **k):
            try:
                from jnius import autoclass
                Intent = autoclass('android.content.Intent')
                Uri = autoclass('android.net.Uri')
                act = autoclass('org.kivy.android.PythonActivity').mActivity
                act.startActivity(Intent(Intent.ACTION_VIEW, Uri.parse(url)))
                return True
            except Exception as ex:
                print('open url failed', ex)
                return False
        webbrowser.open = webbrowser.open_new = webbrowser.open_new_tab = open_url


def _start_text():
    pass


def _stop_text():
    pass


def text_field(rect, active=True, auto=True):
    """Called by the (patched) game every time it draws a text box.
    auto=True: the keyboard opens by itself while this box is on screen."""
    if not ANDROID:
        return
    try:
        r = (rect[0], rect[1], rect[2], rect[3])
    except Exception:
        return
    now = time.time()
    if active or not S.field_rect or now - S.field_t > 0.1:
        S.field_rect = r                       # the keyboard button goes next to the active box
    S.field_t = now
    if auto:
        S.auto_t = now


def _field_shown():
    return time.time() - S.field_t < 0.4


def _kb_auto_tick():
    """Open the phone keyboard when a text box that wants it shows up, close it when no box is left."""
    now = time.time()
    if now - S.auto_t < 0.4:
        if S.auto_gone_since and not S.kb_open:
            _set_keyboard(True)                   # a text box just appeared
        S.auto_gone_since = 0.0
    elif not S.auto_gone_since:
        S.auto_gone_since = now
    if _field_shown():
        S.field_gone_since = 0.0
    else:
        if not S.field_gone_since:
            S.field_gone_since = now
        elif S.kb_open and now - S.field_gone_since > 0.6:
            _set_keyboard(False)


def _kb_home():
    """The keyboard button sits right of the text box (None when there is no text box)."""
    if not _field_shown() or not S.field_rect:
        return None
    W, H = S.size
    x, y, w, h = S.field_rect
    if x + w + 40 <= W - 30:
        return x + w + 40, y + h // 2           # right of the box
    return max(30, x - 40), y + h // 2          # no room on the right: left of it


def _key_events(key, down):
    import pygame
    if down:
        return [pygame.event.Event(pygame.KEYDOWN, key=key, mod=0, unicode='', scancode=0)]
    return [pygame.event.Event(pygame.KEYUP, key=key, mod=0, unicode='', scancode=0)]


def _handle(e):
    """None = give the event to the game; a list = give it these events instead."""
    import pygame
    t = e.type

    # Back button = ESC
    back = getattr(pygame, 'K_AC_BACK', None)
    if t in (pygame.KEYDOWN, pygame.KEYUP) and back is not None and e.key == back:
        return _key_events(pygame.K_ESCAPE, t == pygame.KEYDOWN)

    # a tap on the keyboard button opens / closes the keyboard and is hidden from the game
    if t == pygame.MOUSEBUTTONDOWN and getattr(e, 'button', 1) == 1:
        kb = _kb_home()
        if kb and math.hypot(e.pos[0] - kb[0], e.pos[1] - kb[1]) <= 34:
            S.on_button = True
            _set_keyboard(not S.kb_open)
            return []
        S.on_button = False
    if S.on_button and t in (pygame.MOUSEBUTTONUP, pygame.MOUSEMOTION):
        if t == pygame.MOUSEBUTTONUP:
            S.on_button = False
        return []
    return None


def _set_keyboard(on):
    import pygame
    S.kb_open = on
    try:
        if on:
            W, H = S.size
            pygame.key.set_text_input_rect(pygame.Rect(0, H - 80, W, 60))
            _start_text()
        else:
            _stop_text()
    except Exception as ex:
        print('keyboard', ex)


_font = {}


def _draw_overlay():
    import pygame
    s = pygame.display.get_surface()
    if s is None:
        return
    try:
        _kb_auto_tick()
        kb = _kb_home()
        net = S.net_err and time.time() - S.net_err_t < 12
        if not kb and not net:
            return
        layer = pygame.Surface(s.get_size(), pygame.SRCALPHA)
        if kb:                                   # keyboard button, next to the text box
            kx, ky = kb
            pygame.draw.circle(layer, (255, 255, 255, 210 if S.kb_open else 150), (kx, ky), 26)
            for i in range(3):
                for j in range(3):
                    pygame.draw.rect(layer, (20, 20, 35, 230), (kx - 13 + j * 9, ky - 10 + i * 7, 7, 5), border_radius=1)
        if net:                                  # why the network failed (for fixing it)
            f = _font.get('n') or _font.setdefault('n', pygame.font.SysFont(None, 22))
            t = f.render('net: ' + S.net_err, True, (255, 140, 120))
            W, H = s.get_size()
            bg = pygame.Surface((min(W, t.get_width() + 16), t.get_height() + 8), pygame.SRCALPHA); bg.fill((0, 0, 0, 170))
            layer.blit(bg, (0, H - bg.get_height())); layer.blit(t, (8, H - bg.get_height() + 4))
        s.blit(layer, (0, 0))
    except Exception as ex:
        print('overlay', ex)
