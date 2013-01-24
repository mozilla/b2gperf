#!/usr/bin/env python
#
# Before running this:
# 1) Install a B2G build with Marionette enabled
# 2) adb forward tcp:2828 tcp:2828

from optparse import OptionParser
import os
import time
from urlparse import urlparse
import xml.dom.minidom

import dzclient
from marionette import Marionette


def measure_app_perf(marionette, gaia_atoms, app_names, iterations=30,
                     sources=None, datazilla_config=None):
    # Enable FPS counter first so data is stable by the time we measure it.
    marionette.set_context(marionette.CONTEXT_CHROME)
    script_dir = os.path.dirname(__file__)
    marionette.import_script(os.path.join(script_dir, 'fps.js'))
    marionette.execute_script(
        'Components.utils.import("resource://gre/modules/Services.jsm");'
        'Services.prefs.setBoolPref("layers.acceleration.draw-fps", true);')
    marionette.set_script_timeout(60000)
    marionette.set_context(marionette.CONTEXT_CONTENT)
    # Get all settings
    marionette.import_script(os.path.join(gaia_atoms, 'gaia_data_layer.js'))
    settings = marionette.execute_async_script('return GaiaDataLayer.getSetting("*");')
    mac_address = marionette.execute_script('return navigator.mozWifiManager && navigator.mozWifiManager.macAddress;')
    # Unlock
    marionette.import_script(os.path.join(gaia_atoms, 'gaia_lock_screen.js'))
    marionette.execute_async_script('GaiaLockScreen.unlock()')
    # Kill all running apps
    marionette.import_script(os.path.join(gaia_atoms, 'gaia_apps.js'))
    marionette.switch_to_frame()
    marionette.execute_async_script('GaiaApps.killAll();')
    # Return to home screen
    marionette.execute_script('window.wrappedJSObject.dispatchEvent(new Event("home"));')
    marionette.import_script(os.path.join(script_dir, 'launchapp.js'))

    results = {'time_to_paint': {}}
    for app_name in app_names:
        results['time_to_paint'][app_name] = []
        for i in range(iterations):
            print '%s: [%s/%s]' % (app_name, (i + 1), iterations)
            marionette.set_script_timeout(60000)
            # TODO this sleep is needed due to bug 821766
            # (and perhaps also to prevent panda board overheating...)
            time.sleep(1)
            app = marionette.execute_async_script('launch_app("%s")' % app_name)
            if not app:
                print 'Error launching app'
                return
            results['time_to_paint'][app_name].append(app.get('time_to_paint'))
            # try to get FPS
            marionette.set_context(marionette.CONTEXT_CHROME)
            period = 5000  # ms
            sample_hz = 10
            marionette.set_script_timeout(period + 1000)
            fps = marionette.execute_async_script('measure_fps(%d, %d)' % (period, sample_hz))
            if fps:
                print 'FPS: %f/%f' % (fps.get('composition_fps'),
                                      fps.get('transaction_fps'))
            marionette.execute_script('Services.prefs.setBoolPref("layers.acceleration.draw-fps", false);')
            marionette.set_context(marionette.CONTEXT_CONTENT)
            marionette.execute_async_script('GaiaApps.kill("%s")' % app.get('origin'))

    submit_report = True
    gecko_revision = None
    gaia_revision = None

    if sources:  # TODO use mozdevice to pull sources.xml
        sources_xml = xml.dom.minidom.parse(sources)
        for element in sources_xml.getElementsByTagName('project'):
            path = element.getAttribute('path')
            revision = element.getAttribute('revision')
            if path == 'gecko':
                gecko_revision = revision
            elif path == 'gaia':
                gaia_revision = revision

    required = {
        'gecko revision':gecko_revision,
        'protocol':datazilla_config['protocol'],
        'host':datazilla_config['host'],
        'project':datazilla_config['project'],
        'oauth key':datazilla_config['oauth_key'],
        'oauth secret':datazilla_config['oauth_secret'],
        'machine name':mac_address or 'unknown',
        'os version':settings.get('deviceinfo.os'),
        'id':settings.get('deviceinfo.platform_build_id')}

    for key, value in required.items():
        if not value:
            submit_report = False
            print 'Missing required DataZilla field: %s' % key

    if not submit_report:
        print 'Not submitting results to DataZilla'
        return
    else:
        # Prepare DataZilla results
        test_suite = 'b2g_gaia_launch_perf'
        res = dzclient.DatazillaResult()
        for metric in results.keys():
            res.add_testsuite(test_suite)
            for app_name in results[metric].keys():
                test_name = '_'.join([app_name, metric]).replace(' ', '_').lower()
                res.add_test_results(test_suite, test_name, results[metric][app_name])

        req = dzclient.DatazillaRequest(
            protocol=required.get('protocol'),
            host=required.get('host'),
            project=required.get('project'),
            oauth_key=required.get('oauth key'),
            oauth_secret=required.get('oauth secret'),
            machine_name=required.get('machine name'),
            os='Firefox OS',
            os_version=required.get('os version'),
            platform='Gonk',
            build_name='B2G',
            version='prerelease',
            revision=gaia_revision,
            branch='master',
            id=required.get('id'))

        # Send DataZilla results
        req.add_datazilla_result(res)
        for dataset in req.datasets():
            dataset['test_build']['gecko_revision'] = required.get('gecko revision')
            print 'Submitting results to DataZilla: %s' % dataset
            response = req.send(dataset)
            print 'Response: %s' % response.read()


def cli():
    parser = OptionParser(usage='%prog [options] gaia_atoms_path app_name [app_name] ...')
    parser.add_option('--iterations',
                      action='store',
                      type=int,
                      dest='iterations',
                      default=30,
                      metavar='int',
                      help='number of times to launch each app (default: %default)')
    parser.add_option('--sources',
                      action='store',
                      dest='sources',
                      metavar='path',
                      help='path to sources.xml containing project revisions')
    parser.add_option('--dz-url',
                      action='store',
                      dest='datazilla_url',
                      default='https://datazilla.mozilla.org',
                      metavar='str',
                      help='datazilla server url (default: %default)')
    parser.add_option('--dz-project',
                      action='store',
                      dest='datazilla_project',
                      metavar='str',
                      help='datazilla project name')
    parser.add_option('--dz-key',
                      action='store',
                      dest='datazilla_key',
                      metavar='str',
                      help='oauth key for datazilla server')
    parser.add_option('--dz-secret',
                      action='store',
                      dest='datazilla_secret',
                      metavar='str',
                      help='oauth secret for datazilla server')

    options, args = parser.parse_args()

    if not args:
        parser.print_usage()
        parser.exit()

    if not os.path.isdir(args[0]):
        parser.print_usage()
        print 'must specify valid path for gaia atoms'
        parser.exit()

    if len(args) < 2:
        parser.print_usage()
        print 'must specify at least one app name'
        parser.exit()

    datazilla_url = urlparse(options.datazilla_url)
    datazilla_config = {
        'protocol': datazilla_url.scheme,
        'host': datazilla_url.hostname,
        'project': options.datazilla_project,
        'oauth_key': options.datazilla_key,
        'oauth_secret': options.datazilla_secret}

    marionette = Marionette(host='localhost', port=2828)  # TODO command line option for address
    marionette.start_session()
    measure_app_perf(
        marionette,
        gaia_atoms=args[0],
        app_names=args[1:],
        iterations=options.iterations,
        sources=options.sources,
        datazilla_config=datazilla_config)


if __name__ == '__main__':
    cli()
