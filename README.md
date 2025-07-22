# Spur Enrichment For Splunk
Enhance your Splunk experience with the Spur Enrichment for Splunk App. This application integrates with Spur products, providing you with enriched data and insights right in your Splunk environment. Generate events based on IP inputs, enrich existing events with data from the Spur Context API, and insert feed data into a Splunk index with our modular input feature.

The Spur Splunk App requires an active Spur subscription and specific user privileges for installation. 

Once installed, you can utilize our search commands and modular input features to generate and enrich your data. 

Get the most out of your data with the Spur Splunk App. Download today and start exploring your data in new ways.

## Pre-requisites
1. In order to use this application you must have an active Spur Subscription. You will need to input your token during the app setup. 
2. App install user needs "admin_all_objects" privilege and Splunk search users need "list_storage_passwords" and "list_settings" privileges.

## Installation
### Manual installation
1. Download the application file from the github releases page: https://github.com/spurintel/spur-splunk/releases
2. From splunk click on Apps -> Manage Apps
3. Click 'Install app from file'
4. Upload the compressed file
5. Complete the app setup (requires a Spur API token)

### Splunkbase installation
1. Download the application file from splunkbase: https://splunkbase.splunk.com/app/7126
2. From splunk click on Apps -> Manage Apps
3. Click 'Install app from file'
4. Upload the compressed file
5. Complete the app setup (requires a Spur API token)

### Install from splunk app store
1. From splunk click on Apps -> Find more apps online
2. Search for 'Spur'
3. Click 'Install'
4. Complete the app setup (requires a Spur API token)

## Search Commands
### Generating command
This command generates an event based an on input ip. It uses the Spur Context API so you must have an active Spur subscription. The command takes 1 argument 'ip' which is the ip that will be passed to the context api.

#### Examples
Single IP:
```
| spurcontextapigen ip="1.1.1.1"
```

Multiple IPs:
```
| spurcontextapigen ip="1.1.1.1,8.8.8.8"
```

### Streaming command
This command enriches existing events with data from the Spur Context API. It uses the Spur Context API so you must have an active Spur subscription. The command takes 1 argument 'ip_field' which is the field that contains the ip that will be passed to the context api.

#### Examples
NOTE: This assumes you have uploaded the splunk tutorial data: https://docs.splunk.com/Documentation/Splunk/9.1.1/SearchTutorial/GetthetutorialdataintoSplunk

Simple example:
```
| makeresults
| eval ip = "1.1.1.1"
| spurcontextapi ip_field="ip"
```

Basic IP Query:
```
clientip="223.205.219.67" | spurcontextapi ip_field="clientip"
```

Enrich a list of distinct IPs:
```
clientip=* | head 1000 | stats values(clientip) as "ip" | mvexpand ip | spurcontextapi ip_field="ip"
```

## Modular Input (Feed integration)
The modular input allows you to insert feed data into a splunk index. It uses the Spur Feed API so you must have an active Spur subscription. The modular input takes 2 arguments: 'Feed Type', 'Enable Checkpoint Files'. The feed type is the type of feed you want to pull from the Spur API and depends on your subscription level (anonymous, anonymou-residential, realtime). The enable checkpoint files option will ensure that the same feed file will not be processed multiple times. During setup you can override the splunk defaults to insert into a different index. You can also utilize the interval setting to ensure the feed is ingested at your desired interval. 

### Setup
1. Setup a new data input. Settings -> Data Inputs
2. Select "Spur Feed"
3. Click the new button
4. Give the input a name
5. Input your feed type
6. Enable checkpointing if needed. This is recommended for large daily feeds with an interval defined, it will be ignored for realtime.
7. Check 'More Settings' to configure the details of the input. This is optional but is recommended if you want to override the default index and specify an interval.
8. Click next
9. Depending on your interval settings data may begin ingesting right away. Depending on the feed type it can take several minutes to ingest all the data.


NOTE: You can monitor the progress of the feed by looking at the logs. The logs are logged locally to /opt/splunk/var/log/splunk/spur.log. This can be viewed directly or added to splunk as a data input.

### Examples
```
index="spur" earliest_time=@d | head 1000
```

## IP Geo

### Using Spur IP Geo with built in 'iplocation' command

You can enhance Splunk's built-in `iplocation` command by replacing the default IP geolocation database with Spur's more accurate and comprehensive IP geolocation data. This allows you to leverage Spur's superior IP intelligence while using Splunk's native `iplocation` command syntax.

