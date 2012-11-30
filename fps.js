function measure_fps(period) {
    let utils = window.QueryInterface(Components.interfaces.nsIInterfaceRequestor).getInterface(Components.interfaces.nsIDOMWindowUtils);
    let cf = {}, cfps = {}, tf = {}, tfps = {};
    let data = [];
    function showFPS() {
        utils.getFPSInfo(cf, cfps, tf, tfps);
        data.push([cf.value, cfps.value, tf.value, tfps.value]);
        if ((Date.now() - start) > period) {
            window.clearInterval(i);
            marionetteScriptFinished(data);
        }
    }

    let start = Date.now();
    let i = setInterval(showFPS, 100);
}
