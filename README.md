# Color Under Pressure: RNG for Android

The Windows game (`color_rng.py`, Man Studio) built into an Android APK with Buildozer,
set up exactly like `color-under-pressure-android`.

- `app/` - the game as it is on the computer, plus `main.py` (starts it, shows startup errors in a
  dialog) and `android_shim.py` (full screen scaled 1280x720, Back = ESC, phone keyboard for the
  sign-in and code boxes, links, HTTPS).
- `tools/patch_game.py` - small exact changes made only in the build (saves in the app's private
  folder so updates keep them, text boxes tell the phone to open the keyboard, cards never scaled
  under 2 px).
- `sync.ps1` - copies the latest `color_rng.py` (and any mp3/ogg/wav or `music_cache`) from the
  ManStudio folder. Never copies saves.
- Music and sounds are made in code with numpy, so `numpy` is in the build requirements.
- `recipes/pygame` - pygame 2.1.3 with the SIMD blitters (same fix as the main game).
- GitHub Actions builds, signs (secret `CUP_SIGNING`, the same key as the main game, backed up in
  OneDrive\cup-signing) and publishes a release with `ColorUnderPressureRNG.apk`.

Update: run `sync.ps1`, commit, push.
