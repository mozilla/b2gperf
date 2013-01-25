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
          let result = {frame: app.frame.firstChild,
                        src: app.iframe.src,
                        name: app.name,
                        origin: origin};

          if (alreadyRunning) {
            // return the app's frame id
            marionetteScriptFinished(result);
          }
          else {
            let frame = runningApps[origin].frame.firstChild;
            if ('unpainted' in frame.dataset) {
              // wait until the new application frame sends the mozbrowserloadend event
              window.addEventListener('mozbrowserloadend', function loadend() {
                window.removeEventListener('mozbrowserloadend', loadend);
                result['time_to_load_end'] = performance.now() - start;
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
