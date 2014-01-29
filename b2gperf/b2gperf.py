#!/usr/bin/env python
#
# Before running this:
# 1) Install a B2G build with Marionette enabled
# 2) adb forward tcp:2828 tcp:2828

from optparse import OptionParser
import os
import pkg_resources
import re
import time
import traceback
from urlparse import urlparse
import sys

from b2gpopulate import B2GPopulate
from b2gpopulate import B2GPopulateError
import dzclient
import gaiatest
from marionette import Actions
from marionette import Marionette
from marionette import Wait
from marionette import expected
from marionette.by import By
from marionette.errors import MarionetteException
from marionette.gestures import smooth_scroll
import mozdevice
import mozlog
import mozversion
import numpy

TEST_TYPES = ['startup', 'scrollfps']


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


class FpsError(B2GPerfError):
    def __init__(self):
        Exception.__init__(self, 'Error turning on fps measurement')


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
                 log_level='INFO'):
        # Set up logging
        handler = mozlog.StreamHandler()
        handler.setFormatter(mozlog.MozFormatter(include_timestamp=True))
        self.logger = mozlog.getLogger(self.__class__.__name__, handler)
        self.logger.setLevel(getattr(mozlog, log_level.upper()))

        self.marionette = marionette

        settings = gaiatest.GaiaData(self.marionette).all_settings
        mac_address = self.marionette.execute_script(
            'return navigator.mozWifiManager && '
            'navigator.mozWifiManager.macAddress;')

        self.submit_report = True
        self.ancillary_data = {}
        self.device = gaiatest.GaiaDevice(self.marionette)
        dm = mozdevice.DeviceManagerADB()
        self.device.add_device_manager(dm)

        version = mozversion.get_version(sources=sources, dm_type='adb')
        self.ancillary_data['build_revision'] = version.get('build_changeset')
        self.ancillary_data['gaia_revision'] = version.get('gaia_changeset')
        self.ancillary_data['gecko_revision'] = version.get('gecko_changeset')
        self.ancillary_data['ro.build.version.incremental'] = version.get(
            'device_firmware_version_incremental')
        self.ancillary_data['ro.build.version.release'] = version.get(
            'device_firmware_version_release')
        self.ancillary_data['ro.build.date.utc'] = version.get(
            'device_firmware_date')

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
            'machine name': datazilla_config['machine_name'] or mac_address,
            'device name': datazilla_config['device_name'],
            'os version': settings.get('deviceinfo.os'),
            'id': settings.get('deviceinfo.platform_build_id')}

        for key, value in self.required.items():
            if value:
                self.logger.debug('DataZilla field: %s (%s)' % (key, value))
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
            dataset['test_machine'].update(
                {'type': self.required.get('device name')})
            self.logger.info('Submitting results to DataZilla: %s' % dataset)
            response = req.send(dataset)
            self.logger.info('Response: %s' % response.read())


