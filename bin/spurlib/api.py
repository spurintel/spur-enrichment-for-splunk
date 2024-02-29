"""
Utilities for interacting with the Spur API.
"""


import requests
import urllib.request
import urllib.parse
import json
import ipaddress
import os

_V2_CONTEXT_ENDPOINT = "https://api.spur.us/v2/context/"


def get_proxy_settings(ctx, logger):
    """
    Return a proxy handler for the given context. If the proxy settings are available in the context, return a proxy. Otherwise try to load the proxy settings from the environment.
    """
    proxy_handler_config = {}
    server_config = ctx.service.confs["server"]
    if server_config:
      for stanza in server_config:
        if "proxyConfig" in stanza.name:
          logger.info("proxyConfig stanza found")
          for key in stanza.content:
            if key == "http_proxy":
              logger.info("key: %s", key)
              logger.info("value: %s", stanza.content[key])
              proxy_handler_config["http"] = stanza.content[key]
            if key == "https_proxy":
              logger.info("key: %s", key)
              logger.info("value: %s", stanza.content[key])
              proxy_handler_config["https"] = stanza.content[key]
    
    if "http" in proxy_handler_config or "https" in proxy_handler_config:
      return proxy_handler_config
       
    if "HTTP_PROXY" in os.environ:
        logger.info("HTTP_PROXY: %s", os.environ["HTTP_PROXY"])
        proxy_handler_config["http"] = os.environ["HTTP_PROXY"]
    if "HTTPS_PROXY" in os.environ:
        logger.info("HTTPS_PROXY: %s", os.environ["HTTPS_PROXY"])
        proxy_handler_config["https"] = os.environ["HTTPS_PROXY"]
    
    return proxy_handler_config


def lookup(logger, proxy_handler_config, token, ip_address):
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

    # setup the proxy handler
    logger.info("Using proxy handler config: %s", proxy_handler_config)

    # We need to url encode the ip address
    ip_address = urllib.parse.quote(ip_address)
    url = 'https://api.spur.us/v2/context/'
    url = urllib.parse.urljoin(url, ip_address)
    h = {"TOKEN": token, "Accept": "application/json"}
    logger.info("Requesting %s", url)
    try:
        resp = requests.get(url, headers=h, proxies=proxy_handler_config)
        parsed = resp.json()

        # get the x-balance-remaining header
        balance_remaining = int(resp.headers.get("x-balance-remaining", 0))
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
        balance_remaining = e.headers.get("x-balance-remaining", 0)

        return {"spur_error": msg}, balance_remaining
