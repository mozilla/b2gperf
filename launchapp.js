function launch_app(app_name) {
  GaiaApps.locateWithName(app_name, function(app, name, entry) {
    let start = null;
    if (app) {
      let runningApps = window.wrappedJSObject.WindowManager.getRunningApps();
      let origin = GaiaApps.getRunningAppOrigin(name);
      let alreadyRunning = !!origin;

      start = performance.now();
      app.launch(entry || null);

      function sendResponse(origin, end) {
        let app = runningApps[origin];
        marionetteScriptFinished({frame: app.frame.id,
          src: app.frame.src,
          name: app.name,
          origin: origin,
          time_to_paint: end - start});
      }

      waitFor(
        function() {
          if (alreadyRunning) {
            // return the app's frame id
            sendResponse(origin);
          }
          else {
            // wait until the new iframe sends the mozbrowserfirstpaint event
            let frame = runningApps[origin].frame;
            if (frame.dataset.unpainted) {
              window.addEventListener('mozbrowserfirstpaint',
                function firstpaint() {
                  let end = performance.now();
                  window.removeEventListener('mozbrowserfirstpaint',
                    firstpaint);
                  sendResponse(origin, end);
                });
            }
            else {
              sendResponse(origin);
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
