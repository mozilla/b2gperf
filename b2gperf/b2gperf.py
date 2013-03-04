#!/usr/bin/env python
#
# Before running this:
# 1) Install a B2G build with Marionette enabled
# 2) adb forward tcp:2828 tcp:2828

from optparse import OptionParser
from StringIO import StringIO
import os
import pkg_resources
import sys
import time
from urlparse import urlparse
import xml.dom.minidom
from zipfile import ZipFile

from progressbar import Counter
from progressbar import ProgressBar

import dzclient
import gaiatest
from marionette import Marionette
import mozdevice

TEST_TYPES=['startup', 'scrollfps']

class DatazillaPerfPoster(object):

    def __init__(self, marionette, datazilla_config=None):
        self.marionette = marionette

        settings = gaiatest.GaiaData(self.marionette).all_settings  # get all settings
        mac_address = self.marionette.execute_script('return navigator.mozWifiManager && navigator.mozWifiManager.macAddress;')

        self.submit_report = True
        self.ancillary_data = {}

        if gaiatest.GaiaDevice(self.marionette).is_android_build:
            # get gaia revision
            device_manager = mozdevice.DeviceManagerADB()
            app_zip = device_manager.pullFile('/data/local/webapps/settings.gaiamobile.org/application.zip')
            with ZipFile(StringIO(app_zip)).open('resources/gaia_commit.txt') as f:
                self.ancillary_data['gaia_revision'] = f.read().splitlines()[0]

            # get gecko and build revisions
            sources_xml = xml.dom.minidom.parseString(device_manager.catFile('system/sources.xml'))
            for element in sources_xml.getElementsByTagName('project'):
                path = element.getAttribute('path')
                revision = element.getAttribute('revision')
                if path in ['gecko', 'build']:
                    self.ancillary_data['_'.join([path, 'revision'])] = revision

        self.required = {
            'gaia revision': self.ancillary_data.get('gaia_revision'),
            'gecko revision': self.ancillary_data.get('gecko_revision'),
            'build revision': self.ancillary_data.get('build_revision'),
            'protocol': datazilla_config['protocol'],
            'host': datazilla_config['host'],
            'project': datazilla_config['project'],
            'branch': datazilla_config['branch'],
            'oauth key': datazilla_config['oauth_key'],
            'oauth secret': datazilla_config['oauth_secret'],
            'machine name': mac_address or 'unknown',
            'os version': settings.get('deviceinfo.os'),
            'id': settings.get('deviceinfo.platform_build_id')}

        for key, value in self.required.items():
            if not value:
                self.submit_report = False
                print 'Missing required DataZilla field: %s' % key

        if not self.submit_report:
            print 'Reports will not be submitted to DataZilla'

    def post_to_datazilla(self, results, app_name):
        # Prepare DataZilla results
        res = dzclient.DatazillaResult()
        for metric in results.keys():
            test_suite = app_name.replace(' ', '_').lower()
            res.add_testsuite(test_suite)
            res.add_test_results(test_suite, metric, results[metric])
        req = dzclient.DatazillaRequest(
            protocol=self.required.get('protocol'),
            host=self.required.get('host'),
            project=self.required.get('project'),
            oauth_key=self.required.get('oauth key'),
            oauth_secret=self.required.get('oauth secret'),
            machine_name=self.required.get('machine name'),
            os='Firefox OS',
            os_version=self.required.get('os version'),
            platform='Gonk',
            build_name='B2G',
            version='prerelease',
            revision=self.ancillary_data.get('gaia_revision'),
            branch=self.required.get('branch'),
            id=self.required.get('id'))

        # Send DataZilla results
        req.add_datazilla_result(res)
        for dataset in req.datasets():
            dataset['test_build'].update(self.ancillary_data)
            print 'Submitting results to DataZilla: %s' % dataset
            response = req.send(dataset)
            print 'Response: %s' % response.read()


