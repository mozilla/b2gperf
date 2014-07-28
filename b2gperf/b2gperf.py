#!/usr/bin/env python
#
# Before running this:
# 1) Install a B2G build with Marionette enabled
# 2) adb forward tcp:2828 tcp:2828

from optparse import OptionParser
import os
import pkg_resources
import time
import traceback
from urlparse import urlparse
import sys

from b2gpopulate import B2GPopulate
from b2gpopulate import B2GPopulateError
import dzclient
import gaiatest
from marionette import Marionette
from marionette.errors import MarionetteException
import mozdevice
import mozlog
import mozversion
import numpy

from version import __version__


class B2GPerfError(Exception):
    def __init__(self, message):
        Exception.__init__(self, message)


class AppLaunchError(B2GPerfError):
    def __init__(self):
        Exception.__init__(self, 'Error launching app')


class ExceededThresholdError(B2GPerfError):
    def __init__(self):
        Exception.__init__(
            self, 'Exceeded failure threshold for gathering results')


class NetworkConnectionError(B2GPerfError):
    def __init__(self):
        Exception.__init__(self, 'Unable to connect to network')


class MissingMetricError(B2GPerfError):
    def __init__(self, app_name, metric, iteration):
        Exception.__init__(
            self, '%s missing %s metric in iteration %s' % (
                  app_name, metric, iteration))


class DatazillaPerfPoster(object):

    def __init__(self, marionette, datazilla_config=None, sources=None,
                 log_level='INFO', device_serial=None):
        # Set up logging
        handler = mozlog.StreamHandler()
        handler.setFormatter(mozlog.MozFormatter(include_timestamp=True))
        self.logger = mozlog.getLogger(self.__class__.__name__, handler)
        self.logger.setLevel(getattr(mozlog, log_level.upper()))

        self.device_serial = device_serial
        self.marionette = marionette

        settings = gaiatest.GaiaData(self.marionette).all_settings
        mac_address = self.marionette.execute_script(
            'return navigator.mozWifiManager && '
            'navigator.mozWifiManager.macAddress;')

        self.submit_report = True
        self.ancillary_data = {
            'generated_by': 'b2gperf %s' % __version__,
            'build_url': datazilla_config['build_url']}

        dm = mozdevice.DeviceManagerADB(deviceSerial=self.device_serial)
        self.device = gaiatest.GaiaDevice(self.marionette, manager=dm)

        version = mozversion.get_version(sources=sources, dm_type='adb',
                                         device_serial=self.device_serial)
        self.ancillary_data['build_revision'] = version.get('build_changeset')
        self.ancillary_data['gaia_revision'] = version.get('gaia_changeset')
        self.ancillary_data['gecko_repository'] = version.get('application_repository')
        self.ancillary_data['gecko_revision'] = version.get('application_changeset')
        self.ancillary_data['ro.build.version.incremental'] = version.get(
            'device_firmware_version_incremental')
        self.ancillary_data['ro.build.version.release'] = version.get(
            'device_firmware_version_release')
        self.ancillary_data['ro.build.date.utc'] = version.get(
            'device_firmware_date')

        self.required = {
            'generated_by': self.ancillary_data.get('generated_by'),
            'gaia_revision': self.ancillary_data.get('gaia_revision'),
            'gecko_repository': self.ancillary_data.get('gecko_repository'),
            'gecko_revision': self.ancillary_data.get('gecko_revision'),
            'build_revision': self.ancillary_data.get('build_revision'),
            'protocol': datazilla_config['protocol'],
            'host': datazilla_config['host'],
            'project': datazilla_config['project'],
            'branch': datazilla_config['branch'],
            'oauth_key': datazilla_config['oauth_key'],
            'oauth_secret': datazilla_config['oauth_secret'],
            'machine_name': datazilla_config['machine_name'] or mac_address,
            'device_name': datazilla_config['device_name'],
            'os_version': settings.get('deviceinfo.os'),
            'id': settings.get('deviceinfo.platform_build_id')}

        for key, value in self.required.items():
            if value:
                self.logger.debug('DataZilla field: %s (%s)' % (key, value))
            if not value:
                self.submit_report = False
                self.logger.warn('Missing required DataZilla field: %s' % key)

        for key, value in self.ancillary_data.items():
            if value and key not in self.required.keys():
                self.logger.debug('Ancillary field: %s (%s)' % (key, value))

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
            oauth_key=self.required.get('oauth_key'),
            oauth_secret=self.required.get('oauth_secret'),
            machine_name=self.required.get('machine_name'),
            os='Firefox OS',
            os_version=self.required.get('os_version'),
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
            dataset['test_machine'].update(
                {'type': self.required.get('device_name')})
            self.logger.info('Submitting results to DataZilla: %s' % dataset)
            response = req.send(dataset)
            self.logger.info('Response: %s' % response.read())


