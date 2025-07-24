import os
import sys
import time

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "splunklib"))
from splunklib.searchcommands import dispatch, StreamingCommand, Configuration, Option

from spurlib.logging import setup_logging

try:
    import geoip2.database
    GEOIP_LIB = 'geoip2'
except ImportError:
    try:
        import maxminddb
        GEOIP_LIB = 'maxminddb'
    except ImportError:
        GEOIP_LIB = None

MMDB_PATH = os.path.join(
    os.environ.get('SPLUNK_HOME', '/opt/splunk'),
    'etc', 'apps', 'spur-enrichment-for-splunk', 'local', 'data', 'mmdb', 'ipgeo.mmdb'
)

# Field mapping for user-friendly names to internal keys
FIELD_MAPPING = {
    'country': 'spur_location_country',
    'country_iso': 'spur_location_country_iso',
    'country_geoname_id': 'spur_location_country_geoname_id',
    'subdivision': 'spur_location_subdivision',
    'subdivision_geoname_id': 'spur_location_subdivision_geoname_id',
    'city': 'spur_location_city',
    'city_geoname_id': 'spur_location_city_geoname_id',
    'continent': 'spur_location_continent',
    'continent_code': 'spur_location_continent_code',
    'continent_geoname_id': 'spur_location_continent_geoname_id',
    'registered_country': 'spur_location_registered_country',
    'registered_country_iso': 'spur_location_registered_country_iso',
    'registered_country_geoname_id': 'spur_location_registered_country_geoname_id',
    'latitude': 'spur_location_latitude',
    'longitude': 'spur_location_longitude',
    'accuracy_radius': 'spur_location_accuracy_radius',
    'timezone': 'spur_location_timezone',
    'as_number': 'spur_as_number',
    'as_organization': 'spur_as_organization',
    'error': 'spur_error'
}

ENRICHMENT_FIELDS = [
    "spur_location_country",
    "spur_location_country_iso",
    "spur_location_country_geoname_id",
    "spur_location_subdivision",
    "spur_location_subdivision_geoname_id",
    "spur_location_city",
    "spur_location_city_geoname_id",
    "spur_location_continent",
    "spur_location_continent_code",
    "spur_location_continent_geoname_id",
    "spur_location_registered_country",
    "spur_location_registered_country_iso",
    "spur_location_registered_country_geoname_id",
    "spur_location_latitude",
    "spur_location_longitude",
    "spur_location_accuracy_radius",
    "spur_location_timezone",
    "spur_as_number",
    "spur_as_organization",
    "spur_error"
]

def parse_fields_option(fields_str):
    """Pure function to parse comma-separated fields string into a set of field names."""
    if not fields_str:
        return set(ENRICHMENT_FIELDS)  # Return all fields if none specified
    
    requested_fields = [field.strip() for field in fields_str.split(',')]
    resolved_fields = set()
    
    for field in requested_fields:
        # Check if it's a user-friendly name
        if field in FIELD_MAPPING:
            resolved_fields.add(FIELD_MAPPING[field])
        # Check if it's already a full field name
        elif field in ENRICHMENT_FIELDS:
            resolved_fields.add(field)
        # If not found, we'll log a warning but continue
    
    # Always include error field for debugging
    resolved_fields.add('spur_error')
    
    return resolved_fields

def get_available_fields():
    """Pure function to return a list of available field names for user reference."""
    return list(FIELD_MAPPING.keys())

def extract_english_name(names_dict):
    """Pure function to extract English name from names dictionary."""
    if not names_dict:
        return ""
    return names_dict.get('en', "")

def extract_geoip2_data(resp):
    """Pure function to extract all location data from geoip2 response."""
    return {
        'country': resp.country.name or "",
        'country_iso': resp.country.iso_code or "",
        'country_geoname_id': resp.country.geoname_id or "",
        'subdivision': resp.subdivisions.most_specific.name or "",
        'subdivision_geoname_id': resp.subdivisions.most_specific.geoname_id or "",
        'city': resp.city.name or "",
        'city_geoname_id': resp.city.geoname_id or "",
        'continent': resp.continent.name or "",
        'continent_code': resp.continent.code or "",
        'continent_geoname_id': resp.continent.geoname_id or "",
        'registered_country': resp.registered_country.name or "",
        'registered_country_iso': resp.registered_country.iso_code or "",
        'registered_country_geoname_id': resp.registered_country.geoname_id or "",
        'latitude': resp.location.latitude or "",
        'longitude': resp.location.longitude or "",
        'accuracy_radius': resp.location.accuracy_radius or "",
        'timezone': resp.location.time_zone or "",
        'as_number': "",
        'as_organization': ""
    }