class B2GPerfRunner(DatazillaPerfPoster):

    def measure_app_perf(self, app_names, delay=1, iterations=30, restart=True,
                         settle_time=60, test_type='startup', testvars={}):
        # Store our attributes so tests can use them
        self.app_names = app_names
        self.delay = delay
        self.iterations = iterations
        self.restart = restart
        self.settle_time = settle_time
        self.testvars = testvars

        if test_type == 'startup':
            print "running startup test"
            marionette.import_script(os.path.join(script_dir, 'launchapp.js'))
            test_startup()
        elif test_type == 'scrollfps':
            print 'running fps test'
            marionette.import_script(os.path.join(script_dir, 'scrollapp.js'))
            test_scrollfps()
        else:
            print "ERROR: Invalid test type, it should be one of %s" % TEST_TYPES

    def test_startup(self):
        caught_exception = False

        self.marionette.set_script_timeout(60000)

        if not self.restart:
            time.sleep(self.settle_time)

        for app_name in self.app_names:
            progress = ProgressBar(widgets=['%s: ' % app_name, '[', Counter(), '/%d] ' % iterations], maxval=iterations)
            progress.start()

            if self.restart:
                gaiatest.GaiaDevice(self.marionette).restart_b2g()
                time.sleep(self.settle_time)

            apps = gaiatest.GaiaApps(self.marionette)
            data_layer = gaiatest.GaiaData(self.marionette)
            gaiatest.LockScreen(self.marionette).unlock()  # unlock
            apps.kill_all()  # kill all running apps
            self.marionette.execute_script('window.wrappedJSObject.dispatchEvent(new Event("home"));')  # return to home screen
            self.marionette.import_script(pkg_resources.resource_filename(__name__, 'launchapp.js'))

            try:
                results = {}
                success_counter = 0
                fail_counter = 0
                fail_threshold = int(self.iterations * 0.2)
                for i in range(self.iterations + fail_threshold):
                    if success_counter == self.iterations:
                        break
                    else:
                        try:
                            if self.testvars.get('wifi') and self.marionette.execute_script('return window.navigator.mozWifiManager !== undefined'):
                                data_layer.enable_wifi()
                                data_layer.connect_to_wifi(testvars.get('wifi'))
                            time.sleep(self.delay)
                            result = self.marionette.execute_async_script('launch_app("%s")' % app_name)
                            if not result:
                                raise Exception('Error launching app')
                            for metric in ['cold_load_time']:
                                if result.get(metric):
                                    results.setdefault(metric, []).append(result.get(metric))
                                else:
                                    raise Exception('%s missing %s metric in iteration %s' % (app_name, metric, i + 1))
                            apps.kill(gaiatest.GaiaApp(origin=result.get('origin')))  # kill application
                            success_counter += 1
                        except Exception, e:
                            apps.kill_all()
                            print e
                            fail_counter += 1
                            if fail_counter > fail_threshold:
                                progress.maxval = success_counter
                                progress.finish()
                                raise Exception('Exceeded failure threshold for gathering results!')
                        finally:
                            progress.update(success_counter)
                progress.finish()
                if self.submit_report:
                    self.post_to_datazilla(results, app_name)
                else:
                    print 'Results: %s' % results

            except Exception, e:
                print e
                caught_exception = True

        if caught_exception:
            sys.exit(1)

    def run_scrollfps(self):
        # Enable fps counter so it is stable
        self.marionette.set_context(marionette.CONTEXT_CHROME)
        self.marionette.execute_script(
            'Components.utils.import("resource://gre/modules/Services.jsm");'
            'Services.prefs.setBoolPref("layers.acceleration.draw-fps", true);')
        self.marionette.set_script_timeout(60000)
        self.marionette.set_context(marionette.CONTEXT_CONTENT)
        caught_exception = False 
        for app_name in self.app_names:
            try:
                fps = {}
                success_counter = 0
                fail_counter = 0
                fail_threshold = int(self.iterations * 0.2)
                for i in range(self.iterations + fail_threshold):
                    if success_counter == iterations:
                        break
                    else:
                        try:
                            print '%s: [%s/%s]' % (app_name, (i + 1), self.iterations + fail_counter)
                            self.marionette.set_script_timeout(60000)
                            time.sleep(self.delay)
                            period = 5000  # ms
                            sample_hz = 10
                            self.marionette.set_script_timeout(period + 1000)
                            fps = self.marionette.execute_async_script('scroll_app("%s", %d, %d)' % (app_name, period, sample_hz))
                            if fps:
                                print 'FPS: %f/%f' % (fps.get('composition_fps'),
                                                      fps.get('transaction_fps'))
                            
                            self.marionette.set_context(marionette.CONTEXT_CHROME)
                            self.marionette.execute_script('Services.prefs.setBoolPref("layers.acceleration.draw-fps", false);')
                            self.marionette.set_context(marionette.CONTEXT_CONTENT)
                            if fps:
                                gaiatest.GaiaApps(marionette).kill(gaiatest.GaiaApp(origin=fps.get('origin')))  # kill application
                            success_counter += 1
                        except Exception, e:
                            print e
                            fail_counter += 1
                            if fail_counter > fail_threshold:
                                raise Exception('Exceeded failure threshold for gathering results!')

                # TODO: This is where you submit to datazilla
                print "This is the FPS object: %s" % fps
            except Exception, e:
                print e
                caught_exception = True
        if caught_exception:
            sys.exit(1)

