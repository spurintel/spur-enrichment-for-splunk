
NOTIFICATION_THRESHOLD = 1000

def notify_low_balance(ctx, balance):
    """
    Sends a notification to the user that their balance is low.
    """
    message = "Your Spur Context-API balance is low: %s" % balance
    ctx.service.messages.create(value=message, name="Spur Context-API", severity="warn")
