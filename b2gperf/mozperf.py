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

            results = {}
            for result in app_results.get('passes'):
                metric = result['title'].strip().replace(' ', '_')
                results.setdefault(metric, []).extend(result.get('mozPerfDurations'))

            if self.submit_report:
                self.post_to_datazilla(results, app_name)
            else:
                print 'results for %s' % app_name
                print json.dumps(results)

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