#### Setup

1. **Download the Spur IP Geo database**: Download the latest version of the Spur IP geolocation database from:
   ```
   https://feeds.spur.us/v2/ipgeo/latest.mmdb
   ```

2. **Replace the default database using Splunk Web Interface** (Recommended):
   - Navigate to **Settings > Lookups > GeoIP lookups file**
   - Click **Choose File** and select the downloaded Spur `.mmdb` file
   - Click **Save** to upload and replace the existing GeoIP database
   - Splunk will automatically restart the necessary services

   **Alternative - Manual file replacement**:
   - Copy the downloaded `.mmdb` file to your Splunk installation directory:
     - Default location: `$SPLUNK_HOME/share/GeoLite2-City.mmdb`
     - Or configure a custom path using the `db_path` setting in `limits.conf`
   - Restart your Splunk instance to load the new database file

#### Configuration Options

To use a custom file path or name, add the following to your `limits.conf` file:

```
[iplocation]
db_path = /path/to/your/spur-ipgeo.mmdb
```

For distributed deployments, ensure the `.mmdb` file is deployed to all indexers as it's not automatically included in the knowledge bundle.

#### Example Usage

Test the enhanced IP geolocation with a simple example:

```
| makeresults 
| eval ip="8.8.8.8" 
| iplocation ip
```

This will return enhanced location data powered by Spur's IP intelligence, including more accurate city, country, region, latitude, and longitude information.

### Spur IP Geo modular input

The Spur IP Geo modular input allows you to automatically ingest IP geolocation data into a locally stored mmdb. You must have an active Spur subscription with access to the IP Geo feed. 

#### Setup
1. Setup a new data input. Settings -> Data Inputs
2. Select "Spur Feed"
3. Click the new button
4. Give the input a name
5. Input `ipgeo` as your feed type
7. Check 'More Settings' to configure the details of the input. This is optional but is recommended if you want to specify an interval for weekly downloads.
8. Click next
9. Depending on your interval settings data may begin ingesting right away.

### Spur IP Location Command

The app includes a `spuriplocation` command that enriches events with comprehensive IP geolocation data from the Spur IP Geo MMDB. This command can be used as an enhanced replacement for Splunk's built-in `iplocation` command, providing more detailed geographic and network information.

**Prerequisites**: This command depends on the Spur IP Geo modular input. Please configure the IP Geo feed input first before using this command.

#### Basic Usage

```
| makeresults 
| eval ip="1.1.1.1" 
| spuriplocation ip_field=ip
```

#### Options

- `ip_field` (required): The field containing the IP address to look up
- `fields` (optional): Comma-separated list of fields to include in the output. If not specified, all fields are included.

#### Available Fields

The `spuriplocation` command supports the following fields. You can use either the short field names or full field names when specifying the `fields` option:

| Short Name | Full Field Name | Description |
|------------|-----------------|-------------|
| `country` | `spur_location_country` | Country name (English) |
| `country_iso` | `spur_location_country_iso` | ISO country code (e.g., "US") |
| `country_geoname_id` | `spur_location_country_geoname_id` | GeoNames database ID for country |
| `subdivision` | `spur_location_subdivision` | State/province name (English) |
| `subdivision_geoname_id` | `spur_location_subdivision_geoname_id` | GeoNames database ID for subdivision |
| `city` | `spur_location_city` | City name (English) |
| `city_geoname_id` | `spur_location_city_geoname_id` | GeoNames database ID for city |
| `continent` | `spur_location_continent` | Continent name (English) |
| `continent_code` | `spur_location_continent_code` | Continent code (e.g., "NA") |
| `continent_geoname_id` | `spur_location_continent_geoname_id` | GeoNames database ID for continent |
| `registered_country` | `spur_location_registered_country` | Registered country name (English) |
| `registered_country_iso` | `spur_location_registered_country_iso` | Registered country ISO code |
| `registered_country_geoname_id` | `spur_location_registered_country_geoname_id` | GeoNames ID for registered country |
| `latitude` | `spur_location_latitude` | Latitude coordinate |
| `longitude` | `spur_location_longitude` | Longitude coordinate |
| `accuracy_radius` | `spur_location_accuracy_radius` | Accuracy radius in kilometers |
| `timezone` | `spur_location_timezone` | Timezone (e.g., "America/Chicago") |
| `as_number` | `spur_as_number` | Autonomous System number |
| `as_organization` | `spur_as_organization` | Autonomous System organization name |
| `error` | `spur_error` | Error message (if any) |

