import os
import sys
import json
import gzip
import requests
import time
from datetime import datetime, timezone

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "splunklib"))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "spurlib"))
from spurlib.api import get_proxy_settings
from spurlib.secrets import get_encrypted_context_api_token
from spurlib.logging import setup_logging
from spurlib.notify import notify_feed_failure, notify_feed_success
from splunklib.modularinput import *


def write_checkpoint(checkpoint_file_path, checkpoint_file_new_contents):
    """
    Writes the checkpoint file to disk.

    Args:
      checkpoint_file_path (str): The path to the checkpoint file.
      checkpoint_file_new_contents (str): The new contents of the checkpoint file.
    """
    with open(checkpoint_file_path, "w") as file:
        file.write(checkpoint_file_new_contents)


def get_feed_metadata(logger, proxy_handler_config, token, feed_type):
    """
    Get the latest feed metadata from the Spur API. https://feeds.spur.us/v2/{feed_type}/latest.
    The metadata is returned in JSON format:
    {"json": {"location": "20231117/feed.json.gz", "date": "20231117", "generated_at": "2023-11-17T04:02:12Z", "available_at": "2023-11-17T04:02:19Z"}}
    """
    url = "/".join(["https://feeds.spur.us/v2", feed_type, "latest"])
    logger.debug("Requesting %s", url)
    h = {"TOKEN": token}
    resp = requests.get(url, headers=h, proxies=proxy_handler_config)
    logger.debug("Got feed metadata response with http status %s", resp.status_code)
    parsed = resp.json()
    logger.debug("Got feed metadata: %s", parsed)
    return parsed['json']


def get_feed_response(logger, proxy_handler_config, token, feed_type, feed_metadata):
    """
    Get the latest feed from the Spur API. https://feeds.spur.us/v2/{feed_type}/{feed_metadata['location']}.
    This returns the response object so that the caller can process the feed line by line.
    Be sure to use gzip.GzipFile to decompress the response and close the file when you're done.
    """
    location = feed_metadata['location']
    if "realtime" in location:
        location   = location.replace("realtime/", "")
    url = "/".join(["https://feeds.spur.us/v2", feed_type, location])
    logger.debug("Requesting %s", url)
    h = {"TOKEN": token}
    return requests.get(url, headers=h, proxies=proxy_handler_config, stream=True)


def get_checkpoint(logger, checkpoint_file_path, checkpoints_enabled):
    if not checkpoints_enabled:
        return {}

    checkpoint_file_contents = ""
    try:
        # read sha values from file, if exist
        with open(checkpoint_file_path, 'r') as file:
            checkpoint_file_contents = file.read()
    except:
        return {}

    checkpoint = json.loads(checkpoint_file_contents)
    logger.debug("checkpoint '%s' found in checkpoint file %s",
                checkpoint_file_contents, checkpoint_file_path)
    return checkpoint