class B2GPerfRunner(DatazillaPerfPoster):

    def __init__(self, *args, **kwargs):
        self.delay = kwargs.pop('delay')
        self.iterations = kwargs.pop('iterations')
        self.restart = kwargs.pop('restart')
        self.settle_time = kwargs.pop('settle_time')
        self.test_type = kwargs.pop('test_type')
        self.testvars = kwargs.pop('testvars', {})
        self.reset = kwargs.pop('reset')

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
            if self.test_type == 'startup':
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
            elif self.test_type == 'scrollfps':
                tests = {
                    'browser': B2GPerfScrollBrowserTest,
                    'contacts': B2GPerfScrollContactsTest,
                    'email': B2GPerfScrollEmailTest,
                    'gallery': B2GPerfScrollGalleryTest,
                    'homescreen': B2GPerfScrollHomescreenTest,
                    'messages': B2GPerfScrollMessagesTest,
                    'music': B2GPerfScrollMusicTest,
                    'settings': B2GPerfScrollSettingsTest,
                    'video': B2GPerfScrollVideoTest}
                if app_name.lower() in tests.keys():
                    test_class = tests[app_name.lower()]
                else:
                    self.logger.error('%s is not a valid scroll test. Please '
                                      'select one of %s' % (app_name,
                                                            tests.keys()))
                    sys.exit(1)
            else:
                self.logger.error('Invalid test type, it should be one of %s' %
                                  TEST_TYPES)

            test = test_class(self.marionette, app_name, self.logger,
                              self.iterations, self.delay, self.device,
                              self.restart, self.settle_time, self.testvars,
                              self.reset)
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
                 device, restart, settle_time, testvars, reset):
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
        self.requires_connection = False
        self.b2gpopulate = B2GPopulate(self.marionette)

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
            self.device.manager.removeDir('/data/local/storage/persistent')
            self.device.manager.removeDir('/data/local/indexedDB')

            self.logger.debug('Removing profile')
            self.device.manager.removeDir('/data/b2g/mozilla')

            self.logger.debug('Removing files from sdcard')
            for item in self.device.manager.listFiles('/sdcard/'):
                self.device.manager.removeDir('/'.join(['/sdcard', item]))

        self.logger.debug('Populating databases')
        self.populate_databases()

        if self.restart:
            self.logger.debug('Starting B2G')
            self.device.start_b2g()

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
            'launch_app("%s")' % self.app_name)
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


class B2GPerfScrollTest(B2GPerfTest):

    def __init__(self, *args, **kwargs):
        B2GPerfTest.__init__(self, *args, **kwargs)
        self.metrics = ['fps']

    def after_scroll(self):
        self.logger.debug("Killing '%s'" % self.app_name)
        self.apps.kill(self.app)

    def before_scroll(self):
        self.logger.debug("Launching '%s'" % self.app_name)
        self.app = self.apps.launch(self.app_name)

    def setup(self):
        B2GPerfTest.setup(self)
        self.marionette.import_script(
            pkg_resources.resource_filename(__name__, 'scrollapp.js'))
        self.logger.debug('Enabling FPS debug')
        self.data_layer.set_setting('debug.fps.enabled', True)

    def scroll(self):
        pass

    def teardown(self):
        B2GPerfTest.teardown(self)
        self.logger.debug('Disabling FPS debug')
        self.data_layer.set_setting('debug.fps.enabled', False)

    def test(self):
        period = 5000  # ms
        sample_hz = 100

        self.marionette.switch_to_frame()
        self.logger.debug('Start measuring FPS')
        self.result = self.marionette.execute_async_script(
            'window.wrappedJSObject.fps = new fps_meter("%s", %d, %d); '
            'window.wrappedJSObject.fps.start_fps();' % (
                self.app_name, period, sample_hz))
        if not self.result:
            raise FpsError()

        self.before_scroll()

        self.marionette.switch_to_frame()
        self.marionette.switch_to_frame(self.app.frame)
        self.marionette.execute_script(
            'window.addEventListener("touchend", function() { '
            'window.wrappedJSObject.touchend = true; }, false);',
            new_sandbox=False)

        if self.device.is_android_build:
            self.logger.debug('Clearing logcat')
            self.device.manager.recordLogcat()

        self.scroll()

        Wait(self.marionette, timeout=30).until(
            lambda m: m.execute_script(
                'return window.wrappedJSObject.touchend;', new_sandbox=False))

        if self.device.is_android_build:
            self.logger.debug('Getting logcat')
            logcat = self.device.manager.getLogcat(['Gecko:I', '*:S'], 'brief')

        self.after_scroll()

        self.marionette.switch_to_frame()
        self.logger.debug('Stop measuring FPS')
        self.result = self.marionette.execute_script(
            'return window.wrappedJSObject.fps.stop_fps();')

        if logcat:
            hwc_fps_regex = re.compile('HWComposer: FPS is ([\d\.]+)')
            values = [float(hwc_fps_regex.search(line).group(1)) for
                      line in logcat if hwc_fps_regex.search(line)]
            if len(values) > 0:
                self.logger.debug('HWComposer FPS values: %s' % ','.join(
                    map(str, values)))
                if 'fps_hwc' not in self.metrics:
                    self.metrics.append('fps_hwc')
                self.result['fps_hwc'] = numpy.median(values)


