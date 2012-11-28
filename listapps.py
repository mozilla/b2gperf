#!/usr/bin/env python
#
# This script will list all installed apps in a B2G instance.
# App names can be passed to b2gperf.py.
#
import sys, os
from marionette import Marionette

def listapps():
    marionette = Marionette(host='localhost', port=2828)
    marionette.start_session()
    marionette.set_context(marionette.CONTEXT_CONTENT)
    marionette.set_script_timeout(1000)
    apps = marionette.execute_async_script("""
  let req = navigator.mozApps.mgmt.getAll();
  req.onsuccess = function() {
    let apps = req.result;
    let l = []
    for (let a of apps) {
      let data = {origin: a.origin, name: a.manifest.name};
      if (a.manifest.entry_points)
        data.entry_points = a.manifest.entry_points;
      l.push(data);
    }
    marionetteScriptFinished(l);
  };
""")
    for a in apps:
        print a["name"]

if __name__ == '__main__':
    listapps()
