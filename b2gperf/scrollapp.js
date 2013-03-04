"use strict";

function scroll_app(app_name, period, sample_hz) {
  GaiaApps.locateWithName(app_name, function(app, name, entry) {
    if (app) {
      let origin = GaiaApps.getRunningAppOrigin(name);
      console.log("calling app.launch");
      app.launch(entry || null);
      console.log("DBG::about to waitfor\n");
      waitFor(
        function() {
          // This is the function called once the app launches, here we
          // scroll the app and measure the fps
          // TODO: Try out ted's old fps function first
          let utils = window.QueryInterface(Components.interfaces.nsIInterfaceRequestor).getInterface(Components.interfaces.nsIDOMWindowUtils);
          let cf = {}, cfps = {}, tf = {}, tfps = {};
          let data = [];
          function showFPS() {
            try {
              utils.getFPSInfo(cf, cfps, tf, tfps);
              data.push([performance.now(), cf.value, cfps.value, tf.value, tfps.value]);
              if ((Date.now() - start) > period) {
                window.clearInterval(i);
                // Calculate FPS over the entire period, but also provide the
                // entire list of instantaneous FPS estimates.
                let cp_fps_all = [x[2] for each (x in data)];
                let txn_fps_all = [x[4] for each (x in data)];
                let last = data.pop();
                let time_elapsed = last[0] - data[0][0];
                let total_cp_frames = last[1] - data[0][1];
                let total_txn_frames = last[3] - data[0][3];
                let cp_fps = (total_cp_frames - 1) / (time_elapsed / 1000);
                let txn_fps = (total_txn_frames - 1) / (time_elapsed / 1000);

                marionetteScriptFinished({origin: origin,
                                  time_elapsed: time_elapsed,
                                  composition_fps: cp_fps,
                                  transaction_fps: txn_fps,
                                  composition_frames: total_cp_frames,
                                  transaction_frames: total_txn_frames,
                                  composition_fps_all: cp_fps_all,
                                  transaction_fps_all: txn_fps_all});
              }
            } catch (e) {
              console.log("DBG::we threw inside showfps: " + e + "\n");
              clearInterval(i);
              marionetteScriptFinished(false);
            }
        }
        
        // Now we start measuring fps
        let start = Date.now();
        console.log("DBG::Starting the interval for showfps\n");
        let i = setInterval(showFPS, 1000 / sample_hz);

        // And we scroll the app! TODO: insert scrolling

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