class B2GPerfScrollBrowserTest(B2GPerfScrollTest):

    def __init__(self, *args, **kwargs):
        B2GPerfScrollTest.__init__(self, *args, **kwargs)
        self.requires_connection = True

    def before_scroll(self):
        B2GPerfScrollTest.before_scroll(self)
        from gaiatest.apps.browser.app import Browser
        app = Browser(self.marionette)
        app.go_to_url('http://taskjs.org/')
        # TODO Move readyState wait into app object
        app.switch_to_content()
        Wait(self.marionette, timeout=30).until(
            lambda m: m.execute_script(
                'return window.document.readyState;',
                new_sandbox=False) == 'complete')

    def scroll(self):
        start = self.marionette.execute_script(
            'return window.wrappedJSObject.Browser.currentTab.dom;',
            new_sandbox=False)
        self.logger.debug('Scrolling through browser content')
        smooth_scroll(self.marionette, start, 'y', -1, 2000,
                      increments=20, scroll_back=True)


class B2GPerfScrollContactsTest(B2GPerfScrollTest):

    def __init__(self, *args, **kwargs):
        B2GPerfScrollTest.__init__(self, *args, **kwargs)
        from gaiatest.apps.contacts.app import Contacts
        self.contacts = Contacts(self.marionette)
        self.contact_count = 200

    def before_scroll(self):
        B2GPerfScrollTest.before_scroll(self)
        self.logger.debug('Waiting for contacts to be displayed')
        contact = Wait(self.marionette, timeout=240).until(
            expected.element_present(*self.contacts._contact_locator))
        Wait(self.marionette, timeout=30).until(
            expected.element_displayed(contact))

    def populate_databases(self):
        self.b2gpopulate.populate_contacts(self.contact_count, restart=False)

    def scroll(self):
        start = self.marionette.find_element(*self.contacts._contact_locator)
        distance = self.marionette.execute_script(
            'return arguments[0].scrollHeight',
            script_args=[self.marionette.find_element(By.ID,
                                                      'groups-container')])
        self.logger.debug('Scrolling through contacts')
        smooth_scroll(self.marionette, start, 'y', -1, distance,
                      increments=20, scroll_back=True)


class B2GPerfScrollEmailTest(B2GPerfScrollTest):

    def before_scroll(self):
        B2GPerfScrollTest.before_scroll(self)
        self.logger.debug('Waiting for emails to be displayed')
        Wait(self.marionette, timeout=30).until(expected.element_displayed(
            self.marionette.find_element(By.CLASS_NAME, 'msg-header-author')))

    def scroll(self):
        # TODO Needs updating/fixing once we can pre-populate emails
        emails = self.marionette.find_elements(
            By.CLASS_NAME, 'msg-header-author')
        # We're dynamically adding these elements from a template, and the
        # first one found is blank.
        Wait(self.marionette, timeout=30).until(
            lambda m: emails[0].get_attribute('innerHTML'))
        emails = self.marionette.find_elements(
            By.CLASS_NAME, 'msg-header-author')
        self.logger.debug('Scrolling through emails')
        smooth_scroll(self.marionette, emails[0], 'y', -1, 2000,
                      increments=20, scroll_back=True)