#### Usage Examples

**Basic IP lookup with all fields:**
```
| makeresults 
| eval ip="8.8.8.8" 
| spuriplocation ip_field=ip
```

**Get only basic location information:**
```
| makeresults 
| eval ip="8.8.8.8" 
| spuriplocation ip_field=ip fields="country,subdivision,city"
```

**Get coordinates only:**
```
| makeresults 
| eval ip="8.8.8.8" 
| spuriplocation ip_field=ip fields="latitude,longitude"
```

**Get network information:**
```
| makeresults 
| eval ip="8.8.8.8" 
| spuriplocation ip_field=ip fields="as_number,as_organization"
```

**Enrich existing log data:**
```
index=web_logs 
| head 1000 
| spuriplocation ip_field=client_ip fields="country,city,latitude,longitude"
```

**Get detailed country information with IDs:**
```
| makeresults 
| eval ip="8.8.8.8" 
| spuriplocation ip_field=ip fields="country,country_iso,country_geoname_id"
```

**Mixed field specification (short and full names):**
```
| makeresults 
| eval ip="8.8.8.8" 
| spuriplocation ip_field=ip fields="country,spur_location_latitude,as_number"
```

## Schema

### Search Commands
The following fields are returned from the context api and added to the steamed records:
```
"spur_as_number"
"spur_as_organization"
"spur_organization"
"spur_infrastructure"
"spur_client_behaviors"
"spur_client_concentration_country"
"spur_client_concentration_city"
"spur_client_concentration_geohash"
"spur_client_concentration_density"
"spur_client_concentration_skew"
"spur_client_countries"
"spur_client_spread"
"spur_client_proxies"
"spur_client_count"
"spur_client_types"
"spur_location_country"
"spur_location_state"
"spur_location_city"
"spur_services"
"spur_tunnels_type"
"spur_tunnels_anonymous"
"spur_tunnels_operator"
"spur_risks"
```

### Feed
The records from the feed are inserted with no modifications. The adhere to the following JSON schema:

```
{
  "type": "object",
  "description": "IP Context Object",
  "additionalProperties": false,
  "properties": {
    "ip": {
      "type": "string"
    },
    "as": {
      "type": "object",
      "properties": {
        "number": {
          "type": "integer"
        },
        "organization": {
          "type": "string"
        }
      }
    },
    "organization": {
      "type": "string"
    },
    "infrastructure": {
      "type": "string"
    },
    "client": {
      "type": "object",
      "properties": {
        "behaviors": {
          "type": "array",
          "uniqueItems": true,
          "items": {
            "type": "string"
          }
        },
        "concentration": {
          "type": "object",
          "properties": {
            "country": {
              "type": "string"
            },
            "state": {
              "type": "string"
            },
            "city": {
              "type": "string"
            },
            "geohash": {
              "type": "string"
            },
            "density": {
              "type": "number",
              "minimum": 0,
              "maximum": 1
            },
            "skew": {
              "type": "integer"
            }
          }
        },
        "countries": {
          "type": "integer"
        },
        "spread": {
          "type": "integer"
        },
        "proxies": {
          "type": "array",
          "uniqueItems": true,
          "items": {
            "type": "string"
          }
        },
        "count": {
          "type": "integer"
        },
        "types": {
          "type": "array",
          "uniqueItems": true,
          "items": {
            "type": "string"
          }
        }
      }
    },
    "location": {
      "type": "object",
      "properties": {
        "country": {
          "type": "string"
        },
        "state": {
          "type": "string"
        },
        "city": {
          "type": "string"
        }
      }
    },
    "services": {
      "type": "array",
      "items": {
        "type": "string"
      }
    },
    "tunnels": {
      "type": "array",
      "uniqueItems": true,
      "items": {
        "type": "object",
        "properties": {
          "anonymous": {
            "type": "boolean"
          },
          "entries": {
            "type": "array",
            "uniqueItems": true,
            "items": {
              "type": "string"
            }
          },
          "operator": {
            "type": "string"
          },
          "type": {
            "type": "string"
          },
          "exits": {
            "type": "array",
            "uniqueItems": true,
            "items": {
              "type": "string"
            }
          }
        },
        "required": ["type"]
      }
    },
    "risks": {
      "type": "array",
      "uniqueItems": true,
      "items": {
        "type": "string"
      }
    }
  },
  "required": ["ip"]
}
```
