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
import traceback
from urlparse import urlparse
import xml.dom.minidom
import zipfile
import numpy

import mozlog
from progressbar import Counter
from progressbar import ProgressBar

import dzclient
import gaiatest
from marionette import Actions
from marionette import Marionette
from marionette.gestures import smooth_scroll

from wait import MarionetteWait

TEST_TYPES = ['startup', 'scrollfps']
SCROLLFPS_APP_NAMES = ['browser', 'contacts', 'email', 'homescreen']

class DatazillaPerfPoster(object):

    def __init__(self, marionette, datazilla_config=None, sources=None, log_level='INFO'):
        # Set up logging
        handler = mozlog.StreamHandler()
        handler.setFormatter(B2GPerfFormatter())
        self.logger = mozlog.getLogger(self.__class__.__name__, handler)
        self.logger.setLevel(getattr(mozlog, log_level.upper()))

        self.marionette = marionette

        settings = gaiatest.GaiaData(self.marionette).all_settings  # get all settings
        mac_address = self.marionette.execute_script('return navigator.mozWifiManager && navigator.mozWifiManager.macAddress;')
        self.logger.debug('Device MAC address: %s' % mac_address or 'Unknown')

        self.submit_report = True
        self.ancillary_data = {}
        self.device = gaiatest.GaiaDevice(self.marionette)

        if self.device.is_android_build:
            # get gaia, gecko and build revisions
            try:
                app_zip = self.device.manager.pullFile('/data/local/webapps/settings.gaiamobile.org/application.zip')
                with zipfile.ZipFile(StringIO(app_zip)).open('resources/gaia_commit.txt') as f:
                    gaia_revision = f.read().splitlines()[0]
                    self.logger.debug('Gaia revision: %s' % gaia_revision)
                    self.ancillary_data['gaia_revision'] = gaia_revision
            except zipfile.BadZipfile:
                # the zip file will not exist if Gaia has not been flashed to
                # the device, so we fall back to the sources file
                pass

            device_name = 'unknown'
            build_prop = self.device.manager.pullFile('/system/build.prop')
            device_prefix = 'ro.product.device='
            for line in build_prop.split('\n'):
                if line.startswith(device_prefix):
                    device_name = line[len(device_prefix):]
                    self.logger.debug('Device name: %s' % device_name)

            try:
                sources_xml = sources and xml.dom.minidom.parse(sources) or xml.dom.minidom.parseString(self.device.manager.catFile('system/sources.xml'))
                for element in sources_xml.getElementsByTagName('project'):
                    path = element.getAttribute('path')
                    revision = element.getAttribute('revision')
                    if not self.ancillary_data.get('gaia_revision') and path in 'gaia':
                        self.logger.debug('Gaia revision: %s' % revision)
                        self.ancillary_data['gaia_revision'] = revision
                    if path in ['gecko', 'build']:
                        self.logger.debug('%s revision: %s' % (path.capitalize(), revision))
                        self.ancillary_data['_'.join([path, 'revision'])] = revision
            except:
                pass

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
            'device name': device_name,
            'os version': settings.get('deviceinfo.os'),
            'id': settings.get('deviceinfo.platform_build_id')}

        for key, value in self.required.items():
            if not value:
                self.submit_report = False
                self.logger.warn('Missing required DataZilla field: %s' % key)

        if not self.submit_report:
            self.logger.info('Reports will not be submitted to DataZilla')

    def post_to_datazilla(self, results, app_name):
        # Prepare DataZilla results
        res = dzclient.DatazillaResult()
        test_suite = app_name.replace(' ', '_').lower()
        res.add_testsuite(test_suite)
        for metric in results.keys():
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
            dataset['test_machine'].update({'type': self.required.get('device name')})
            self.logger.info('Submitting results to DataZilla: %s' % dataset)
            response = req.send(dataset)
            self.logger.info('Response: %s' % response.read())