class B2GPerfScrollGalleryTest(B2GPerfScrollTest):

    def __init__(self, *args, **kwargs):
        B2GPerfScrollTest.__init__(self, *args, **kwargs)
        from gaiatest.apps.gallery.app import Gallery
        self.gallery = Gallery(self.marionette)
        self.picture_count = 50

    def before_scroll(self):
        B2GPerfScrollTest.before_scroll(self)
        # TODO Replace with a suitable wait
        self.logger.debug('Sleep for 5 seconds to allow scan to start')
        time.sleep(5)
        self.logger.debug('Waiting for correct number of pictures')
        Wait(self.marionette, timeout=240).until(
            lambda m: len(m.find_elements(
                *self.gallery._gallery_items_locator)) == self.picture_count)
        self.logger.debug('Waiting for progress bar to be hidden')
        Wait(self.marionette, timeout=60).until(expected.element_not_displayed(
            self.marionette.find_element(*self.gallery._progress_bar_locator)))

    def populate_files(self):
        self.b2gpopulate.populate_pictures(self.picture_count)

    def scroll(self):
        start = self.marionette.find_element(
            *self.gallery._gallery_items_locator)
        distance = self.marionette.execute_script(
            'return arguments[0].scrollHeight',
            script_args=[self.marionette.find_element(By.ID, 'thumbnails')])
        self.logger.debug('Scrolling through gallery thumbnails')
        smooth_scroll(self.marionette, start, 'y', -1, distance,
                      increments=20, scroll_back=True)


class B2GPerfScrollHomescreenTest(B2GPerfScrollTest):

    def __init__(self, *args, **kwargs):
        B2GPerfScrollTest.__init__(self, *args, **kwargs)
        from gaiatest.apps.homescreen.app import Homescreen
        self.homescreen = Homescreen(self.marionette)

    def after_scroll(self):
        pass

    def before_scroll(self):
        self.app = gaiatest.GaiaApp(frame=self.apps.displayed_app.frame)
        self.marionette.switch_to_frame(self.app.frame)

    def scroll(self):
        action = Actions(self.marionette)
        for page in self.marionette.find_elements(By.CSS_SELECTOR,
                                                  '#icongrid > div')[:-1]:
            self.logger.debug('Swiping to next page of apps')
            action.flick(
                page,
                page.size['width'] / 100 * 90,
                page.size['width'] / 2,
                page.size['width'] / 100 * 10,
                page.size['width'] / 2, 200).perform()
            Wait(self.marionette, timeout=30).until(
                lambda m: page.get_attribute('aria-hidden') or
                not page.is_displayed())
        for page in reversed(self.marionette.find_elements(
                By.CSS_SELECTOR, '#icongrid > div')[1:]):
            Wait(self.marionette, timeout=30).until(
                lambda m: page.is_displayed() or
                not page.get_attribute('aria-hidden'))
            self.logger.debug('Swiping to previous page of apps')
            action.flick(
                page,
                page.size['width'] / 100 * 10,
                page.size['width'] / 2,
                page.size['width'] / 100 * 90,
                page.size['width'] / 2, 200).perform()


class B2GPerfScrollMessagesTest(B2GPerfScrollTest):

    def before_scroll(self):
        B2GPerfScrollTest.before_scroll(self)
        self.logger.debug('Waiting for messages to be displayed')
        Wait(self.marionette, timeout=240).until(
            expected.element_displayed(
                self.marionette.find_element(
                    By.CSS_SELECTOR, '#threads-container li')))

    def populate_databases(self):
        self.b2gpopulate.populate_messages(200, restart=False)

    def scroll(self):
        start = self.marionette.find_element(
            By.CSS_SELECTOR, '#threads-container li')
        distance = self.marionette.execute_script(
            'return arguments[0].scrollHeight',
            script_args=[self.marionette.find_element(
                By.ID, 'threads-container')])
        self.logger.debug('Scrolling through messages')
        smooth_scroll(self.marionette, start, 'y', -1, distance,
                      increments=20, scroll_back=True)


