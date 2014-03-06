#!/usr/bin/env python
#

import json

from b2gperf import dzOptionParser, DatazillaPerfPoster
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
            results = { 'durations': {},
                        'uss': { app_memory: [] },
                        'pss': { app_memory: [] },
                        'rss': { app_memory: [] },
                        'vsize': { app_memory: [] },
                        'system_uss': { app_memory: [] },
                        'system_pss': { app_memory: [] },
                        'system_rss': { app_memory: [] },
                        'system_vsize': { app_memory: [] },
                      }

            for result in app_results.get('passes'):
                metric = result['title'].strip().replace(' ', '_')
                results['durations'].setdefault(metric, []).extend(result.get('mozPerfDurations'))
                for perfmemory in result.setdefault('mozPerfMemory', []):
                    if perfmemory.get('app'):
                        for memory_metric in ('uss', 'pss', 'rss', 'vsize'):
                            if perfmemory['app'].get(memory_metric):
                                results[memory_metric][app_memory].append(perfmemory['app'][memory_metric])
                    if perfmemory.get('system'):
                        for memory_metric in ('uss', 'pss', 'rss', 'vsize'):
                            if perfmemory['system'].get(memory_metric):
                                results['system_%s' % memory_metric][app_memory].append(perfmemory['system'][memory_metric])

            if self.submit_report:
                for item in results:
                    name = app_name if item == 'durations' else item
                    self.post_to_datazilla(results[item], name)
            else:
                print 'results for %s' % app_name
                for item in results:
                    print item, json.dumps(results[item])

if __name__ == "__main__":
    parser = dzOptionParser(usage='%prog [options] result_file')
    options, args = parser.parse_args()

    if not args:
        parser.print_usage()
        parser.exit()

    if len(args) != 1:
        parser.exit("You can only specify one result file")

    datazilla_config = parser.datazilla_config(options)

    marionette = Marionette(host='localhost', port=2828)
    marionette.start_session()
    handler = MozPerfHandler(marionette,
                             datazilla_config=datazilla_config,
                             sources=options.sources)
    handler.process_results(args[0])
