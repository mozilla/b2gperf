"use strict";

function launch_app(app_name) {
  GaiaApps.locateWithName(app_name, function(app, name, entry) {
    let start = null;
    if (app) {
      let runningApps = window.wrappedJSObject.WindowManager.getRunningApps();
      let origin = GaiaApps.getRunningAppOrigin(name);
      let alreadyRunning = !!origin;

      start = performance.now();
      app.launch(entry || null);

      waitFor(
        function() {
          let app = runningApps[origin];
          let result = {frame: app.frame.id,
                        src: app.frame.src,
                        name: app.name,
                        origin: origin};

          if (alreadyRunning) {
            // return the app's frame id
            marionetteScriptFinished(result);
          }
          else {
            // wait until the new iframe sends the mozbrowserfirstpaint event
            let frame = runningApps[origin].frame;
            if (frame.dataset.unpainted) {
              window.addEventListener('mozbrowserfirstpaint', function firstpaint() {
                window.removeEventListener('mozbrowserfirstpaint', firstpaint);
                result['time_to_paint'] = performance.now() - start;
                marionetteScriptFinished(result);
              });
            }
            else {
              marionetteScriptFinished(result);
            }
          }
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
