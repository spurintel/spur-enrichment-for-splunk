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
    
    url = 'https://api.spur.us/v2/context/'
    url = urllib.parse.urljoin(url, ip_address)
    h = {"TOKEN": token, "Accept": "application/json"}
    logger.info("Headers: %s", h)
    req = urllib.request.Request(url, headers=h)
    logger.info("Requesting %s", url)
    with urllib.request.urlopen(req) as response:
        if response.status != 200:
            logger.error("Error for ip %s: %s", ip_address, response.status)
            return {}

        body = response.read().decode("utf-8")
        parsed = json.loads(body)
        return parsed
