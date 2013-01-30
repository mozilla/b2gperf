# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

# This script will simply kill any running Gaia apps, go to the Gaia homescreen,
# and then launch the specified app.  It will not wait for the app to appear,
# and it will not terminate the app.
#
# To run:
#   virtualenv --no-site-packages venv
#   cd venv
#   source bin/activate
#   pip install -e git://github.com/mozilla/gaia-ui-tests.git#egg=gaia-ui-tests
#   hg clone http://hg.mozilla.org/users/tmielczarek_mozilla.com/b2gperf
#   cd b2gperf
#   adb forward tcp:2828 tcp:2828
#   python simple_launch.py /path/to/gaia-atoms app_name
#      e.g.,
#   python simple_launch.py ../src/gaia-ui-tests/gaiatest/atoms Clock

from marionette import Marionette
from optparse import OptionParser
import os


def launchApp(marionette, gaia_atoms, app_name):
    # Unlock
    marionette.import_script(os.path.join(gaia_atoms, 'gaia_lock_screen.js'))
    marionette.execute_async_script('GaiaLockScreen.unlock()')
    # Kill all running apps
    marionette.import_script(os.path.join(gaia_atoms, 'gaia_apps.js'))
    marionette.switch_to_frame()
    marionette.execute_async_script('GaiaApps.killAll();')
    # Return to home screen
    marionette.execute_script('window.wrappedJSObject.dispatchEvent(new Event("home"));')
    script_dir = os.path.dirname(__file__)
    marionette.import_script(os.path.join(script_dir, 'launchapp.js'))
    app = marionette.execute_async_script('launch_app("%s")' % app_name)
    if not app:
        print 'Error launching app'
        return


def cli():
    parser = OptionParser(usage='%prog gaia_atoms_path app_name [app_name] ...')

    options, args = parser.parse_args()

    if not args:
        parser.print_usage()
        parser.exit()

    if not os.path.isdir(args[0]):
        parser.print_usage()
        print 'must specify valid path for gaia atoms'
        parser.exit()

    if len(args) != 2:
        parser.print_usage()
        print 'must specify at one app name'
        parser.exit()

    marionette = Marionette(host='localhost', port=2828)  # TODO command line option for address
    marionette.start_session()
    launchApp(
        marionette,
        gaia_atoms=args[0],
        app_name=args[1])


if __name__ == '__main__':
    cli()
