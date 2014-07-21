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

    For full usage details run `b2gperf --help`.

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
