"use strict";

function launch_app(app_name) {
  GaiaApps.locateWithName(app_name, function(app, name, entry) {
    if (app) {
      let windowManager = window.wrappedJSObject.WindowManager;
      let runningApps = windowManager.getRunningApps();
      let origin = GaiaApps.getRunningAppOrigin(name);

      if (windowManager.getDisplayedApp() == origin) {
        console.error("app with origin '" + origin + "' is already running");
        marionetteScriptFinished(false);
      }
      else {
        window.addEventListener('apploadtime', function apploadtime(aEvent) {
          window.removeEventListener('apploadtime', apploadtime);
          waitFor(
            function() {
              let app = runningApps[origin];
              let result = {frame: app.frame.firstChild,
                src: app.iframe.src,
                name: app.name,
                origin: origin};
              let load_type = (aEvent.detail.type === 'w') ? 'warm' : 'cold';
              result[load_type + '_load_time'] = aEvent.detail.time;
              marionetteScriptFinished(result);
            },
            function() {
              origin = GaiaApps.getRunningAppOrigin(name);
              return !!origin;
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
