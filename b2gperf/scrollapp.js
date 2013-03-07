"use strict";

function fps_meter(app_name, period, sample_hz) {
  console.log("DBG: fps_meter constructor called\n");
  this.app_name = app_name;
  this.period = period;
  this.sample_hz = sample_hz;
}

fps_meter.prototype = {
  app_name: null,
  period: null,
  sample_hz: null,
  _app_origin: null,
  _startstamp: null,
  _data: [],
  _interval: null,
  _animation_handle: null,

  start_fps: function() {
    console.log("DBG:start_fps called\n");
    let self = this;
    GaiaApps.locateWithName(self.app_name, function(app, name, entry) {
      if (app) {
        self._app_origin = GaiaApps.getRunningAppOrigin(name);
        console.log("DBG: got app origin: " + self._app_origin + "\n"); 
        let utils = window.QueryInterface(Components.interfaces.nsIInterfaceRequestor).getInterface(Components.interfaces.nsIDOMWindowUtils);
        let cf = {}, cfps = {}, tf = {}, tfps = {};
        let showFPS = function showFPS() {
          try {
            //utils.getFPSInfo(cf, cfps, tf, tfps);
            //self._data.push([performance.now(), cf.value, cfps.value, tf.value, tfps.value]);
            console.log("DBG: showFPS called");
            self._data.push(performance.now());
            self._animation_handle = window.mozRequestAnimationFrame(showFPS);
          } catch (e) {
            console.log("DBG: Threw inside startfps: " + e + "\n");
            //clearInterval(self._interval);
            window.mozCancelAnimationFrame(self._animation_handle);
            marionetteScriptFinished(false);
          }
        };
        // Now we start measuring fps
        console.log("DBG::Starting the interval for showfps\n");
        window.mozRequestAnimationFrame(showFPS);
        //self._startstamp = performance.now();
        //self._interval = setInterval(showFPS, 1000 / self.sample_hz);
        //self._interval = setInterval(animate, 1000 / self.sample_hz);
        marionetteScriptFinished(true);
      } 
    });   
  },

  stop_fps: function() {
    console.log("DBG: stop_fps called\n");
    //window.clearInterval(this._interval);
    window.mozCancelAnimationFrame(this._animation_handle);
    // Calculate FPS over the entire period, but also provide the
    // entire list of instantaneous FPS estimates.
    /*let cp_fps_all = [x[2] for each (x in this._data)];
    let txn_fps_all = [x[4] for each (x in this._data)];
    let last = this._data.pop();
    let time_elapsed = last[0] - this._data[0][0];
    let total_cp_frames = last[1] - this._data[0][1];
    let total_txn_frames = last[3] - this._data[0][3];
    let cp_fps = (total_cp_frames - 1) / (time_elapsed / 1000);
    let txn_fps = (total_txn_frames - 1) / (time_elapsed / 1000);*/

    let time_elapsed = this._data[this._data.length -1] - this._data[0];
    let num_frames = this._data.length;
    let framepersec = num_frames/(time_elapsed/1000);
    console.log("DBG: Data is: " + this._data);  
    console.log("DBG: Total time elapsed was " + time_elapsed);
    console.log("DBG: num_frames: " + num_frames);
    console.log("DBG: fps: " + framepersec);
    //console.log("DBG: num cp frames: " + total_cp_frames);
    //console.log("DBG: cp_fps: " + cp_fps);
    //console.log("DBG: origin: " + this._app_origin);
    marionetteScriptFinished({origin: this._app_origin,
                      time_elapsed: time_elapsed,
                      number_frames: num_frames,
                      fps: framepersec});
                      //composition_fps: cp_fps,
                      //transaction_fps: txn_fps,
                      //composition_frames: total_cp_frames,
                      //transaction_frames: total_txn_frames,
                      //composition_fps_all: cp_fps_all,
                      //transaction_fps_all: txn_fps_all});
  }
};

