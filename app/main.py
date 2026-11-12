# Color Under Pressure: RNG for Android: turn on the phone layer, then run the game exactly as on a computer.
# If anything fails while starting, the error is shown in an Android dialog (and copied),
# so it can be sent instead of the app just closing.
import os, sys, runpy, traceback, time

here = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, here)
os.chdir(here)


def show_error(text):
    try:
        with open(os.path.join(os.environ.get('ANDROID_PRIVATE', here), 'boot_error.txt'), 'w', encoding='utf-8') as f:
            f.write(text)
    except Exception:
        pass
    print(text)
    try:
        from jnius import autoclass
        from android.runnable import run_on_ui_thread
        act = autoclass('org.kivy.android.PythonActivity').mActivity
        Context = autoclass('android.content.Context')
        ClipData = autoclass('android.content.ClipData')
        Builder = autoclass('android.app.AlertDialog$Builder')
        String = autoclass('java.lang.String')

        @run_on_ui_thread
        def _show():
            try:
                cm = act.getSystemService(Context.CLIPBOARD_SERVICE)
                cm.setPrimaryClip(ClipData.newPlainText(String('error'), String(text)))
            except Exception:
                pass
            b = Builder(act)
            b.setTitle(String('Color Under Pressure: RNG - error (copied)'))
            b.setMessage(String(text[-3500:]))
            b.setCancelable(False)
            b.create().show()
        _show()
        while True:                      # keep the app open so the message can be read
            time.sleep(1)
    except Exception:
        traceback.print_exc()


try:
    import android_shim
    android_shim.install()
    # the Android build ships compiled files: color_rng.pyc instead of color_rng.py
    game = os.path.join(here, 'color_rng.py')
    if not os.path.exists(game):
        game += 'c'
    runpy.run_path(game, run_name='__main__')
except SystemExit:
    raise
except BaseException:
    show_error('Startup error:\n' + traceback.format_exc())
