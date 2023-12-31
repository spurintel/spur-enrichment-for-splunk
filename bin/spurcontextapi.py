import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "splunklib"))
from splunklib.searchcommands import dispatch, StreamingCommand, Configuration, Option

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "spurlib"))
from spurlib.api import lookup
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
        token = get_encrypted_context_api_token(self)
        low_balance_threshold = get_low_query_threshold(self)
        logger.info("low_balance_threshold: %s", low_balance_threshold)
        if token is None or token == "":
            raise ValueError("No token found")
        if len(self.ip_field) == 0:
            raise ValueError("No ip field specified")
        ipfield = self.ip_field
        logger.info("ipfield: %s", ipfield)
        notified = False
        for record in records:
            if ipfield in record and record[ipfield] != "":
                if CACHE.get(record[ipfield]):
                    ctx = CACHE[record[ipfield]]
                else:
                    try:
                        ctx, balance_remaining = lookup(logger, token, record[ipfield])
                        if balance_remaining is not None:
                            if balance_remaining is not None and balance_remaining < int(low_balance_threshold) and not notified:
                                notify_low_balance(self, balance_remaining)
                                notified = True
                    except Exception as e:
                        error_msg = "Error looking up ip %s: %s" % (record[ipfield], e)
                        logger.error(error_msg)
                        ctx = {"spur_error": error_msg}
                if 'ip' in ctx:
                    del ctx['ip']
                CACHE[record[ipfield]] = ctx
                flattened = format_for_enrichment(ctx)
                for field in ENRICHMENT_FIELDS:
                    if field in flattened:
                        record[field] = flattened[field]
            yield record


dispatch(SpurContextAPI, sys.argv, sys.stdin, sys.stdout, __name__)
