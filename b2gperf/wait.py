import time

from marionette.errors import NoSuchElementException
from marionette.errors import TimeoutException

POLL_FREQUENCY = 0.5  # How long to sleep inbetween calls to the method
IGNORED_EXCEPTIONS = [NoSuchElementException]  # list of exceptions ignored during calls to the method


class MarionetteWait(object):

    def __init__(self, marionette, timeout, poll_frequency=POLL_FREQUENCY, ignored_exceptions=None):
        self._marionette = marionette
        self._timeout = timeout
        self._poll = poll_frequency
        # avoid the divide by zero
        if self._poll == 0:
            self._poll = POLL_FREQUENCY
        exceptions = IGNORED_EXCEPTIONS
        if ignored_exceptions is not None:
            try:
                exceptions.extend(iter(ignored_exceptions))
            except TypeError:  # ignored_exceptions is not iterable
                exceptions.append(ignored_exceptions)
        self._ignored_exceptions = tuple(exceptions)

    def until(self, method, message=''):
        end_time = time.time() + self._timeout
        while(True):
            try:
                value = method(self._marionette)
                if value:
                    return value
            except self._ignored_exceptions:
                pass
            time.sleep(self._poll)
            if(time.time() > end_time):
                break
        raise TimeoutException(message)

    def until_not(self, method, message=''):
        end_time = time.time() + self._timeout
        while(True):
            try:
                value = method(self._marionette)
                if not value:
                    return value
            except self._ignored_exceptions:
                return True
            time.sleep(self._poll)
            if(time.time() > end_time):
                break
        raise TimeoutException(message)
