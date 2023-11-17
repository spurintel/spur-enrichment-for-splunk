import os
import time
import sys
import urllib.request
import json
import gzip

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "splunklib"))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "spurlib"))
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


def get_feed_metadata(logger, token, feed_type):
    """
    Get the latest feed metadata from the Spur API. https://feeds.spur.us/v2/{feed_type}/latest.
    The metadata is returned in JSON format:
    {"json": {"location": "20231117/feed.json.gz", "date": "20231117", "generated_at": "2023-11-17T04:02:12Z", "available_at": "2023-11-17T04:02:19Z"}}
    """
    url = "/".join(["https://feeds.spur.us/v2", feed_type, "latest"])
    logger.info("Requesting %s", url)
    req = urllib.request.Request(url, headers={"TOKEN": token})
    resp = urllib.request.urlopen(req)
    logger.info("Got feed metadata response with http status %s", resp.status)
    body = resp.read().decode("utf-8")
    parsed = json.loads(body)
    logger.info("Got feed metadata: %s", parsed)
    return parsed['json']


def get_feed_response(logger, token, feed_type, feed_metadata):
    """
    Get the latest feed from the Spur API. https://feeds.spur.us/v2/{feed_type}/{feed_metadata['location']}.
    This returns the response object so that the caller can process the feed line by line.
    Be sure to use gzip.GzipFile to decompress the response and close the file when you're done.
    """
    url = "/".join(["https://feeds.spur.us/v2", feed_type, feed_metadata['location']])
    logger.info("Requesting %s", url)
    req = urllib.request.Request(url, headers={"TOKEN": token})
    return urllib.request.urlopen(req)


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
    logger.info("checkpoint '%s' found in checkpoint file %s",
                checkpoint_file_contents, checkpoint_file_path)
    return checkpoint

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
        feed_type_argument.description = "The type of feed to download. Must be one of 'anonymous, anonymous-residential, 'realtime'"
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
        if feed_type not in ["anonymous", "anonymous-residential", "realtime"]:
            raise ValueError(
                f"feed_type must be one of 'anonymous, anonymous-residential, 'realtime'; found {feed_type}")

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
            if feed_type not in ["anonymous", "anonymous-residential", "realtime"]:
                notify_feed_failure(
                    self, f"feed_type must be one of 'anonymous, anonymous-residential, 'realtime'; found {feed_type}")
                raise ValueError(
                    f"feed_type must be one of 'anonymous, anonymous-residential, 'realtime'; found {feed_type}")
            logger.info("feed_type: %s", feed_type)
            checkpoints_enabled = bool(int(input_item["enable_checkpoint"]))
            logger.info("checkpoints_enabled: %s", checkpoints_enabled)

            if feed_type == "realtime":
                checkpoints_enabled = False

            # Get the feed metadata
            try:
                feed_metadata = get_feed_metadata(logger, token, feed_type)
            except Exception as e:
                notify_feed_failure(self, "Error getting spur %s feed metadata" % feed_type)
                logger.error("Error getting feed metadata: %s", e)
                raise e

            # Get the latest checkpoint
            checkpoint_dir = inputs.metadata["checkpoint_dir"]
            checkpoint_file_path = os.path.join(checkpoint_dir, feed_type + "_" + ".txt")
            logger.info("checkpoint_file_path: %s", checkpoint_file_path)
            checkpoint = get_checkpoint(logger, checkpoint_file_path, checkpoints_enabled)

            # If we have a checkpoint check to see if we have already processed the feed for today or we need to start from the offset in the file
            start_offset = 0
            if checkpoints_enabled:
                today = time.strftime("%Y%m%d")
                if checkpoint['completed_date'] == today:
                    # If the current date is in the file, we've already processed the feed for today
                    logger.info("Already processed feed for today, doing nothing")
                    return
                elif checkpoint['last_touched_date'] == today:
                    # If the current date is not in the file, we need to start from the offset in the file
                    logger.info("Starting from offset %s", checkpoint['offset'])
                    start_offset = checkpoint['offset']
                else:
                    logger.info("Checkpoint found, but not for today")
            else:
                logger.info("No checkpoint found, starting from offset 0")

            # If the latest feed location hasn't changed yet, we don't need to process the feed
            if 'feed_metadata'in checkpoint:
                logger.info("Checkpoint file found, checking if feed location has changed")
                if 'location' in checkpoint['feed_metadata']:
                    logger.info("Found previous feed location: %s", checkpoint['feed_metadata']['location'])
                    if feed_metadata['location']:
                        logger.info("Found current feed location: %s", feed_metadata['location'])
                        if checkpoint['feed_metadata']['location'] == feed_metadata['location'] and checkpoints_enabled:
                            logger.info("Feed location hasn't changed, doing nothing")
                            return

            # Process the feed
            logger.info("Attempting to retrieve feed with feed metadata: %s", feed_metadata)
            try:
                response = get_feed_response(logger, token, feed_type, feed_metadata)
                logger.info("Got feed response")
                processed = 0
                checkpoint = {
                    "offset": 0,
                    "start_time": time.time(),
                    "end_time": None,
                    "completed_date": None,
                    "last_touched_date": time.strftime("%Y%m%d"),
                    "feed_metadata": feed_metadata,
                }
                write_checkpoint(checkpoint_file_path, json.dumps(checkpoint))
                feed_generation_date = response.getheader(
                    "x-feed-generation-date")
                checkpoint["feed_generation_date"] = feed_generation_date
                logger.info("Feed generation date: %s", feed_generation_date)
                with gzip.GzipFile(fileobj=response) as f:
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
                                logger.info("Wrote %s events", processed)
                                if checkpoints_enabled:
                                    write_checkpoint(
                                        checkpoint_file_path, json.dumps(checkpoint))
                        except Exception as e:
                            logger.error("Error processing line: %s", e)
                response.close()
            except Exception as e:
                checkpoint["offset"] = processed
                if checkpoints_enabled:
                    write_checkpoint(checkpoint_file_path,
                                     json.dumps(checkpoint))
                logger.error("Error processing feed: %s", e)
                notify_feed_failure(self, "Error processing spur %s feed: %s" % (feed_type, e))
                raise e

            # If we get here, we've successfully processed the feed, write out the date to the checkpoint file
            checkpoint["end_time"] = time.time()
            checkpoint["completed_date"] = time.strftime("%Y%m%d")
            checkpoint_file_new_contents = json.dumps(checkpoint)
            logger.info("Wrote %s events", processed)
            logger.info("Writing checkpoint file %s", checkpoint_file_path)
            notify_feed_success(self, processed)            
            if checkpoints_enabled:
                write_checkpoint(checkpoint_file_path,
                                 checkpoint_file_new_contents)


if __name__ == "__main__":
    sys.exit(SpurFeed().run(sys.argv))