class dzOptionParser(OptionParser):
    def __init__(self, **kwargs):
        OptionParser.__init__(self, **kwargs)
        self.add_option('--dz-url',
                        action='store',
                        dest='datazilla_url',
                        default='https://datazilla.mozilla.org',
                        metavar='str',
                        help='datazilla server url (default: %default)')
        self.add_option('--dz-project',
                        action='store',
                        dest='datazilla_project',
                        metavar='str',
                        help='datazilla project name')
        self.add_option('--dz-branch',
                        action='store',
                        dest='datazilla_branch',
                        metavar='str',
                        help='datazilla branch name')
        self.add_option('--dz-key',
                        action='store',
                        dest='datazilla_key',
                        metavar='str',
                        help='oauth key for datazilla server')
        self.add_option('--dz-secret',
                        action='store',
                        dest='datazilla_secret',
                        metavar='str',
                        help='oauth secret for datazilla server')

    def datazilla_config(self, options):
        datazilla_url = urlparse(options.datazilla_url)
        datazilla_config = {
            'protocol': datazilla_url.scheme,
            'host': datazilla_url.hostname,
            'project': options.datazilla_project,
            'branch': options.datazilla_branch,
            'oauth_key': options.datazilla_key,
            'oauth_secret': options.datazilla_secret}
        return datazilla_config


def cli():
    parser = dzOptionParser(usage='%prog [options] app_name [app_name] ...')
    parser.add_option('--delay',
                      action='store',
                      type='float',
                      dest='delay',
                      default=1,  # TODO default is needed due to bug 821766
                      # (and perhaps also to prevent panda board overheating...)
                      metavar='float',
                      help='duration (in seconds) to wait before each iteration (default: %default)')
    parser.add_option('--iterations',
                      action='store',
                      type=int,
                      dest='iterations',
                      default=30,
                      metavar='int',
                      help='number of times to launch each app (default: %default)')
    parser.add_option('--no-restart',
                      action='store_false',
                      dest='restart',
                      default=True,
                      help='do not restart B2G between tests')
    parser.add_option('--settle-time',
                      action='store',
                      type='float',
                      dest='settle_time',
                      default=60,
                      metavar='float',
                      help='time to wait before initial launch (default: %default)')
    parser.add_option('--test-type',
                      action='store',
                      type='str',
                      dest='test_type',
                      default='startup',
                      help='Type of test to run, valid types are: %s' %
                      TEST_TYPES),
    parser.add_option('--testvars',
                      action='store',
                      dest='testvars',
                      metavar='str',
                      help='path to a json file with any test data required')
    options, args = parser.parse_args()

    if not args:
        parser.print_usage()
        parser.exit()

    if len(args) < 1:
        parser.print_usage()
        print 'must specify at least one app name'
        parser.exit()

    if options.test_type not in TEST_TYPES:
        print 'Invalid test type. Test type must be one of %s' % TEST_TYPES
        parser.exit()

    testvars = {}
    if options.testvars:
        if not os.path.exists(options.testvars):
            raise Exception('--testvars file does not exist')

        import json
        with open(options.testvars) as f:
            testvars = json.loads(f.read())

    datazilla_config = parser.datazilla_config(options)

    marionette = Marionette(host='localhost', port=2828)  # TODO command line option for address
    marionette.start_session()
    b2gperf = B2GPerfRunner(marionette, datazilla_config=datazilla_config)
    b2gperf.measure_app_perf(
        app_names=args,
        delay=options.delay,
        iterations=options.iterations,
        restart=options.restart,
        settle_time=options.settle_time,
        test_type=options.test_type
        testvars=testvars)


if __name__ == '__main__':
    cli()
