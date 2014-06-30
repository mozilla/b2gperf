#!/usr/bin/env python
#

import json

from b2gperf import dzOptionParser, DatazillaPerfPoster, B2GPerfError
from marionette import Marionette


class MozPerfHandler(DatazillaPerfPoster):

    def process_results(self, filename):
        with open(filename, 'r') as f:
            raw_results = json.loads(f.read())

        for app_results in raw_results:
            app_name = app_results.get('stats', {}).get('application')
            if not len(app_results.get('passes', ())):
                print "no passing results for %s, skipping" % app_name
                continue

            app_memory = '%s_memory' % app_name
            results = {'durations': {},
                       'uss': {app_memory: []},
                       'pss': {app_memory: []},
                       'rss': {app_memory: []},
                       'vsize': {app_memory: []},
                       'system_uss': {app_memory: []},
                       'system_pss': {app_memory: []},
                       'system_rss': {app_memory: []},
                       'system_vsize': {app_memory: []}}

            for result in app_results.get('passes'):
                metric = result['title'].strip().replace(' ', '_')
                results['durations'].setdefault(metric, []).extend(
                    result.get('mozPerfDurations'))
                for perfmemory in result.setdefault('mozPerfMemory', []):
                    if perfmemory.get('app'):
                        for memory_metric in ('uss', 'pss', 'rss', 'vsize'):
                            if perfmemory['app'].get(memory_metric):
                                results[memory_metric][app_memory].append(
                                    perfmemory['app'][memory_metric])
                    if perfmemory.get('system'):
                        for memory_metric in ('uss', 'pss', 'rss', 'vsize'):
                            if perfmemory['system'].get(memory_metric):
                                metric = results['system_%s' % memory_metric]
                                metric[app_memory].append(
                                    perfmemory['system'][memory_metric])

            if self.submit_report:
                for item in results:
                    name = app_name if item == 'durations' else item
                    self.post_to_datazilla(results[item], name)
            else:
                print 'results for %s' % app_name
                for item in results:
                    print item, json.dumps(results[item])


def cli():
    parser = dzOptionParser(usage='%prog [options] result_file')
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
    options, args = parser.parse_args()

    if not args:
        parser.print_usage()
        parser.exit()

    if len(args) != 1:
        parser.exit("You can only specify one result file")

    datazilla_config = parser.datazilla_config(options)

    try:
        host, port = options.address.split(':')
    except ValueError:
        raise B2GPerfError('--address must be in the format host:port')

    marionette = Marionette(host=host, port=int(port))
    marionette.start_session()
    handler = MozPerfHandler(marionette,
                             datazilla_config=datazilla_config,
                             sources=options.sources,
                             device_serial=options.device_serial)
    handler.process_results(args[0])


if __name__ == '__main__':
    cli()
