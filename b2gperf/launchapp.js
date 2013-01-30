"use strict";

function launch_app(app_name) {
  GaiaApps.locateWithName(app_name, function(app, name, entry) {
    if (app) {
      let runningApps = window.wrappedJSObject.WindowManager.getRunningApps();
      let origin = GaiaApps.getRunningAppOrigin(name);

      app.launch(entry || null);

      waitFor(
        function() {
          let app = runningApps[origin];
          let result = {frame: app.frame.firstChild,
                        src: app.iframe.src,
                        name: app.name,
                        origin: origin};
          window.addEventListener('apploadtime', function apploadtime(aEvent) {
            window.removeEventListener('apploadtime', apploadtime);
            var load_type = (aEvent.detail.type === 'w') ? 'warm' : 'cold';
            result[load_type + '_load_time'] = aEvent.detail.time;
            marionetteScriptFinished(result);
          });
        },
        // wait until the app is found in the running apps list
        function() {
          origin = GaiaApps.getRunningAppOrigin(name);
          return !!origin;
        }
      );
    } else {
      marionetteScriptFinished(false);
    }
  });
}
