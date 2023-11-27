
def get_low_query_threshold(ctx):
    """
    Retreive the low query threshold from the splunk config.
    config name: customalerts.conf
    stanza: alerts
    setting: low_query_threshold
    """
    conf = ctx.service.confs['customalerts']
    return conf['alerts']['low_query_threshold']
