import os
import time
import sys
import json

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "splunklib"))
from splunklib.searchcommands import dispatch, GeneratingCommand, Configuration, Option

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "spurlib"))
from spurlib.api import lookup
from spurlib.logging import setup_logging
from spurlib.secrets import get_encrypted_context_api_token
from spurlib.notify import notify_low_balance
from spurlib.conf import get_low_query_threshold


@Configuration()
class SpurContextAPIGen(GeneratingCommand):
    """
    Generates a context record for a given IP address.
    """
    ip = Option(require=True)
    def generate(self):
        logger = setup_logging()
        token = get_encrypted_context_api_token(self)
        low_balance_threshold = get_low_query_threshold(self)
        logger.info("low_balance_threshold: %s", low_balance_threshold)
        if token is None or token == "":
            raise ValueError("No token found")
        if len(self.ip) == 0:
            raise ValueError("No ip specified")
        logger.info("ip: %s", self.ip)
        
        # Split the ip address by a comma in case it's a list of ip addresses
        ips = self.ip.split(",")
        for ip in ips:
            try:
                ctx, balance_remaining = lookup(logger, token, ip)
                if balance_remaining is not None and balance_remaining < int(low_balance_threshold):
                    notify_low_balance(self, balance_remaining)
            except Exception as e:
                logger.error("Error for ip %s: %s", ip, e)
                error_msg = "Error looking up ip %s: %s" % (ip, e)
                ctx = {"spur_error": error_msg, "ip": ip}

            record = {"_time": time.time(), 'event_no': 1, "_raw": json.dumps(ctx)}
            record.update(ctx)
            yield record

dispatch(SpurContextAPIGen, sys.argv, sys.stdin, sys.stdout, __name__)