def process_feed(ctx, logger, token, feed_type, input_name, ew, checkpoint_file_path, checkpoints_enabled):
    if feed_type == "anonymous-residential/realtime":
        checkpoints_enabled = False

    proxy_handler_config = get_proxy_settings(ctx, logger)
    logger.debug("proxy_handler_config: %s", proxy_handler_config)

    # Get the feed metadata
    try:
        feed_metadata = get_feed_metadata(logger, proxy_handler_config, token, feed_type)
    except Exception as e:
        notify_feed_failure(ctx, "Error getting spur %s feed metadata" % feed_type)
        logger.error("Error getting feed metadata: %s", e)
        raise e

    # Get the latest checkpoint
    logger.debug("checkpoint_file_path: %s", checkpoint_file_path)
    checkpoint = get_checkpoint(logger, checkpoint_file_path, checkpoints_enabled)

    # If we have a checkpoint check to see if we have already processed the feed for today or we need to start from the offset in the file
    start_offset = 0
    today = datetime.now(timezone.utc).strftime("%Y%m%d")
    if checkpoints_enabled:
        if 'completed_date' in checkpoint and checkpoint['completed_date'] == today:
            # If the current date is in the file, we've already processed the feed for today
            logger.debug("Already processed feed for today, doing nothing")
            return
        elif 'last_touched_date' in checkpoint and checkpoint['last_touched_date'] == today:
            # If the current date is not in the file, we need to start from the offset in the file
            logger.debug("Starting from offset %s", checkpoint['offset'])
            start_offset = checkpoint['offset']
        else:
            logger.debug("Checkpoint found, but not for today")
    else:
        logger.debug("No checkpoint found, starting from offset 0")

    # If the latest feed location hasn't changed yet, we don't need to process the feed
    if 'feed_metadata'in checkpoint:
        logger.debug("Checkpoint file found, checking if feed location has changed")
        if 'location' in checkpoint['feed_metadata']:
            logger.debug("Found previous feed location: %s", checkpoint['feed_metadata']['location'])
            if feed_metadata['location']:
                logger.debug("Found current feed location: %s", feed_metadata['location'])
                if checkpoint['feed_metadata']['location'] == feed_metadata['location'] and checkpoints_enabled:
                    logger.debug("Feed location hasn't changed, doing nothing")
                    return

    # Process the feed
    logger.debug("Attempting to retrieve feed with feed metadata: %s", feed_metadata)
    processed = 0
    try:
        response = get_feed_response(logger, proxy_handler_config, token, feed_type, feed_metadata)
        logger.debug("Got feed response")
        checkpoint = {
            "offset": 0,
            "start_time": time.time(),
            "end_time": None,
            "completed_date": None,
            "last_touched_date": today,
            "feed_metadata": feed_metadata,
        }
        if checkpoints_enabled:
            write_checkpoint(checkpoint_file_path, json.dumps(checkpoint))
        feed_generation_date = response.headers.get("x-feed-generation-date")
        checkpoint["feed_generation_date"] = feed_generation_date
        logger.debug("Feed generation date: %s", feed_generation_date)
        with gzip.GzipFile(fileobj=response.raw) as f:
            for line in f:
                try:
                    data = json.loads(line.decode("utf-8"))
                    event = Event()
                    event.stanza = input_name
                    event.sourceType = "spur_feed"
                    event.time = time.time()
                    event.data = json.dumps(data)
                    processed += 1

                    if processed < start_offset:
                        continue
                    ew.write_event(event)
                    checkpoint["offset"] = processed

                    if processed % 10000 == 0:
                        logger.debug("Wrote %s events", processed)
                        if checkpoints_enabled:
                            write_checkpoint(
                                checkpoint_file_path, json.dumps(checkpoint))
                except Exception as e:
                    logger.error("Error processing line: %s", e)
        response.close()
        checkpoint["offset"] = processed
    except Exception as e:
        checkpoint["offset"] = processed
        if checkpoints_enabled:
            write_checkpoint(checkpoint_file_path,
                                json.dumps(checkpoint))
        logger.error("Error processing feed: %s", e)
        notify_feed_failure(ctx, "Error processing spur %s feed: %s" % (feed_type, e))
        raise e

    # If we get here, we've successfully processed the feed, write out the date to the checkpoint file
    checkpoint["end_time"] = time.time()
    checkpoint["completed_date"] = today
    checkpoint_file_new_contents = json.dumps(checkpoint)
    logger.info("Wrote %s events", processed)
    if "realtime" not in feed_type:
        notify_feed_success(ctx, processed)
    if checkpoints_enabled:
        logger.debug("Writing checkpoint file %s", checkpoint_file_path)
        write_checkpoint(checkpoint_file_path,
                            checkpoint_file_new_contents)


