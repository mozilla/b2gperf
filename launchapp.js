function launch_app(origin) {
  let start = 0;
  let windows = document.getElementById("windows");
  function firstpaint(evt) {
    let end = performance.now();
    windows.removeEventListener('mozbrowserfirstpaint', firstpaint);
    let id = window.wrappedJSObject.WindowManager.getAppFrame(origin).id;
    marionetteScriptFinished({'frame': id, 'time_to_paint': end - start});
  }
  windows.addEventListener('mozbrowserfirstpaint', firstpaint);

  //TODO: GaiaApps.locateWithName
  let req = navigator.mozApps.mgmt.getAll();
  req.onsuccess = function() {
    let apps = req.result;
    for (let a of apps) {
      if (a.origin == origin) {
        start = performance.now();
        a.launch();
        return;
      }
    }
    marionetteScriptFinished(null);
  };
  req.onerror = function() { marionetteScriptFinished(null); };
}