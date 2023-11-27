
NOTIFICATION_THRESHOLD = 1000

def notify_low_balance(ctx, balance):
    """
    Sends a notification to the user that their balance is low.
    """
    message = "Your Spur Context-API balance is low: %s" % balance
    ctx.service.messages.create(value=message, name="Spur Context-API", severity="warn")


def notify_feed_failure(ctx, error):
    """
    Sends a notification to the user that their feed has failed.
    """
    message = "Spur Context-API feed failure: %s" % error
    ctx.service.messages.create(value=message, name="Spur Feed Error", severity="error")


def notify_feed_success(ctx, count):
    """
    Sends a notification to the user that their feed has succeeded.
    """
    message = "Spur Context-API feed success: %s records" % count
    ctx.service.messages.create(value=message, name="Spur Feed Success", severity="info")