class B2GPerfRunner(DatazillaPerfPoster):

    def measure_app_perf(self, app_names, delay=1, iterations=30, restart=True,
                         settle_time=60, test_type='startup', testvars=None):
        # Store our attributes so tests can use them
        self.app_names = app_names
        self.delay = delay
        self.iterations = iterations
        self.restart = restart
        self.settle_time = settle_time
        self.testvars = testvars or {}

        # Add various attributes to the report
        self.ancillary_data['delay'] = self.delay
        self.ancillary_data['restart'] = self.restart
        self.ancillary_data['settle_time'] = self.settle_time

        if test_type == 'startup':
            self.logger.info('Running startup tests')
            self.test_startup()
        elif test_type == 'scrollfps':
            for app_name in self.app_names:
                if app_name.lower() not in SCROLLFPS_APP_NAMES:
                    self.logger.error("%s is not a valid scrollfps test app name. Please select one of %s" % (app_name, SCROLLFPS_APP_NAMES))
                    sys.exit(1)
            self.logger.info('Running FPS tests')
            self.test_scrollfps()
        else:
            self.logger.error('Invalid test type, it should be one of %s' % TEST_TYPES)

    def test_startup(self):
        requires_connection = ['marketplace']
        caught_exception = False

        self.marionette.set_script_timeout(60000)

        if not self.restart:
            self.logger.debug('Settling for %d seconds' % self.settle_time)
            time.sleep(self.settle_time)

        for app_name in self.app_names:
            progress = ProgressBar(widgets=['%s: ' % app_name, '[', Counter(), '/%d] ' % self.iterations], maxval=self.iterations)
            progress.start()

            if self.restart:
                self.logger.debug('Restarting B2G')
                self.device.restart_b2g()
                self.logger.debug('Settling for %d seconds' % self.settle_time)
                time.sleep(self.settle_time)

            apps = gaiatest.GaiaApps(self.marionette)
            data_layer = gaiatest.GaiaData(self.marionette)

            safe_volume = 5
            self.logger.debug('Setting content volume to %d' % safe_volume)
            data_layer.set_setting('audio.volume.content', safe_volume)

            self.logger.debug('Unlocking device')
            gaiatest.LockScreen(self.marionette).unlock()

            self.logger.debug('Killing all running apps')
            apps.kill_all()

            self.logger.debug('Returning to home screen')
            self.marionette.execute_script('window.wrappedJSObject.dispatchEvent(new Event("home"));')

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
                                if app_name.lower() in requires_connection:
                                    self.logger.debug('Connecting to WiFi')
                                    data_layer.enable_wifi()
                                    data_layer.connect_to_wifi(self.testvars.get('wifi'))
                                else:
                                    self.logger.debug('Disabling WiFi')
                                    data_layer.disable_wifi()
                            self.logger.debug('Waiting for %d seconds' % self.delay)
                            time.sleep(self.delay)
                            self.logger.debug("Launching '%s'" % app_name)
                            result = self.marionette.execute_async_script('launch_app("%s")' % app_name)
                            if not result:
                                raise Exception('Error launching app')
                            for metric in ['cold_load_time']:
                                if result.get(metric):
                                    value = result.get(metric)
                                    self.logger.debug("Metric '%s' returned: %s" % (metric, value))
                                    results.setdefault(metric, []).append(value)
                                else:
                                    raise Exception('%s missing %s metric in iteration %s' % (app_name, metric, i + 1))
                            self.logger.debug("Killing '%s'" % app_name)
                            apps.kill(gaiatest.GaiaApp(origin=result.get('origin')))
                            success_counter += 1
                        except Exception:
                            traceback.print_exc()
                            fail_counter += 1
                            self.logger.debug('Exception within failure threshold')
                            if fail_counter > fail_threshold:
                                progress.maxval = success_counter
                                progress.finish()
                                raise Exception('Exceeded failure threshold for gathering results!')
                        finally:
                            try:
                                self.logger.debug('Killing all running apps')
                                apps.kill_all()
                            except:
                                pass
                            progress.update(success_counter)
                progress.finish()
                if self.submit_report:
                    self.logger.debug('Submitting report')
                    self.post_to_datazilla(results, app_name)
                else:
                    for key, values in results.iteritems():
                        result_summary = 'median:%s, mean:%s, std: %s, max:%s, min:%s, all:%s' % (
                            int(numpy.median(values)),
                            int(numpy.mean(values)),
                            int(numpy.std(values)),
                            max(values),
                            min(values),
                            ','.join(str(x) for x in values))
                        self.logger.info('Results for %s, %s: %s' % (
                            app_name,
                            key,
                            result_summary))

            except Exception:
                traceback.print_exc()
                caught_exception = True

        if caught_exception:
            sys.exit(1)

    def test_scrollfps(self):
        requires_connection = ['browser']
        self.marionette.set_context(self.marionette.CONTEXT_CONTENT)
        caught_exception = False

        if not self.restart:
            self.logger.debug('Settling for %d seconds' % self.settle_time)
            time.sleep(self.settle_time)

        for app_name in self.app_names:
            progress = ProgressBar(widgets=['%s: ' % app_name, '[', Counter(), '/%d] ' % self.iterations], maxval=self.iterations)
            progress.start()

            if self.restart:
                self.logger.debug('Restarting B2G')
                self.device.restart_b2g()
                self.logger.debug('Settling for %d seconds' % self.settle_time)
                time.sleep(self.settle_time)

            apps = gaiatest.GaiaApps(self.marionette)
            data_layer = gaiatest.GaiaData(self.marionette)

            self.logger.debug('Unlocking device')
            gaiatest.LockScreen(self.marionette).unlock()

            self.logger.debug('Killing all running apps')
            apps.kill_all()

            self.logger.debug('Returning to home screen')
            self.marionette.execute_script('window.wrappedJSObject.dispatchEvent(new Event("home"));')

            self.marionette.import_script(pkg_resources.resource_filename(__name__, 'scrollapp.js'))

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
                            self.marionette.set_script_timeout(60000)
                            self.logger.debug('Waiting for %d seconds' % self.delay)
                            time.sleep(self.delay)
                            period = 5000  # ms
                            sample_hz = 100

                            if self.testvars.get('wifi') and self.marionette.execute_script('return window.navigator.mozWifiManager !== undefined'):
                                if app_name.lower() in requires_connection:
                                    self.logger.debug('Connecting to WiFi')
                                    data_layer.enable_wifi()
                                    data_layer.connect_to_wifi(self.testvars.get('wifi'))
                                else:
                                    self.logger.debug('Disabling WiFi')
                                    data_layer.disable_wifi()

                            app = apps.launch(app_name, switch_to_frame=False)

                            # Prepare app
                            self.marionette.switch_to_frame(app.frame)
                            self.prepare_app(app_name)
                            self.marionette.switch_to_frame()

                            # Turn on FPS
                            self.marionette.set_script_timeout(period + 1000)
                            self.logger.debug('Start measuring FPS')
                            result = self.marionette.execute_async_script('window.wrappedJSObject.fps = new fps_meter("%s", %d, %d); window.wrappedJSObject.fps.start_fps();' % (app_name, period, sample_hz))
                            if not result:
                                raise Exception('Error turning on fps measurement')

                            # Do scroll
                            self.marionette.set_script_timeout(60000)
                            self.marionette.switch_to_frame(app.frame)
                            self.marionette.execute_script('window.addEventListener("touchend", function() { window.wrappedJSObject.touchend = true; }, false);', new_sandbox=False)
                            self.scroll_app(app_name)
                            MarionetteWait(self.marionette, 30).until(lambda m: m.execute_script('return window.wrappedJSObject.touchend;', new_sandbox=False))
                            self.marionette.switch_to_frame()
                            self.logger.debug('Stop measuring FPS')
                            fps = self.marionette.execute_script('return window.wrappedJSObject.fps.stop_fps();')
                            for metric in ['fps']:
                                if fps.get(metric):
                                    value = fps.get(metric)
                                    self.logger.debug("Metric '%s' returned: %s" % (metric, value))
                                    results.setdefault(metric, []).append(value)
                                else:
                                    raise Exception('%s missing %s metric in iteration %s' % (app_name, metric, i + 1))

                            if fps:
                                self.logger.debug("Killing '%s'" % app_name)
                                gaiatest.GaiaApps(self.marionette).kill(gaiatest.GaiaApp(origin=fps.get('origin')))
                            success_counter += 1
                        except Exception:
                            traceback.print_exc()
                            fail_counter += 1
                            self.logger.debug('Exception within failure threshold')
                            if fail_counter > fail_threshold:
                                progress.maxval = success_counter
                                progress.finish()
                                raise Exception('Exceeded failure threshold for gathering results!')
                        finally:
                            try:
                                self.logger.debug('Killing all running apps')
                                apps.kill_all()
                            except:
                                pass
                            progress.update(success_counter)
                progress.finish()

                if self.submit_report:
                    self.logger.debug('Submitting report')
                    self.post_to_datazilla(results, app_name)
                else:
                    for key, values in results.iteritems():
                        result_summary = 'median:%s, mean:%s, std: %s, max:%s, min:%s, all:%s' % (
                            int(numpy.median(values)),
                            int(numpy.mean(values)),
                            int(numpy.std(values)),
                            max(values),
                            min(values),
                            ','.join(str(x) for x in values))
                        self.logger.info('Results for %s, %s: %s' % (
                            app_name,
                            key,
                            result_summary))

            except Exception:
                traceback.print_exc()
                caught_exception = True
        if caught_exception:
            sys.exit(1)

    def prepare_app(self, app_name):
        if app_name.lower() == 'browser':
            from gaiatest.apps.browser.app import Browser
            browser = Browser(self.marionette)
            browser.go_to_url('http://taskjs.org/')
            tab_frame = self.marionette.execute_script("return window.wrappedJSObject.Browser.currentTab.dom;")
            self.marionette.switch_to_frame(tab_frame)
            MarionetteWait(self.marionette, 30).until(lambda m: m.execute_script('return window.document.readyState;', new_sandbox=False) == 'complete')

    def scroll_app(self, app_name):
        touch_duration = float(200)

        #wait up to 30secs for the elements we want to show up
        self.marionette.set_search_timeout(30000)

        if app_name.lower() == 'homescreen':
            action = Actions(self.marionette)
            landing_page = self.marionette.find_element('id', 'landing-page')
            self.logger.debug('Swiping to first page of apps')
            action.flick(
                landing_page,
                landing_page.size['width'] / 100 * 90,
                landing_page.size['width'] / 2,
                landing_page.size['width'] / 100 * 10,
                landing_page.size['width'] / 2, touch_duration).perform()
            first_page = self.marionette.find_elements('css selector', '.page')[0]
            self.logger.debug('Swiping back to home screen')
            action.flick(
                first_page,
                first_page.size['width'] / 100 * 10,
                first_page.size['width'] / 2,
                first_page.size['width'] / 100 * 90,
                first_page.size['width'] / 2, touch_duration).perform()
        elif app_name.lower() == 'contacts':
            name = self.marionette.find_element("css selector", ".contact-item p > strong")
            MarionetteWait(self.marionette, 30).until(lambda m: name.is_displayed())
            self.logger.debug('Scrolling through contacts')
            smooth_scroll(self.marionette, name, "y", -1, 5000, scroll_back=False)
        elif app_name.lower() == 'browser':
            tab_dom = self.marionette.execute_script("return window.wrappedJSObject.Browser.currentTab.dom;", new_sandbox=False)
            self.logger.debug('Scrolling through browser content')
            smooth_scroll(self.marionette, tab_dom, "y", -1, 5000, scroll_back=True)
        elif app_name.lower() == 'email':
            email = self.marionette.find_element("class name", "msg-header-author")
            MarionetteWait(self.marionette, 30).until(lambda m: email.is_displayed() or not email.get_attribute('hidden'))
            emails = self.marionette.find_elements("class name", "msg-header-author")
            #we're dynamically adding these elements from a template, and the first one found is blank.
            MarionetteWait(self.marionette, 30).until(lambda m: emails[0].get_attribute('innerHTML'))
            emails = self.marionette.find_elements("class name", "msg-header-author")
            self.logger.debug('Scrolling through emails')
            smooth_scroll(self.marionette, emails[0], "y", -1, 2000, scroll_back=True)

