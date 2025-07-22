import os
import sys
import urllib
import urllib.request

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "splunklib"))
from splunklib.searchcommands import dispatch, StreamingCommand, Configuration, Option

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "spurlib"))
from spurlib.api import lookup, get_proxy_settings
from spurlib.logging import setup_logging
from spurlib.secrets import get_encrypted_context_api_token
from spurlib.formatting import format_for_enrichment, ENRICHMENT_FIELDS
from spurlib.notify import notify_low_balance
from spurlib.conf import get_low_query_threshold

CACHE = {}

@Configuration()
class SpurContextAPI(StreamingCommand):
    """
    Enriches records with context from the Spur API.
    """
    ip_field = Option(require=True)
    def stream(self, records):
        logger = setup_logging()
        proxy_handler_config = get_proxy_settings(self, logger)
        token = get_encrypted_context_api_token(self)
        low_balance_threshold = get_low_query_threshold(self)
        logger.debug("low_balance_threshold: %s", low_balance_threshold)
        if token is None or token == "":
            raise ValueError("No token found")
        if len(self.ip_field) == 0:
            raise ValueError("No ip field specified")
        ipfield = self.ip_field
        logger.debug("ipfield: %s", ipfield)
        notified = False
        for record in records:
            if ipfield in record and record[ipfield] != "":
                if CACHE.get(record[ipfield]):
                    ctx = CACHE[record[ipfield]]
                else:
                    try:
                        ctx, balance_remaining = lookup(logger, proxy_handler_config, token, record[ipfield], self)
                        if balance_remaining is not None:
                            if balance_remaining is not None and balance_remaining < int(low_balance_threshold) and not notified:
                                notify_low_balance(self, balance_remaining)
                                notified = True
                    except Exception as e:
                        error_msg = "Error looking up ip %s: %s" % (record[ipfield], e)
                        logger.error(error_msg)
                        ctx = {"spur_error": error_msg, "ip": record[ipfield]}
                if 'spur_ip' in ctx:
                    del ctx['spur_ip']
                CACHE[record[ipfield]] = ctx
                flattened = format_for_enrichment(ctx)
                for field in ENRICHMENT_FIELDS:
                    if field in flattened:
                        record[field] = flattened[field]
                    else:
                        record[field] = ""
            else: 
                ctx = {"spur_error": "No ip address found in record"}
                flattened = format_for_enrichment(ctx)
                for field in ENRICHMENT_FIELDS:
                    if field in flattened:
                        record[field] = flattened[field]
                    else:
                        record[field] = ""
            try:
                yield record
            except StopIteration:
                return


dispatch(SpurContextAPI, sys.argv, sys.stdin, sys.stdout, __name__)
