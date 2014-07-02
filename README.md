# b2gperf

b2gperf is a tool for testing the performance of
[Firefox OS](https://developer.mozilla.org/en-US/docs/Mozilla/Firefox_OS).

## Prerequisites

You will need a
[Marionette enabled Firefox build](https://developer.mozilla.org/en-US/docs/Marionette/Builds)
that you can
[successfully connect to](https://developer.mozilla.org/en-US/docs/Marionette/Connecting_to_B2G).

## Installation

Installation is simple:

    pip install b2gperf

If you anticipate modifying b2gperf, you can instead:

    git clone git://github.com/mozilla/b2gperf.git
    cd b2gperf
    python setup.py develop

## Running

    Usage: b2gperf [options] app_name [app_name] ...

    Options:
      -h, --help        show this help message and exit
      --dz-url=str      datazilla server url (default: https://datazilla.mozilla.org)
      --dz-project=str  datazilla project name
      --dz-branch=str   datazilla branch name
      --dz-key=str      oauth key for datazilla server
      --dz-secret=str   oauth secret for datazilla server
      --delay=float     duration (in seconds) to wait before each iteration
      --log-level=str   threshold for log output (default: INFO)
      --iterations=int  number of times to launch each app (default: 30)
      --no-restart      do not restart B2G between tests
      --settle-time     time to wait before initial launch (default: 60)
      --testvars=str    path to a json file with any test data required
      --test-type=str   type of test to run, valid types are: ['startup', 'scrollfps'] (default: startup)

## Test Variables

Currently the only test variable support is for a wifi network. If you want to
connect to wifi before measuring performance, please specify a path to a JSON
file that describes the network. For example:

    {
      "wifi": {
        "ssid": "MyNetwork",
        "keyManagement": "WPA-PSK",
        "psk": "SecurePassword"
      }
    }