def extract_maxminddb_data(resp):
    """Pure function to extract all location data from maxminddb response."""
    if not resp:
        return create_empty_location_data()
    
    # Extract subdivision data
    subdivisions = resp.get('subdivisions', [])
    subdivision = ""
    subdivision_geoname_id = ""
    if subdivisions:
        subdivision = extract_english_name(subdivisions[0].get('names', {}))
        subdivision_geoname_id = subdivisions[0].get('geoname_id', "")
    
    # Extract AS information from spur section
    spur_data = resp.get('spur', {})
    as_data = spur_data.get('as', {})
    
    return {
        'country': extract_english_name(resp.get('country', {}).get('names', {})),
        'country_iso': resp.get('country', {}).get('iso_code', ""),
        'country_geoname_id': resp.get('country', {}).get('geoname_id', ""),
        'subdivision': subdivision,
        'subdivision_geoname_id': subdivision_geoname_id,
        'city': extract_english_name(resp.get('city', {}).get('names', {})),
        'city_geoname_id': resp.get('city', {}).get('geoname_id', ""),
        'continent': extract_english_name(resp.get('continent', {}).get('names', {})),
        'continent_code': resp.get('continent', {}).get('code', ""),
        'continent_geoname_id': resp.get('continent', {}).get('geoname_id', ""),
        'registered_country': extract_english_name(resp.get('registered_country', {}).get('names', {})),
        'registered_country_iso': resp.get('registered_country', {}).get('iso_code', ""),
        'registered_country_geoname_id': resp.get('registered_country', {}).get('geoname_id', ""),
        'latitude': resp.get('location', {}).get('latitude', ""),
        'longitude': resp.get('location', {}).get('longitude', ""),
        'accuracy_radius': resp.get('location', {}).get('accuracy_radius', ""),
        'timezone': resp.get('location', {}).get('time_zone', ""),
        'as_number': as_data.get('number', ""),
        'as_organization': as_data.get('organization', "")
    }

def create_empty_location_data():
    """Pure function to create empty location data structure."""
    return {
        'country': "",
        'country_iso': "",
        'country_geoname_id': "",
        'subdivision': "",
        'subdivision_geoname_id': "",
        'city': "",
        'city_geoname_id': "",
        'continent': "",
        'continent_code': "",
        'continent_geoname_id': "",
        'registered_country': "",
        'registered_country_iso': "",
        'registered_country_geoname_id': "",
        'latitude': "",
        'longitude': "",
        'accuracy_radius': "",
        'timezone': "",
        'as_number': "",
        'as_organization': ""
    }

def populate_record_with_location_data(record, location_data, selected_fields, error_msg=""):
    """Pure function to populate record with selected location data fields."""
    # Mapping from internal data keys to field names
    data_to_field_mapping = {
        'country': 'spur_location_country',
        'country_iso': 'spur_location_country_iso',
        'country_geoname_id': 'spur_location_country_geoname_id',
        'subdivision': 'spur_location_subdivision',
        'subdivision_geoname_id': 'spur_location_subdivision_geoname_id',
        'city': 'spur_location_city',
        'city_geoname_id': 'spur_location_city_geoname_id',
        'continent': 'spur_location_continent',
        'continent_code': 'spur_location_continent_code',
        'continent_geoname_id': 'spur_location_continent_geoname_id',
        'registered_country': 'spur_location_registered_country',
        'registered_country_iso': 'spur_location_registered_country_iso',
        'registered_country_geoname_id': 'spur_location_registered_country_geoname_id',
        'latitude': 'spur_location_latitude',
        'longitude': 'spur_location_longitude',
        'accuracy_radius': 'spur_location_accuracy_radius',
        'timezone': 'spur_location_timezone',
        'as_number': 'spur_as_number',
        'as_organization': 'spur_as_organization'
    }
    
    # Only populate selected fields
    for data_key, field_name in data_to_field_mapping.items():
        if field_name in selected_fields:
            record[field_name] = location_data[data_key]
    
    # Always set error field
    if 'spur_error' in selected_fields:
        record["spur_error"] = error_msg
    
    return record

def ensure_selected_fields_present(record, selected_fields):
    """Pure function to ensure selected enrichment fields are present in record."""
    for field in selected_fields:
        if field not in record:
            record[field] = ""
    return record

