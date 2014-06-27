"use strict";

function launch(appName) {
  GaiaApps.locateWithName(appName, function(app, appName, launchPath, entryPoint) {
    if (app) {
      let origin = app.origin;
      if (GaiaApps.getDisplayedApp().origin == origin) {
        console.error("app with origin '" + origin + "' is already running");
        marionetteScriptFinished(false);
      }
      else {
        window.addEventListener('apploadtime', function appLoadTime(aEvent) {
          window.removeEventListener('apploadtime', appLoadTime);
          waitFor(
            function() {
              let appWindow = GaiaApps.getAppByURL(app.origin + launchPath);
              let result = {
                frame: (appWindow.browser) ? appWindow.browser.element : appWindow.frame.firstChild,
                src: (appWindow.browser) ? appWindow.browser.element.src : appWindow.iframe.src,
                name: appWindow.name,
                origin: appWindow.origin
              };
              let loadType = (aEvent.detail.type === 'w') ? 'warm' : 'cold';
              result[loadType + '_load_time'] = aEvent.detail.time;
              marionetteScriptFinished(result);
            },
            function() {
              return GaiaApps.getDisplayedApp().src == (origin + launchPath);
            }
          );
        });
        console.log("launching app with name '" + appName + "'");
        app.launch(entryPoint || null);
      }
    } else {
      marionetteScriptFinished(false);
    }
  });
}
