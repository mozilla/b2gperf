function launch_app(app_name) {
  let start = null;
  let origin = null;
  let windows = document.getElementById("windows");
  function firstpaint(evt) {
    let end = performance.now();
    windows.removeEventListener('mozbrowserfirstpaint', firstpaint);
    //window.wrappedJSObject.WindowManager.getAppFrame(origin)
    let id = evt.target.id;
    marionetteScriptFinished({'frame': id, 'origin': origin, 'time_to_paint': end - start});
  }

  GaiaApps.locateWithName(app_name, function(app, name, entry) {
    if (app == false) {
      marionetteScriptFinished(null);
      return;
    }
    windows.addEventListener('mozbrowserfirstpaint', firstpaint);
    origin = app.origin;
    start = performance.now();
    app.launch(entry);
  });
}
