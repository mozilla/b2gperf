import sys, os
from marionette import Marionette

GAIA_DIR = "/home/luser/B2G/gaia"

def measure_app_perf(marionette, app_name):
    # Give apps a long timeout to launch
    marionette.set_script_timeout(60000)
    marionette.set_context(marionette.CONTEXT_CONTENT)
    marionette.import_script(os.path.join(GAIA_DIR, "tests/atoms/gaia_apps.js"))
    marionette.execute_script("GaiaApps.killAll()")
    #XXX: fixme: do something better
    marionette.execute_script("navigator.mozSettings.createLock().set({'lockscreen.enabled': false});")
    #XXX: send home button press?
    marionette.import_script("/build/b2gperf/launchapp.js")
    res = marionette.execute_async_script("launch_app('%s')" % app_name)
    if not res:
        print "Error launching app"
        return
    print "time_to_paint: %f" % res.get('time_to_paint')
    marionette.execute_script("window.wrappedJSObject.WindowManager.kill('%s')" % res.get('origin'))

def main(args):
    app_name = args[0] if args else "Clock"
    marionette = Marionette(host='localhost', port=2828)
    marionette.start_session()
    measure_app_perf(marionette, app_name)

if __name__ == '__main__':
    main(sys.argv[1:])
