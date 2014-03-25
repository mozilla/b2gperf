"use strict";

function launch_app(app_name) {
  GaiaApps.locateWithName(app_name, function(app, name, entry) {
    if (app) {
      let origin = app.origin;
      if (GaiaApps.getActiveApp().origin == origin) {
        console.error("app with origin '" + origin + "' is already running");
        marionetteScriptFinished(false);
      }
      else {
        window.addEventListener('apploadtime', function apploadtime(aEvent) {
          window.removeEventListener('apploadtime', apploadtime);
          waitFor(
            function() {
              let appWindow = GaiaApps.getAppByName(name);
              let result = {
                frame: (appWindow.browser) ? appWindow.browser.element : appWindow.frame.firstChild,
                src: (appWindow.browser) ? appWindow.browser.element.src : appWindow.iframe.src,
                name: appWindow.name,
                origin: appWindow.origin
              };
              let load_type = (aEvent.detail.type === 'w') ? 'warm' : 'cold';
              result[load_type + '_load_time'] = aEvent.detail.time;
              marionetteScriptFinished(result);
            },
            function() {
              return GaiaApps.getActiveApp().name == name;
            }
          );
        });
        app.launch(entry || null);
      }
    } else {
      marionetteScriptFinished(false);
    }
  });
}