class B2GPerfRunner(DatazillaPerfPoster):

    def __init__(self, *args, **kwargs):
        self.delay = kwargs.pop('delay')
        self.iterations = kwargs.pop('iterations')
        self.restart = kwargs.pop('restart')
        self.settle_time = kwargs.pop('settle_time')
        self.testvars = kwargs.pop('testvars', {})
        self.reset = kwargs.pop('reset')
        self.start_timeout = kwargs.pop('start_timeout')

        DatazillaPerfPoster.__init__(self, *args, **kwargs)
        # Add various attributes to the report
        self.ancillary_data['delay'] = self.delay
        self.ancillary_data['restart'] = self.restart
        self.ancillary_data['settle_time'] = self.settle_time

    def measure_app_perf(self, app_names):
        caught_exception = False
        self.marionette.set_script_timeout(60000)
        self.marionette.set_search_timeout(60000)

        for app_name in app_names:
            tests = {
                'contacts': B2GPerfLaunchContactsTest,
                'gallery': B2GPerfLaunchGalleryTest,
                'messages': B2GPerfLaunchMessagesTest,
                'music': B2GPerfLaunchMusicTest,
                'video': B2GPerfLaunchVideoTest}
            if app_name.lower() in tests.keys():
                test_class = tests[app_name.lower()]
            else:
                test_class = B2GPerfLaunchTest

            test = test_class(self.marionette, app_name, self.logger,
                              self.iterations, self.delay, self.device,
                              self.restart, self.settle_time, self.testvars,
                              self.reset, self.start_timeout,
                              self.device_serial)
            try:
                test.run()

                if self.submit_report:
                    self.logger.debug('Submitting report')
                    self.post_to_datazilla(test.results, app_name)
                for key, values in test.results.iteritems():
                    result_summary = 'median:%s, mean:%s, std: %s, max:%s, ' \
                        'min:%s, all:%s' % (int(numpy.median(values)),
                                            int(numpy.mean(values)),
                                            int(numpy.std(values)),
                                            max(values),
                                            min(values),
                                            ','.join(str(x) for x in values))
                    self.logger.info('Results for %s, %s: %s' % (
                        app_name, key, result_summary))
            except (B2GPerfError, B2GPopulateError, MarionetteException):
                caught_exception = True
                traceback.print_exc()
        if caught_exception:
            sys.exit(1)


