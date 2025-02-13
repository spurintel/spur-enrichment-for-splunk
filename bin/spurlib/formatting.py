"""
This module contains functions for formatting data for indexing into Splunk.
"""

ENRICHMENT_FIELDS = [
    "spur_ip",
    "spur_as_number",
    "spur_as_organization",
    "spur_organization",
    "spur_infrastructure",
    "spur_client_behaviors",
    "spur_client_concentration_country",
    "spur_client_concentration_city",
    "spur_client_concentration_geohash",
    "spur_client_concentration_density",
    "spur_client_concentration_skew",
    "spur_client_countries",
    "spur_client_spread",
    "spur_client_proxies",
    "spur_client_count",
    "spur_client_types",
    "spur_location_country",
    "spur_location_state",
    "spur_location_city",
    "spur_services",
    "spur_tunnels_type",
    "spur_tunnels_anonymous",
    "spur_tunnels_operator",
    "spur_risks",
    "spur_error",
]


def format_for_enrichment(data):
    """
    Formats a dictionary for enrichment into an existing Splunk event.
    """
    new_dict = {}
    if "ip" in data:
        new_dict["spur_ip"] = data["ip"]

    if "spur_error" in data:
        new_dict["spur_error"] = data["spur_error"]
        return new_dict

    if "as" in data:
        if "number" in data["as"]:
            new_dict["spur_as_number"] = data["as"]["number"]
        if "organization" in data["as"]:
            new_dict["spur_as_organization"] = data["as"]["organization"]
    else:
        new_dict["spur_as_number"] = ""
        new_dict["spur_as_organization"] = ""
    if "organization" in data:
        new_dict["spur_organization"] = data["organization"]
    else:
        new_dict["spur_organization"] = ""
    if "infrastructure" in data:
        new_dict["spur_infrastructure"] = data["infrastructure"]
    else:
        new_dict["spur_infrastructure"] = ""
    if "client" in data:
        if "behaviors" in data["client"]:
            new_dict["spur_client_behaviors"] = data["client"]["behaviors"]
        else:
            new_dict["spur_client_behaviors"] = []
        if "countries" in data["client"]:
            new_dict["spur_client_countries"] = data["client"]["countries"]
        else:
            new_dict["spur_client_countries"] = ""
        if "spread" in data["client"]:
            new_dict["spur_client_spread"] = data["client"]["spread"]
        else:
            new_dict["spur_client_spread"] = ""
        if "proxies" in data["client"]:
            new_dict["spur_client_proxies"] = data["client"]["proxies"]
        else:
            new_dict["spur_client_proxies"] = []
        if "count" in data["client"]:
            new_dict["spur_client_count"] = data["client"]["count"]
        else:
            new_dict["spur_client_count"] = ""
        if "types" in data["client"]:
            new_dict["spur_client_types"] = data["client"]["types"]
        else:
            new_dict["spur_client_types"] = []
        if "concentration" in data["client"]:
            if "country" in data["client"]["concentration"]:
                new_dict["spur_client_concentration_country"] = data["client"]["concentration"]["country"]
            else:
                new_dict["spur_client_concentration_country"] = ""
            if "city" in data["client"]["concentration"]:
                new_dict["spur_client_concentration_city"] = data["client"]["concentration"]["city"]
            else:
                new_dict["spur_client_concentration_city"] = ""
            if "geohash" in data["client"]["concentration"]:
                new_dict["spur_client_concentration_geohash"] = data["client"]["concentration"]["geohash"]
            else:
                new_dict["spur_client_concentration_geohash"] = ""
            if "density" in data["client"]["concentration"]:
                new_dict["spur_client_concentration_density"] = data["client"]["concentration"]["density"]
            else:
                new_dict["spur_client_concentration_density"] = ""
            if "skew" in data["client"]["concentration"]:
                new_dict["spur_client_concentration_skew"] = data["client"]["concentration"]["skew"]
            else:
                new_dict["spur_client_concentration_skew"] = ""
    else:
        new_dict["spur_client_behaviors"] = ""
        new_dict["spur_client_countries"] = ""
        new_dict["spur_client_spread"] = ""
        new_dict["spur_client_proxies"] = ""
        new_dict["spur_client_count"] = ""
        new_dict["spur_client_types"] = ""
        new_dict["spur_client_concentration_country"] = ""
        new_dict["spur_client_concentration_city"] = ""
        new_dict["spur_client_concentration_geohash"] = ""
        new_dict["spur_client_concentration_density"] = ""
        new_dict["spur_client_concentration_skew"] = ""
    if "location" in data:
        if "country" in data["location"]:
            new_dict["spur_location_country"] = data["location"]["country"]
        if "state" in data["location"]:
            new_dict["spur_location_state"] = data["location"]["state"]
        if "city" in data["location"]:
            new_dict["spur_location_city"] = data["location"]["city"]
    else:
        new_dict["spur_location_country"] = ""
        new_dict["spur_location_state"] = ""
        new_dict["spur_location_city"] = ""
    if "services" in data:
        new_dict["spur_services"] = data["services"]
    else:
        new_dict["spur_services"] = ""
    if "tunnels" in data:
        tunnel_types = []
        tunnels_anonymous = []
        tunnels_operator = []
        for tunnel in data["tunnels"]:
            if "type" in tunnel:
                tunnel_types.append(tunnel["type"])
            if "anonymous" in tunnel:
                tunnels_anonymous.append(str(tunnel["anonymous"]))
            if "operator" in tunnel:
                tunnels_operator.append(tunnel["operator"])
        new_dict["spur_tunnels_type"] = tunnel_types
        new_dict["spur_tunnels_anonymous"] = tunnels_anonymous
        new_dict["spur_tunnels_operator"] = tunnels_operator
    else:
        new_dict["spur_tunnels_type"] = ""
        new_dict["spur_tunnels_anonymous"] = ""
        new_dict["spur_tunnels_operator"] = ""
    if "risks" in data:
        new_dict["spur_risks"] = data["risks"]
    else:
        new_dict["spur_risks"] = []

    return new_dict
