# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.


from gaiatest import GaiaTestCase
import json
import os


class TestPopulateData(GaiaTestCase):
    """
    This 'test' just populates a device with contacts/photos/music files
    needed for gaia app startup performance tests.

    To run, install https://github.com/mozilla/gaia-ui-tests, then:
        adb forward tcp:2828 tcp:2828
        gaiatest --address localhost:2828 test_populate.py
    """

    _loading_overlay = ('id', 'loading-overlay')

    def add_contacts(self, count=1):
        self.marionette.switch_to_frame()

        print 'adding contacts'

        for x in range(0, count):
            if not x % 100:
                print '\tcontact %d - %d' % (x, x + 99)
            contact = {'name': 'testcontact_%d' % x,
                       'tel': {'type': 'Mobile', 'value': '1-555-522-%d' % x}}

            result = self.marionette.execute_async_script(
                'return GaiaDataLayer.insertContact(%s);' % json.dumps(contact),
                special_powers=True)
            assert(result)

        self.marionette.refresh()

    def push_resource(self, filename, count=1, destination=''):
        local = os.path.join(os.path.dirname(__file__), filename)
        remote = '/'.join(['sdcard', destination, filename])
        self.device_manager.mkDirs(remote)
        self.device_manager.pushFile(local, remote)

        for x in range(0, count):
            if not x % 100:
                print '\tfile %d - %d' % (x, min(x + 99, count))
            remote_copy = '%s_%d%s' % (remote[:remote.find('.')],
                                      x,
                                      remote[remote.find('.'):])
            self.device_manager._checkCmd(['shell',
                                           'dd',
                                           'if=%s' % remote,
                                           'of=%s' % remote_copy])

        self.device_manager.removeFile(remote)

    def add_music(self, count=1):
        print 'adding music'
        self.push_resource('MUS_0001.mp3', count=count, destination='')

    def add_photos(self, count=1):
        print 'adding photos'
        self.push_resource('IMG_fx.jpg', count=count, destination='DCIM/100MZLLA')

    def test_populate_data(self):
        self.add_contacts(count=100)
        self.add_music(count=500)
        self.add_photos(count=700)