class B2GPerfTest(object):

    def __init__(self, marionette, app_name, logger, iterations, delay,
                 device, restart, settle_time, testvars, reset, start_timeout,
                 device_serial):
        self.marionette = marionette
        self.app_name = app_name
        self.logger = logger
        self.iterations = iterations
        self.delay = delay
        self.device = device
        self.restart = restart
        self.settle_time = settle_time
        self.testvars = testvars
        self.reset = reset
        self.start_timeout = start_timeout
        self.requires_connection = False
        self.device_serial = device_serial
        self.b2gpopulate = B2GPopulate(self.marionette,
                                       device_serial=self.device_serial)

    def connect_to_network(self):
        while not self.device.is_online:
            if self.testvars.get('wifi') and self.device.has_wifi:
                self.logger.debug('Connecting to WiFi')
                self.data_layer.connect_to_wifi(self.testvars['wifi'])
            elif self.device.has_mobile_connection:
                self.logger.debug('Connecting to cell data')
                self.data_layer.connect_to_cell_data()
            else:
                raise NetworkConnectionError()
        self.logger.debug('Connected to network')

    def populate_databases(self):
        self.logger.debug('No databases to populate')

    def populate_files(self):
        self.logger.debug('No files to populate')

    def setup(self):
        if self.restart:
            self.logger.debug('Stopping B2G')
            self.device.stop_b2g()

        if self.reset:
            self.logger.debug('Removing persistent storage')
            self.device.file_manager.remove('/data/local/storage/persistent')
            self.device.file_manager.remove('/data/local/indexedDB')

            self.logger.debug('Removing profile')
            self.device.file_manager.remove('/data/b2g/mozilla')

            self.logger.debug('Removing files from storage')
            # TODO: Remove hard-coded paths once bug 1018079 is resolved
            for path in ['/mnt/sdcard',
                         '/mnt/extsdcard',
                         '/storage/sdcard',
                         '/storage/sdcard0',
                         '/storage/sdcard1']:
                if self.device.file_manager.dir_exists(path):
                    for item in self.device.file_manager.list_items(path):
                        self.device.file_manager.remove('/'.join([path, item]))

        self.logger.debug('Populating databases')
        self.populate_databases()

        if self.restart:
            self.logger.debug('Starting B2G')
            self.device.start_b2g(self.start_timeout)

        self.apps = gaiatest.GaiaApps(self.marionette)
        self.data_layer = gaiatest.GaiaData(self.marionette)

        self.logger.debug('Populating files')
        self.populate_files()

        self.logger.debug('Settling for %d seconds' % self.settle_time)
        time.sleep(self.settle_time)

        self.marionette.switch_to_frame()

        safe_volume = 5
        self.logger.debug('Setting content volume to %d' % safe_volume)
        self.data_layer.set_setting('audio.volume.content', safe_volume)

        self.logger.debug('Switching off keyboard first time use screen')
        self.data_layer.set_setting('keyboard.ftu.enabled', False)

        self.logger.debug('Unlocking device')
        self.device.unlock()

        self.logger.debug('Killing all running apps')
        self.apps.kill_all()

        self.logger.debug('Returning to home screen')
        self.marionette.execute_script(
            'window.wrappedJSObject.dispatchEvent(new Event("home"));')

    def run(self):
        self.logger.info('Running %s' % self.__class__.__name__)
        self.setup()
        self.results = {}
        success_counter = 0
        fail_counter = 0
        fail_threshold = int(self.iterations * 0.2)

        for i in range(self.iterations + fail_threshold):
            while not success_counter == self.iterations:
                try:
                    if self.requires_connection:
                        self.logger.debug('Connecting to network')
                        self.connect_to_network()

                    self.logger.debug('Waiting for %d seconds' % self.delay)
                    time.sleep(self.delay)
                    self.test()
                    for metric in self.metrics:
                        if self.result.get(metric):
                            value = self.result.get(metric)
                            self.logger.debug("Metric '%s' returned: %s" % (
                                metric, value))
                            self.results.setdefault(metric, []).append(value)
                        else:
                            raise MissingMetricError(self.app_name, metric, i)
                    success_counter += 1
                    self.logger.info('%s [%s/%d]' % (self.app_name,
                                                     success_counter,
                                                     self.iterations))
                except (B2GPerfError, MarionetteException):
                    traceback.print_exc()
                    fail_counter += 1
                    self.logger.debug('Exception within failure threshold')
                    if fail_counter > fail_threshold:
                        raise ExceededThresholdError()
        self.teardown()

    def teardown(self):
        pass


class B2GPerfLaunchTest(B2GPerfTest):

    def __init__(self, *args, **kwargs):
        B2GPerfTest.__init__(self, *args, **kwargs)
        self.metrics = ['cold_load_time']

    def setup(self):
        B2GPerfTest.setup(self)
        self.marionette.import_script(
            pkg_resources.resource_filename(__name__, 'launchapp.js'))

    def test(self):
        self.logger.debug("Launching '%s'" % self.app_name)
        self.result = self.marionette.execute_async_script(
            'launch("%s")' % self.app_name)
        if not self.result:
            raise AppLaunchError()
        self.logger.debug("Killing '%s'" % self.app_name)
        self.apps.kill(gaiatest.GaiaApp(origin=self.result.get('origin')))


class B2GPerfLaunchContactsTest(B2GPerfLaunchTest):

    def populate_databases(self):
        self.b2gpopulate.populate_contacts(200, restart=False)


class B2GPerfLaunchGalleryTest(B2GPerfLaunchTest):

    def populate_files(self):
        self.b2gpopulate.populate_pictures(700)


class B2GPerfLaunchMessagesTest(B2GPerfLaunchTest):

    def populate_databases(self):
        self.b2gpopulate.populate_messages(200, restart=False)


class B2GPerfLaunchMusicTest(B2GPerfLaunchTest):

    def populate_files(self):
        self.b2gpopulate.populate_music(500)


