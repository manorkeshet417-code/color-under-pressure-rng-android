"""Small, exact changes to color_rng.py for the Android build (the original on the computer stays as is).

1. Saves go to the app's private folder (kept across updates), not next to the code
   (the code folder is replaced on every update).
2. The text boxes (sign in, codes) tell the phone layer they are on screen, so the phone keyboard
   opens by itself / a keyboard button appears. In the dark (the light-switch secret) a keyboard
   button appears too, so BONES can be typed on a phone.
3. Safety: a shrinking card is never scaled to less than 2 pixels (pygame's smoothscale and
   1-pixel surfaces crashed Color Under Pressure on Windows).
Every change must find its spot exactly once; otherwise the build stops, so a change in the game
can't silently break the phone version.
"""
import sys

path = sys.argv[1] if len(sys.argv) > 1 else 'app/color_rng.py'
src = open(path, encoding='utf-8').read()

SHIM = "__import__('android_shim')"
CHANGES = [
    ('def _data_dir():\n',
     'def _data_dir():\n    if os.environ.get("ANDROID_PRIVATE"): return os.environ["ANDROID_PRIVATE"]   # Android: survives updates\n'),
    # sign in: NAME / PASSWORD boxes (the keyboard opens by itself)
    ('        y = 210 + i * 100; r = pygame.Rect(W // 2 - 250, y + 14, 500, 52)\n',
     f'        y = 210 + i * 100; r = pygame.Rect(W // 2 - 250, y + 14, 500, 52); {SHIM}.text_field(r, G["login_field"] == i)\n'),
    # LUCK SHOP code box (the keyboard opens when the box is tapped)
    ('    act = G.get("code_on")\n',
     f'    act = G.get("code_on"); {SHIM}.text_field(r, bool(act), bool(act))\n'),
    # lights off: a keyboard button left of the switch, for typing BONES
    ('    if G["dark"]:\n        for e in events:\n',
     f'    if G["dark"]:\n        {SHIM}.text_field((lx - 200, ly - 20, 40, 40), True, False)\n        for e in events:\n'),
    ('if scale != 1.0: cs = pygame.transform.smoothscale(cs, (max(1, int(cw * scale)), max(1, int(ch * scale))))',
     'if scale != 1.0: cs = pygame.transform.smoothscale(cs, (max(2, int(cw * scale)), max(2, int(ch * scale))))'),
]
for old, new in CHANGES:
    n = src.count(old)
    if n != 1:
        sys.exit(f'patch_game: expected exactly 1 of {old!r}, found {n}')
    src = src.replace(old, new)

open(path, 'w', encoding='utf-8').write(src)
print('patched', path)
