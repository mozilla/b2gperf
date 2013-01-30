import sys, os
from marionette import Marionette

def kill(origin):
    marionette = Marionette(host='localhost', port=2828)
    marionette.start_session()
    marionette.set_context(marionette.CONTEXT_CONTENT)
    marionette.execute_script("window.wrappedJSObject.WindowManager.kill('%s')" % origin)

if __name__ == '__main__':
    kill(sys.argv[1])