class B2GPerfFormatter(mozlog.MozFormatter):

    def format(self, record):
        record.message = record.getMessage()
        import datetime
        record.timestamp = datetime.datetime.fromtimestamp(int(record.created)).strftime('%Y-%m-%d %H:%M:%S')
        sep = ' | '
        fmt = sep.join(['%(timestamp)s', '%(levelname)s', '%(message)s'])
        return fmt % record.__dict__


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
        self.add_option('--sources',
                        action='store',
                        dest='sources',
                        metavar='str',
                        help='path to sources.xml containing project revisions')

    def datazilla_config(self, options):
        if options.sources:
            if not os.path.exists(options.sources):
                raise Exception('--sources file does not exist')

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
    parser.add_option('--log-level',
                      action='store',
                      dest='log_level',
                      default='INFO',
                      metavar='str',
                      help='threshold for log output (default: %default)')
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
                      metavar='str',
                      help='type of test to run, valid types are: %s (default: startup)' % TEST_TYPES),
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
    b2gperf = B2GPerfRunner(marionette,
                            datazilla_config=datazilla_config,
                            sources=options.sources,
                            log_level=options.log_level)
    b2gperf.measure_app_perf(
        app_names=args,
        delay=options.delay,
        iterations=options.iterations,
        restart=options.restart,
        settle_time=options.settle_time,
        test_type=options.test_type,
        testvars=testvars)


if __name__ == '__main__':
    cli()
