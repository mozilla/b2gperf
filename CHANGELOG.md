# Change Log

## 0.11
* Changed homescreen pages locator to work on both 1.2 and 1.3
* Disable the keyboard first time use screen

## 0.10
* Tests can now populate device content
* Added custom launch tests
* Refactored so scroll and launch tests can be more customised

## 0.9 (unreleased)
* Output HWComposer FPS values to debug log
* Move cleanup within error threshold measurements
* Require device name to be provided on the command line
* Improve debug logging for DataZilla fields
* Fix homescreen scroll fps test and scroll through all pages of apps
* Add video scroll fps test
* Add music scroll fps test
* Add messages scroll fps test
* Improved scrolling in browser app
* Improved scrolling in contacts app
* Add gallery scroll fps test
* Add settings scroll fps test
* Disable the keyboard FTU screen
* Add support for gathering FPS measurements from the HWComposer logs

## 0.8
* Remove case sensitivity from scroll fps tests
* Fail early if the app does not support scroll fps tests
* Add median to displayed results

## 0.7
* Added console level logging and debugging

## 0.6
* Fixed homescreen FPS test

## 0.5
* Fixed script timeout issue in FPS tests
* Updated locator for Contacts app

## 0.4
* Added average, min, and max values when reporting results
* Use gestures from the Marionette client
* Reverted fix for locale sensitive app names due to regression

## 0.3.6
* Added several testrun options to DataZilla report
* Remove locale sensitive app name checking when launching apps

## 0.3.5
* Avoid running the the stop FPS script asynchronously

## 0.3.4
* Fixed regression introduced by a bad merge

## 0.3.3
* Set the content audio volume to prevent warning dialog
* Maintain a list of apps that require a connection for each test type
* Include device type in DataZilla report

## 0.3.2
* No release

## 0.3.1
* Fixed missing manifest file for scrolling apps

## 0.3
* Stabilised scrolling FPS tests

## 0.2.1
* Avoid reseting the testsuite for every new metric we add
* Retrieve Gecko and Gaia revisions from provided sources file
* Reintroduced scrolling FPS tests

## 0.2
* Added support for connecting to a wifi network using test variables
* Sleep after the B2G process is restarted, not before
* Make settle time configurable from the command line
* Fixed issue when actual app name differs from requested app name
* Added support for progressbar
* Print results to the console if not submitting to DataZilla
* Added support for B2G desktop client (Firefox OS simulator) builds
* Removed profile population scripts in favour of using b2gpopulate

## 0.1.3
* Fixed dependancy for gaiatest
* Fixed packaging issues
* Added script to process mozPerfDuration results

## 0.1.2
* Fixed issues with the B2G restart

## 0.1.1
* Restart between tests, with a command line option to disable
* Removed FPS measurement collection
* Made more resilient to failures
* Use atoms packaged with gaiatest

## 0.1
* Initial release