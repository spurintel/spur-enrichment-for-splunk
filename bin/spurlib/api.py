"""
Utilities for interacting with the Spur API.
"""


import urllib.request
import urllib.parse
import json
import ipaddress

_V2_CONTEXT_ENDPOINT = "https://api.spur.us/v2/context/"


def lookup(logger, token, ip_address):
    """
    Performs a lookup of the given IP address using the Spur Context-API.

    Args:
      ip_address (str): The IP address to lookup.

    Returns:
      dict: A dictionary containing the response body parsed as JSON.

    Raises:
      ValueError: If the HTTP status code is not 200.
    """
    # Make sure we get a valid token
    if token is None or token == "":
        raise ValueError("No token found")

    # Make sure its a valid ip
    try:
        ipaddress.ip_address(ip_address)
    except ValueError:
        raise ValueError("Invalid IP address")

    # We need to url encode the ip address
    ip_address = urllib.parse.quote(ip_address)
    url = 'https://api.spur.us/v2/context/'
    url = urllib.parse.urljoin(url, ip_address)
    h = {"TOKEN": token, "Accept": "application/json"}
    req = urllib.request.Request(url, headers=h)
    logger.info("Requesting %s", url)
    try:
        resp = urllib.request.urlopen(req)
        body = resp.read().decode("utf-8")
        parsed = json.loads(body)

        # get the x-balance-remaining header
        balance_remaining = int(resp.getheader("x-balance-remaining"))
        return parsed, balance_remaining
    except urllib.error.HTTPError as e:
        raw_error = e.read().decode("utf-8")
        err_msg = ""
        try:
          parsed = json.loads(raw_error)
          if "error" in parsed:
            err_msg = parsed["error"]
        except Exception:
          err_msg = raw_error
        msg = "Error for ip %s, HTTP Status %s: %s" % (ip_address, e.status, err_msg)
        logger.error(msg)

        # get the x-balance-remaining header
        balance_remaining = e.getheader("x-balance-remaining")

        return {"spur_error": msg}, balance_remaining