class B2GPerfScrollMusicTest(B2GPerfScrollTest):

    def __init__(self, *args, **kwargs):
        B2GPerfScrollTest.__init__(self, *args, **kwargs)
        self.music_count = 200
        self.tracks_per_album = 10
        self.album_count = self.music_count / self.tracks_per_album

    def before_scroll(self):
        B2GPerfScrollTest.before_scroll(self)
        # TODO Replace with a suitable wait
        self.logger.debug('Sleep for 5 seconds to allow scan to start')
        time.sleep(5)
        self.logger.debug('Waiting for progress bar to be hidden')
        Wait(self.marionette, timeout=240).until(
            expected.element_not_displayed(
                self.marionette.find_element(By.ID, 'scan-progress')))

    def populate_files(self):
        self.b2gpopulate.populate_music(
            self.music_count, tracks_per_album=self.tracks_per_album)

    def scroll(self):
        start = self.marionette.find_element(
            By.CSS_SELECTOR, '#views-tiles .tile')
        distance = self.marionette.execute_script(
            'return arguments[0].scrollHeight',
            script_args=[self.marionette.find_element(By.ID, 'views-tiles')])
        self.logger.debug('Scrolling through music albums')
        smooth_scroll(self.marionette, start, 'y', -1, distance,
                      increments=20, scroll_back=True)


class B2GPerfScrollSettingsTest(B2GPerfScrollTest):

    def scroll(self):
        start = self.marionette.find_element(
            By.CSS_SELECTOR, '#root .menu-item')
        distance = self.marionette.execute_script(
            'return arguments[0].scrollHeight',
            script_args=[self.marionette.find_element(
                By.CSS_SELECTOR, '#root > div')])
        self.logger.debug('Scrolling through settings')
        smooth_scroll(self.marionette, start, 'y', -1, distance,
                      increments=20, scroll_back=True)


class B2GPerfScrollVideoTest(B2GPerfScrollTest):

    def __init__(self, *args, **kwargs):
        B2GPerfScrollTest.__init__(self, *args, **kwargs)
        from gaiatest.apps.videoplayer.app import VideoPlayer
        self.video = VideoPlayer(self.marionette)
        self.video_count = 50

    def before_scroll(self):
        B2GPerfScrollTest.before_scroll(self)
        # TODO Replace with a suitable wait
        self.logger.debug('Sleep for 5 seconds to allow scan to start')
        time.sleep(5)
        self.logger.debug('Waiting for correct number of videos')
        Wait(self.marionette, timeout=120).until(
            lambda m: len(m.find_elements(
                By.CSS_SELECTOR,
                '#thumbnails .thumbnail')) == self.video_count)
        self.logger.debug('Waiting for progress bar to be hidden')
        Wait(self.marionette, timeout=60).until(expected.element_not_displayed(
            self.marionette.find_element(By.ID, 'throbber')))

    def populate_files(self):
        self.b2gpopulate.populate_videos(self.video_count)

    def scroll(self):
        start = self.marionette.find_element(
            By.CSS_SELECTOR, '#thumbnails .thumbnail')
        distance = self.marionette.execute_script(
            'return arguments[0].scrollHeight',
            script_args=[self.marionette.find_element(By.ID, 'thumbnails')])
        self.logger.debug('Scrolling through video thumbnails')
        smooth_scroll(self.marionette, start, 'y', -1, distance,
                      increments=20, scroll_back=True)


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
            'oauth_secret': options.datazilla_secret}
        return datazilla_config


def cli():
    parser = dzOptionParser(usage='%prog [options] app_name [app_name] ...')
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
    parser.add_option('--test-type',
                      action='store',
                      type='str',
                      dest='test_type',
                      default='startup',
                      metavar='str',
                      help='type of test to run, valid types are: %s '
                           '(default: startup)' % TEST_TYPES),
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

    if options.test_type not in TEST_TYPES:
        print 'Invalid test type. Test type must be one of %s' % TEST_TYPES
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

    # TODO command line option for address
    marionette = Marionette(host='localhost', port=2828)
    marionette.start_session()
    b2gperf = B2GPerfRunner(marionette,
                            datazilla_config=datazilla_config,
                            sources=options.sources,
                            log_level=options.log_level,
                            delay=options.delay,
                            iterations=options.iterations,
                            restart=options.restart,
                            settle_time=options.settle_time,
                            test_type=options.test_type,
                            testvars=testvars,
                            reset=options.reset)
    b2gperf.measure_app_perf(args)


if __name__ == '__main__':
    cli()
