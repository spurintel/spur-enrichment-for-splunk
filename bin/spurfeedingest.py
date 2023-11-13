import os
import time
import sys
import urllib.request
import json
import gzip

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "splunklib"))
from splunklib.modularinput import *

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "spurlib"))
from spurlib.logging import setup_logging
from spurlib.secrets import get_encrypted_context_api_token


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
            raise ValueError(f"feed_type must be one of 'anonymous, anonymous-residential, 'realtime'; found {feed_type}")

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
                raise ValueError("No token found")

            # Get fields from the InputDefinition object
            feed_type = input_item["feed_type"]
            if feed_type not in ["anonymous", "anonymous-residential", "realtime"]:
                raise ValueError(f"feed_type must be one of 'anonymous, anonymous-residential, 'realtime'; found {feed_type}")

            # Get the checkpoint directory out of the modular input's metadata
            checkpoint_dir = inputs.metadata["checkpoint_dir"]
            date = time.strftime("%Y%m%d")
            checkpoint_file_path = os.path.join(checkpoint_dir, feed_type + "_" + date + ".txt")
            checkpoint_file_new_contents = ""

            # Set the temporary contents of the checkpoint file to an empty string
            checkpoint_file_contents = ""

            try:
                # read sha values from file, if exist
                with open(checkpoint_file_path, 'r') as file:
                    checkpoint_file_contents = file.read()
            except:
                # If there's an exception, assume the file doesn't exist
                # Create the checkpoint file with an empty string
                with open(checkpoint_file_path, "a") as file:
                    file.write(checkpoint_file_contents + "\n")

            # If the file exists, check if the current date is in the file
            if date in checkpoint_file_contents:
                logger.info("Date %s found in checkpoint file %s", date, checkpoint_file_path)
                # If the date is in the file, assume we've already processed the feed for today
                # and exit
                logger.info("Already processed feed for today, doing nothing")
                return
            
            # Process the feed
            url = "/".join(["https://feeds.spur.us/v2", feed_type, "latest.json.gz"])
            h = {"TOKEN": token, "Accept": "application/json"}
            logger.info("Headers: %s", h)
            req = urllib.request.Request(url, headers=h)
            logger.info("Requesting %s", url)
            written = 0
            with urllib.request.urlopen(req) as response:
                if response.status != 200:
                    logger.error("Error reading feed: %s", response.status)
                    raise Exception("Error reading feed")
                with gzip.GzipFile(fileobj=response) as f:
                    for line in f:
                        try:
                            data = json.loads(line.decode("utf-8"))
                            event = Event()
                            event.stanza = input_name
                            event.sourceType = "spur_feed"
                            event.time = time.time()
                            event.data = json.dumps(data)
                            ew.write_event(event)
                            written += 1

                            if written % 1000 == 0:
                                logger.info("Wrote %s events", written)
                        except Exception as e:
                            logger.error("Error processing line: %s", e)

                # If we get here, we've successfully processed the feed, write out the date to the checkpoint file
                checkpoint_file_new_contents =  date + "\n"
                logger.info("Wrote %s events", written)
                logger.info("Writing checkpoint file %s", checkpoint_file_path)
                with open(checkpoint_file_path, "w") as file:
                    file.write(checkpoint_file_new_contents)

if __name__ == "__main__":
    sys.exit(SpurFeed().run(sys.argv))
