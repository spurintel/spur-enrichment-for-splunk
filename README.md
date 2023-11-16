# Spur Splunk App
Enhance your Splunk experience with the Spur Enrichment for Splunk App. This application integrates with Spur products, providing you with enriched data and insights right in your Splunk environment. Generate events based on IP inputs, enrich existing events with data from the Spur Context API, and insert feed data into a Splunk index with our modular input feature.

The Spur Splunk App requires an active Spur subscription and specific user privileges for installation. 

Once installed, you can utilize our search commands and modular input features to generate and enrich your data. 

Get the most out of your data with the Spur Splunk App. Download today and start exploring your data in new ways.

## Pre-requisites
1. In order to use this application you must have an active Spur Subscription. You will need to input your token during the app setup. 
2. App install user needs "admin_all_objects" privilege and Splunk search users need "list_storage_passwords" privilege.

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

### Search Commands
#### Generating command
This command generates an event based an on input ip. It uses the Spur Context API so you must have an active Spur subscription. The command takes 1 argument 'ip' which is the ip that will be passed to the context api.

##### Examples
Single IP:
```
| spurcontextapigen ip="1.1.1.1"
```

Multiple IPs:
```
| spurcontextapigen ip="1.1.1.1,8.8.8.8"
```

#### Streaming command
This command enriches existing events with data from the Spur Context API. It uses the Spur Context API so you must have an active Spur subscription. The command takes 1 argument 'ip_field' which is the field that contains the ip that will be passed to the context api.

##### Examples
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

### Modular Input (Feed integration)
The modular input allows you to insert feed data into a splunk index. It uses the Spur Feed API so you must have an active Spur subscription. The modular input takes 1 argument 'feed_type'. The feed type is the type of feed you want to pull from the Spur API and depends on your subscription level (anonymous, anonymou-residential, realtime). During setup you can override the splunk defaults to insert into a different index. You can also utilize the interval setting to ensure the feed is ingested at your desired interval. 

#### Setup
1. Setup a new data input. Settings -> Data Inputs
3. Select "Spur Feed"
4. Click the new button
5. Give the input a name
6. Input your feed type
7. Check 'More Settings' to configure the details of the input. This is optional but is recommended if you want to override the default index and specify an interval.
9. Click next
10. Depending on your interval settings data may begin ingesting right away. Depending on the feed type it can take several minutes to ingest all the data.


NOTE: You can monitor the progress of the feed by looking at the logs. The logs are logged locally to /opt/splunk/var/log/splunk/spurcontextapi.log. This can be viewed directly or added to splunk as a data input.

#### Examples
```
index="spur" earliest_time=@d | head 1000
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
