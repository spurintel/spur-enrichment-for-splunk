import os
import logging
import logging.handlers
import splunk

def setup_logging():
    """
    Create a logger for the Splunk scripts.
    """
    logger = logging.getLogger('splunk.spur')
    splunk_home = os.environ['SPLUNK_HOME']
    logging_default_config_file = os.path.join(splunk_home, 'etc', 'log.cfg')
    logging_local_config_file = os.path.join(
        splunk_home, 'etc', 'log-local.cfg')
    logging_stanza_name = 'python'
    logging_file_name = "spur.log"
    base_log_path = os.path.join('var', 'log', 'splunk')
    logging_format = "%(asctime)s %(levelname)-s\t%(module)s:%(lineno)d - %(message)s"
    splunk_log_handler = logging.handlers.RotatingFileHandler(
        os.path.join(splunk_home, base_log_path, logging_file_name), mode='a')
    splunk_log_handler.setFormatter(logging.Formatter(logging_format))
    logger.addHandler(splunk_log_handler)
    splunk.setupSplunkLogger(logger, logging_default_config_file,
                             logging_local_config_file, logging_stanza_name)
    return logger