def download_mmdb_if_needed(ctx, logger, mmdb_path):
    """
    Download MMDB file if it doesn't exist or is older than 24 hours.
    Raises ValueError with user-friendly message if download fails.
    """
    try:
        # Import here to avoid circular imports
        sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "spurlib"))
        from spurlib.secrets import get_encrypted_context_api_token
        
        # Import the complete geo feed processing function
        sys.path.insert(0, os.path.dirname(__file__))
        from spurfeedingest import process_geo_feed
        
        # Check if file exists and is recent (less than 24 hours old)
        if os.path.exists(mmdb_path):
            file_age = time.time() - os.path.getmtime(mmdb_path)
            if file_age < 7 * 86400:  # 7 days in seconds
                logger.debug("MMDB file exists and is recent, using existing file")
                return
            else:
                logger.debug("MMDB file exists but is older than 24 hours, will refresh")
        
        logger.info("Downloading MMDB file from Spur API")
        
        # Get token using the command context
        token = get_encrypted_context_api_token(ctx)
        if not token or token == "":
            raise ValueError("No Spur API token configured. Please configure your Spur API token in the setup page.")
        
        # Use the existing process_geo_feed function to handle the complete download
        process_geo_feed(ctx, logger, token, "ipgeo", "spuriplocation", None)
        
        # Verify the file was created
        if not os.path.exists(mmdb_path):
            raise ValueError("Failed to download Spur MMDB file. Please check your network connectivity and API token.")
        
        logger.info("Successfully downloaded MMDB file to %s", mmdb_path)
            
    except ValueError:
        # Re-raise ValueError with original message
        raise
    except Exception as e:
        # Get more detailed error information
        import traceback
        error_details = traceback.format_exc()
        logger.error("Error downloading MMDB file: %s", e)
        logger.error("Full traceback: %s", error_details)
        
        # Provide specific error messages based on error type
        if "401" in str(e) or "Unauthorized" in str(e):
            error_msg = f"Failed to download Spur MMDB file: Invalid API token. Please check your API token configuration."
        elif "403" in str(e) or "Forbidden" in str(e):
            error_msg = f"Failed to download Spur MMDB file: Access denied. Please check your API token permissions."
        elif "timeout" in str(e).lower() or "timed out" in str(e).lower():
            error_msg = f"Failed to download Spur MMDB file: Connection timeout. Please check your network connectivity and proxy settings."
        elif "connection" in str(e).lower():
            error_msg = f"Failed to download Spur MMDB file: Connection error ({str(e)}). Please check your network connectivity and proxy settings."
        else:
            error_msg = f"Failed to download Spur MMDB file: {str(e) or type(e).__name__}. Please check your network connectivity, proxy settings, and API token."
        
        raise ValueError(error_msg)

@Configuration(distributed=False)
class SpurIPLocation(StreamingCommand):
    """
    Enriches records with location info from the Spur IPGeo MMDB.
    """
    ip_field = Option(require=True)
    fields = Option(require=False, default="")

    def stream(self, records):
        logger = setup_logging()
        ipfield = self.ip_field
        selected_fields = parse_fields_option(self.fields)
        
        logger.debug("ipfield: %s", ipfield)
        logger.debug("selected_fields: %s", selected_fields)
        
        # Log available fields if user specified invalid ones
        if self.fields:
            available = get_available_fields()
            logger.debug("Available field names: %s", ', '.join(available))
        
        if not GEOIP_LIB:
            raise ValueError("Required library not found. Please install either 'geoip2' or 'maxminddb' Python package.")
            
        # Try to download MMDB if it doesn't exist or is stale
        # This will raise ValueError with clear message if it fails
        download_mmdb_if_needed(self, logger, MMDB_PATH)
            
        if GEOIP_LIB == 'geoip2':
            reader = geoip2.database.Reader(MMDB_PATH)
        else:
            reader = maxminddb.open_database(MMDB_PATH)
            
        for record in records:
            if ipfield in record and record[ipfield]:
                ip = record[ipfield]
                try:
                    if GEOIP_LIB == 'geoip2':
                        resp = reader.city(ip)
                        location_data = extract_geoip2_data(resp)
                    else:
                        resp = reader.get(ip)
                        location_data = extract_maxminddb_data(resp)
                    
                    record = populate_record_with_location_data(record, location_data, selected_fields)
                except Exception as e:
                    logger.error("Error looking up ip %s: %s", ip, e)
                    empty_data = create_empty_location_data()
                    record = populate_record_with_location_data(
                        record, empty_data, selected_fields, f"Error looking up ip {ip}: {e}"
                    )
            else:
                empty_data = create_empty_location_data()
                record = populate_record_with_location_data(
                    record, empty_data, selected_fields, "No ip address found in record"
                )
            
            yield record
            
        if GEOIP_LIB == 'geoip2':
            reader.close()
        else:
            reader.close()

dispatch(SpurIPLocation, sys.argv, sys.stdin, sys.stdout, __name__) 