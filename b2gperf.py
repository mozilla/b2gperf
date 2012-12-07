#!/usr/bin/env python
#
# To run this:
# 1) Install a B2G build with Marionette enabled
# 2) adb forward tcp:2828 tcp:2828
# 3) b2gperf.py /path/to/gaia/atoms <app name>

import sys, os
from marionette import Marionette

def measure_app_perf(marionette, gaia_atoms_path, app_name):
    # Enable FPS counter first so data is stable by the time we measure it.
    marionette.set_context(marionette.CONTEXT_CHROME)
    script_dir = os.path.dirname(__file__)
    marionette.import_script(os.path.join(script_dir, "fps.js"))
    marionette.execute_script("""
Components.utils.import("resource://gre/modules/Services.jsm");
Services.prefs.setBoolPref("layers.acceleration.draw-fps", true);
""")
    # Give apps a long timeout to launch
    marionette.set_script_timeout(60000)
    marionette.set_context(marionette.CONTEXT_CONTENT)
    marionette.import_script(os.path.join(gaia_atoms_path, "gaia_apps.js"))
    marionette.execute_async_script("GaiaApps.killAll()")
    # Unlock
    marionette.import_script(os.path.join(gaia_atoms_path, "gaia_lock_screen.js"))
    marionette.execute_async_script("GaiaLockScreen.unlock()")
    # Return to home screen
    marionette.execute_script("window.wrappedJSObject.dispatchEvent(new Event('home'));")
    marionette.import_script(os.path.join(script_dir, "launchapp.js"))
    res = marionette.execute_async_script("launch_app('%s')" % app_name)
    if not res:
        print "Error launching app"
        return
    print "time_to_paint: %f" % res.get('time_to_paint')
    # try to get FPS
    marionette.set_context(marionette.CONTEXT_CHROME)
    period = 5000 # ms
    sample_hz = 10
    marionette.set_script_timeout(period + 1000)
    #TODO: do something useful with all this data
    fps = marionette.execute_async_script("measure_fps(%d,%d)" % (period, sample_hz))
    if fps:
        print "FPS: %f/%f" % (fps.get('composition_fps'),
                              fps.get('transaction_fps'))
    marionette.execute_script("""Services.prefs.setBoolPref("layers.acceleration.draw-fps", false);""")
    marionette.set_context(marionette.CONTEXT_CONTENT)
    marionette.execute_async_script("GaiaApps.kill('%s')" % res.get('origin'))

def main(args):
    if len(args) < 1:
        print >>sys.stderr, "Usage: b2gperf.py <path to gaia atoms> [app name]"
        sys.exit(1)
    gaia_atoms_path = args[0]
    app_name = args[1] if len(args) == 2 else "Clock"
    marionette = Marionette(host='localhost', port=2828)
    marionette.start_session()
    measure_app_perf(marionette, gaia_atoms_path, app_name)

if __name__ == '__main__':
    main(sys.argv[1:])
