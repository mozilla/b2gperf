# b2gperf

b2gperf is a tool for testing the performance of
[Firefox OS](https://developer.mozilla.org/en-US/docs/Mozilla/Firefox_OS).

## Requirements

Your device must be running a build of Firefox OS with
[Marionette](https://developer.mozilla.org/docs/Marionette) enabled.

## Installation

Installation is simple:

    pip install b2gperf

If you anticipate modifying b2gperf, you can instead:

    git clone git://github.com/davehunt/b2gperf.git
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
      --iterations=int  number of times to launch each app (default: 30)
      --no-restart      do not restart B2G between tests
      --settle-time     time to wait before initial launch (default: 60)
