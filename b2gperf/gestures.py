from marionette import Actions

#axis is y or x
#direction is negative or positive
def smooth_scroll(marionette_session, start_element, axis, direction, length, increments=None, wait_period=None, scroll_back=None):
    if axis not in ["x", "y"]:
        raise Exception("Axis must be either 'x' or 'y'")
    if direction not in ["negative", "positive"]:
        raise Exception("Direction must either be negative or positive")
    increments = increments or 100
    wait_period = wait_period or 0.05
    scroll_back = scroll_back or False
    current = 0
    if axis is "x":
        if direction is "negative":
            offset = [-increments, 0]
        else:
            offset = [increments, 0]
    else:
        if direction is "negative":
            offset = [0, -increments]
        else:
            offset = [0, increments]
    action = Actions(marionette_session)
    action.press(start_element)
    while (current < length):
        current += increments
        action.move_by_offset(*offset).wait(wait_period)
    if scroll_back:
        offset = [-value for value in offset]
        while (current > 0):
            current -= increments
            action.move_by_offset(*offset).wait(wait_period)
    action.release()
    action.perform()