class B2GPerfLaunchVideoTest(B2GPerfLaunchTest):

    def populate_files(self):
        self.b2gpopulate.populate_videos(100)


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
        self.add_option('--dz-device',
                        action='store',
                        dest='datazilla_device_name',
                        metavar='str',
                        help='datazilla device name')
        self.add_option('--dz-key',
                        action='store',
                        dest='datazilla_key',
                        metavar='str',
                        help='oauth key for datazilla server')
        self.add_option('--dz-machine',
                        action='store',
                        dest='datazilla_machine_name',
                        metavar='str',
                        help='datazilla machine name')
        self.add_option('--dz-secret',
                        action='store',
                        dest='datazilla_secret',
                        metavar='str',
                        help='oauth secret for datazilla server')
        self.add_option('--dz-build-url',
                        action='store',
                        dest='datazilla_build_url',
                        metavar='str',
                        help='url of the build generating the results')
        self.add_option('--sources',
                        action='store',
                        dest='sources',
                        metavar='str',
                        help='path to sources.xml containing project '
                             'revisions')

    def datazilla_config(self, options):
        if options.sources:
            if not os.path.exists(options.sources):
                raise B2GPerfError('--sources file does not exist')

        datazilla_url = urlparse(options.datazilla_url)
        datazilla_config = {
            'protocol': datazilla_url.scheme,
            'host': datazilla_url.hostname,
            'project': options.datazilla_project,
            'branch': options.datazilla_branch,
            'machine_name': options.datazilla_machine_name,
            'device_name': options.datazilla_device_name,
            'oauth_key': options.datazilla_key,
            'oauth_secret': options.datazilla_secret,
            'build_url': options.datazilla_build_url}
        return datazilla_config


def cli():
    parser = dzOptionParser(usage='%prog [options] app_name [app_name] ...')
    parser.add_option('--address',
                      action='store',
                      dest='address',
                      default='localhost:2828',
                      metavar='str',
                      help='address of marionette server (default: %default)')
    parser.add_option('--device-serial',
                      action='store',
                      dest='device_serial',
                      metavar='str',
                      help='serial identifier of device to target')
    parser.add_option('--delay',
                      action='store',
                      type='float',
                      dest='delay',
                      default=1,
                      metavar='float',
                      help='duration (in seconds) to wait before each '
                           'iteration (default: %default)')
    parser.add_option('--iterations',
                      action='store',
                      type=int,
                      dest='iterations',
                      default=30,
                      metavar='int',
                      help='number of times to launch each app '
                           '(default: %default)')
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
                      help='time to wait before initial launch '
                           '(default: %default)')
    parser.add_option('--start-timeout',
                      action='store',
                      type=int,
                      dest='start_timeout',
                      default=60,
                      metavar='int',
                      help='b2g start timeout in seconds (default: %default)')
    parser.add_option('--testvars',
                      action='store',
                      dest='testvars',
                      metavar='str',
                      help='path to a json file with any test data required'),
    parser.add_option('--reset',
                      action='store_true',
                      dest='reset',
                      default=False,
                      help='reset the target to a clean state between tests '
                           '(requires restart). WARNING: any personal data '
                           'will be removed!')
    options, args = parser.parse_args()

    if not args:
        parser.print_usage()
        parser.exit()

    if len(args) < 1:
        parser.print_usage()
        print 'must specify at least one app name'
        parser.exit()

    testvars = {}
    if options.testvars:
        if not os.path.exists(options.testvars):
            raise B2GPerfError('--testvars file does not exist')

        import json
        with open(options.testvars) as f:
            testvars = json.loads(f.read())

    if options.reset and not options.restart:
        raise B2GPerfError('--reset requires restart')

    datazilla_config = parser.datazilla_config(options)

    try:
        host, port = options.address.split(':')
    except ValueError:
        raise B2GPerfError('--address must be in the format host:port')

    marionette = Marionette(host=host, port=int(port))
    marionette.start_session()
    b2gperf = B2GPerfRunner(marionette,
                            datazilla_config=datazilla_config,
                            sources=options.sources,
                            log_level=options.log_level,
                            delay=options.delay,
                            iterations=options.iterations,
                            restart=options.restart,
                            settle_time=options.settle_time,
                            testvars=testvars,
                            reset=options.reset,
                            start_timeout=options.start_timeout,
                            device_serial=options.device_serial)
    b2gperf.measure_app_perf(args)


if __name__ == '__main__':
    cli()
