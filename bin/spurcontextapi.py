import os
import sys
import urllib.request
import json
import logging
import logging.handlers

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "splunklib"))
from splunklib.searchcommands import dispatch, StreamingCommand, Configuration, Option

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "spurlib"))
from spurlib.api import lookup
from spurlib.logging import setup_logging
from spurlib.secrets import get_encrypted_context_api_token
from spurlib.formatting import format_for_enrichment, ENRICHMENT_FIELDS

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
        if token is None or token == "":
            raise ValueError("No token found")
        if len(self.ip_field) == 0:
            raise ValueError("No ip field specified")
        ipfield = self.ip_field
        logger.info("ipfield: %s", ipfield)
        for record in records:
            if ipfield in record and record[ipfield] != "":
                if CACHE.get(record[ipfield]):
                    ctx = CACHE[record[ipfield]]
                else:
                    try:
                        ctx = lookup(logger, token, record[ipfield])
                    except Exception as e:
                        error_msg = "Error looking up ip %s: %s" % (record[ipfield], e)
                        logger.error(error_msg)
                        ctx = {"spur_error": error_msg}
                if 'ip' in ctx:
                    del ctx['ip']
                CACHE[record[ipfield]] = ctx
                logger.info("Context for %s: %s", record[ipfield], ctx)
                flattened = format_for_enrichment(ctx)
                for field in ENRICHMENT_FIELDS:
                    if field in flattened:
                        record[field] = flattened[field]
            yield record


dispatch(SpurContextAPI, sys.argv, sys.stdin, sys.stdout, __name__)