class SpurFeed(Script):
    """ 
    Modular input that downloads the latest spur feed and indexes it into Splunk.
    """

    def get_scheme(self):
        """When Splunk starts, it looks for all the modular inputs defined by
        its configuration, and tries to run them with the argument --scheme.
        Splunkd expects the modular inputs to print a description of the
        input in XML on stdout. The modular input framework takes care of all
        the details of formatting XML and printing it. The user need only
        override get_scheme and return a new Scheme object.

        :return: scheme, a Scheme object
        """
        scheme = Scheme("Spur Feed")
        scheme.description = "Downloads the latest spur feed and indexes it into Splunk."
        scheme.use_external_validation = True

        feed_type_argument = Argument("feed_type")
        feed_type_argument.title = "Feed Type"
        feed_type_argument.data_type = Argument.data_type_string
        feed_type_argument.description = "The type of feed to download. Must be one of 'anonymous, anonymous-ipv6, anonymous-residential, anonymous-residential-ipv6, anonymous-residential/realtime'"
        feed_type_argument.required_on_create = True
        feed_type_argument.required_on_edit = True
        scheme.add_argument(feed_type_argument)

        # Checkpoint settings
        checkpoint_argument = Argument("enable_checkpoint")
        checkpoint_argument.title = "Enable Checkpoint Files"
        checkpoint_argument.data_type = Argument.data_type_boolean
        checkpoint_argument.description = "Write out a checkpoint file to make sure the same feed isn't ingested twice."
        checkpoint_argument.required_on_create = True
        checkpoint_argument.required_on_edit = True
        scheme.add_argument(checkpoint_argument)

        return scheme

    def validate_input(self, definition):
        """When using external validation, after splunkd calls the modular input with
        --scheme to get a scheme, it calls it again with --validate-arguments for
        each instance of the modular input in its configuration files, feeding XML
        on stdin to the modular input to do validation. It is called the same way
        whenever a modular input's configuration is edited.

        :param validation_definition: a ValidationDefinition object
        """
        feed_type = definition.parameters["feed_type"]
        if feed_type not in ["anonymous", "anonymous-ipv6", "anonymous-residential", "anonymous-residential-ipv6", "anonymous-residential/realtime"]:
            raise ValueError(
                f"feed_type must be one of 'anonymous, anonymous-ipv6, anonymous-residential, anonymous-residential-ipv6, anonymous-residential/realtime'; found {feed_type}")

    def stream_events(self, inputs, ew):
        """This function handles all the action: splunk calls this modular input
        without arguments, streams XML describing the inputs to stdin, and waits
        for XML on stdout describing events.

        If you set use_single_instance to True on the scheme in get_scheme, it
        will pass all the instances of this input to a single instance of this
        script.

        :param inputs: an InputDefinition object
        :param event_writer: an EventWriter object
        """

        logger = setup_logging()

        # Go through each input for this modular input
        for input_name, input_item in list(inputs.inputs.items()):
            logger.info("Starting spur feed ingest")
            token = get_encrypted_context_api_token(self)
            if token is None or token == "":
                notify_feed_failure(self, "No token found")
                raise ValueError("No token found")

            # Get fields from the InputDefinition object
            feed_type = input_item["feed_type"]
            if feed_type not in ["anonymous", "anonymous-ipv6", "anonymous-residential", "anonymous-residential-ipv6", "anonymous-residential/realtime"]:
                notify_feed_failure(
                    self, f"feed_type must be one of 'anonymous, anonymous-ipv6, anonymous-residential, anonymous-residential-ipv6, anonymous-residential/realtime'; found {feed_type}")
                raise ValueError(
                    f"feed_type must be one of 'anonymous, anonymous-ipv6, anonymous-residential, anonymous-residential-ipv6, anonymous-residential/realtime'; found {feed_type}")
            logger.debug("feed_type: %s", feed_type)

            checkpoints_enabled = bool(int(input_item["enable_checkpoint"]))
            logger.debug("checkpoints_enabled: %s", checkpoints_enabled)

            checkpoint_dir = inputs.metadata["checkpoint_dir"]
            checkpoint_file_path = os.path.join(checkpoint_dir, feed_type + ".txt")
            logger.debug("checkpoint_file_path: %s", checkpoint_file_path)

            try:
                process_feed(self, logger, token, feed_type, input_name, ew, checkpoint_file_path, checkpoints_enabled)
            except Exception as e:
                logger.error("Error processing feed: %s", e)
                notify_feed_failure(self, "Error processing spur %s feed: %s" % (feed_type, e))
                raise e


if __name__ == "__main__":
    sys.exit(SpurFeed().run(sys.argv))
