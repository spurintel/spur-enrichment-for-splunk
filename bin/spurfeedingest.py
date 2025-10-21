import os
import sys
import json
import gzip
import requests
import time
import tempfile
import fcntl
from datetime import datetime, timezone

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "splunklib"))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "spurlib"))
from spurlib.api import get_proxy_settings
from spurlib.secrets import get_encrypted_context_api_token
from spurlib.logging import setup_logging
from spurlib.notify import (
    notify_feed_failure,
    notify_feed_success,
    notify_geo_feed_success,
)
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


def get_lock_file_path(checkpoint_dir, feed_type):
    """
    Generate lock file path for a given feed type.
    
    Args:
        checkpoint_dir: Directory for lock files
        feed_type: Type of feed
        
    Returns:
        str: Path to lock file
    """
    safe_feed_type = feed_type.replace("/", "_").replace("\\", "_")
    lock_filename = f"{safe_feed_type}.lock"
    return os.path.join(checkpoint_dir, lock_filename)


def is_lock_stale(lock_file_path, max_age_seconds=86400):
    """
    Check if a lock file is stale (older than max_age_seconds).
    
    Args:
        lock_file_path: Path to the lock file
        max_age_seconds: Maximum age in seconds before considering lock stale (default 24 hours)
        
    Returns:
        bool: True if lock is stale or doesn't exist, False otherwise
    """
    if not os.path.exists(lock_file_path):
        return True
    
    try:
        lock_age = time.time() - os.path.getmtime(lock_file_path)
        return lock_age > max_age_seconds
    except Exception:
        return True


def acquire_lock(logger, lock_file_path):
    """
    Acquire a lock for feed processing using file locking.
    Returns a file handle that must be kept open, or None if lock cannot be acquired.
    
    Args:
        logger: Logger instance
        lock_file_path: Path to the lock file
        
    Returns:
        file handle if lock acquired, None otherwise
    """
    try:
        # Ensure the directory exists
        lock_dir = os.path.dirname(lock_file_path)
        if not os.path.exists(lock_dir):
            os.makedirs(lock_dir)
        
        # Open the lock file
        lock_file = open(lock_file_path, 'w')
        
        # Try to acquire an exclusive lock (non-blocking)
        try:
            fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            # Write process info to lock file
            lock_info = {
                "pid": os.getpid(),
                "timestamp": time.time(),
                "iso_time": datetime.now(timezone.utc).isoformat()
            }
            lock_file.write(json.dumps(lock_info))
            lock_file.flush()
            logger.info("Successfully acquired lock: %s", lock_file_path)
            return lock_file
        except IOError:
            # Lock is held by another process
            lock_file.close()
            logger.warning("Could not acquire lock (already held by another process): %s", lock_file_path)
            return None
            
    except Exception as e:
        logger.error("Error acquiring lock: %s", e)
        return None


def release_lock(logger, lock_file_handle, lock_file_path):
    """
    Release a previously acquired lock.
    
    Args:
        logger: Logger instance
        lock_file_handle: File handle returned by acquire_lock
        lock_file_path: Path to the lock file
    """
    if lock_file_handle is None:
        return
    
    try:
        # Release the lock
        fcntl.flock(lock_file_handle.fileno(), fcntl.LOCK_UN)
        lock_file_handle.close()
        
        # Remove the lock file
        if os.path.exists(lock_file_path):
            os.remove(lock_file_path)
        
        logger.info("Successfully released lock: %s", lock_file_path)
    except Exception as e:
        logger.warning("Error releasing lock: %s", e)


def cleanup_stale_lock(logger, lock_file_path, max_age_seconds=86400):
    """
    Remove stale lock files that are older than max_age_seconds.
    
    Args:
        logger: Logger instance
        lock_file_path: Path to the lock file
        max_age_seconds: Maximum age in seconds before considering lock stale (default 24 hours)
        
    Returns:
        bool: True if stale lock was removed, False otherwise
    """
    if is_lock_stale(lock_file_path, max_age_seconds):
        try:
            if os.path.exists(lock_file_path):
                os.remove(lock_file_path)
                logger.info("Removed stale lock file: %s", lock_file_path)
                return True
        except Exception as e:
            logger.warning("Failed to remove stale lock file %s: %s", lock_file_path, e)
    return False


def cleanup_old_checkpoints(logger, checkpoint_dir, feed_type, current_feed_identifier):
    """
    Clean up old checkpoint files for the same feed type but different feed identifiers.
    This prevents accumulation of old checkpoint files and ensures we don't use stale data.
    
    Args:
        logger: Logger instance
        checkpoint_dir: Directory containing checkpoint files
        feed_type: Type of feed (e.g., 'anonymous', 'anonymous-residential')
        current_feed_identifier: Current feed identifier to keep
    """
    if not os.path.exists(checkpoint_dir):
        return
        
    try:
        # Pattern to match old checkpoint files for this feed type
        old_pattern = f"{feed_type}_"
        current_checkpoint_file = f"{feed_type}_{current_feed_identifier}.txt"
        legacy_checkpoint_file = f"{feed_type}.txt"
        
        files_to_remove = []
        
        for filename in os.listdir(checkpoint_dir):
            if filename.startswith(old_pattern) and filename.endswith(".txt"):
                if filename != current_checkpoint_file:
                    files_to_remove.append(filename)
            elif filename == legacy_checkpoint_file:
                # Remove legacy checkpoint files that don't use feed identifier
                files_to_remove.append(filename)
        
        for filename in files_to_remove:
            try:
                file_path = os.path.join(checkpoint_dir, filename)
                os.remove(file_path)
                logger.debug("Cleaned up old checkpoint file: %s", file_path)
            except Exception as e:
                logger.warning("Failed to remove old checkpoint file %s: %s", filename, e)
                
    except Exception as e:
        logger.warning("Error during checkpoint cleanup: %s", e)


def get_checkpoint_file_path(checkpoint_dir, feed_type, feed_identifier):
    """
    Generate checkpoint file path using feed type and feed identifier.
    
    Args:
        checkpoint_dir: Directory for checkpoint files
        feed_type: Type of feed
        feed_identifier: Feed identifier (x-goog-generation)
        
    Returns:
        str: Path to checkpoint file
    """
    # Sanitize feed_identifier to be safe for filesystem
    safe_identifier = feed_identifier.replace("/", "_").replace("\\", "_")
    checkpoint_filename = f"{feed_type}_{safe_identifier}.txt"
    return os.path.join(checkpoint_dir, checkpoint_filename)


def get_feed_metadata(logger, proxy_handler_config, token, feed_type):
    """
    Get the latest feed metadata from the Spur API. https://feeds.spur.us/v2/{feed_type}/latest.
    The metadata is returned in JSON format:
    {"json": {"location": "20231117/feed.json.gz", "date": "20231117", "generated_at": "2023-11-17T04:02:12Z", "available_at": "2023-11-17T04:02:19Z"}}
    """
    url = "/".join(["https://feeds.spur.us/v2", feed_type, "latest"])
    logger.debug("Requesting %s", url)
    h = {"TOKEN": token}
    logger.debug("headers: %s", h)
    resp = requests.get(url, headers=h, proxies=proxy_handler_config)
    logger.debug("Got feed metadata response with http status %s", resp.status_code)
    parsed = resp.json()
    logger.debug("Got feed metadata: %s", parsed)
    return parsed["json"]


def get_feed_metadata_mmdb(logger, proxy_handler_config, token, feed_type):
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
    return parsed["mmdb"]


def get_feed_response(logger, proxy_handler_config, token, feed_type, feed_metadata):
    """
    Get the latest feed from the Spur API. https://feeds.spur.us/v2/{feed_type}/{feed_metadata['location']}.
    This returns the response object so that the caller can process the feed line by line.
    Be sure to use gzip.GzipFile to decompress the response and close the file when you're done.
    """
    location = feed_metadata["location"]
    if "realtime" in location:
        location = location.replace("realtime/", "")
    url = "/".join(["https://feeds.spur.us/v2", feed_type, location])
    logger.debug("Requesting %s", url)
    h = {"TOKEN": token}
    logger.debug("headers: %s", h)
    return requests.get(url, headers=h, proxies=proxy_handler_config, stream=True)


def get_feed_identifier(logger, proxy_handler_config, token, feed_type, feed_metadata):
    """
    Get the feed identifier (x-goog-generation) by making requests to the feed URL.
    First tries HEAD request, then falls back to a range request for just the first byte.
    
    Args:
        logger: Logger instance
        proxy_handler_config: Proxy configuration
        token: API token
        feed_type: Type of feed
        feed_metadata: Feed metadata containing location
        
    Returns:
        str: Feed identifier (x-goog-generation) or "unknown" if not available
    """
    location = feed_metadata["location"]
    if "realtime" in location:
        location = location.replace("realtime/", "")
    url = "/".join(["https://feeds.spur.us/v2", feed_type, location])
    logger.debug("Getting feed identifier from %s", url)
    h = {"TOKEN": token}
    
    # Try HEAD request first
    try:
        response = requests.head(url, headers=h, proxies=proxy_handler_config)
        feed_identifier = response.headers.get("x-goog-generation")
        if feed_identifier:
            logger.info("Feed identifier from HEAD request (x-goog-generation): %s", feed_identifier)
            return feed_identifier
        else:
            logger.info("No x-goog-generation header in HEAD response, trying range request")
    except Exception as e:
        logger.warn("HEAD request failed, trying range request: %s", e)
    
    # Fall back to range request for first byte to get headers
    try:
        h_range = h.copy()
        h_range["Range"] = "bytes=0-0"
        response = requests.get(url, headers=h_range, proxies=proxy_handler_config)
        feed_identifier = response.headers.get("x-goog-generation")
        response.close()
        if feed_identifier:
            logger.info("Feed identifier from range request (x-goog-generation): %s", feed_identifier)
            return feed_identifier
        else:
            logger.warning("No x-goog-generation header found in range request either")
    except Exception as e:
        logger.warning("Range request also failed: %s", e)
    
    logger.warning("Could not get feed identifier, using 'unknown'")
    return "unknown"


def get_checkpoint(logger, checkpoint_file_path, checkpoints_enabled):
    if not checkpoints_enabled:
        return {}

    checkpoint_file_contents = ""
    try:
        # read sha values from file, if exist
        with open(checkpoint_file_path, "r") as file:
            checkpoint_file_contents = file.read()
    except:
        return {}

    checkpoint = json.loads(checkpoint_file_contents)
    logger.debug(
        "checkpoint '%s' found in checkpoint file %s",
        checkpoint_file_contents,
        checkpoint_file_path,
    )
    return checkpoint


def download_feed_to_temp(logger, proxy_handler_config, token, feed_type, feed_metadata):
    """
    Download the feed file to a temporary location using x-goog-generation header for naming.
    Returns a tuple of (file_path, goog_generation).
    """
    logger.info("Downloading feed to temporary file")
    response = get_feed_response(logger, proxy_handler_config, token, feed_type, feed_metadata)
    
    # Get the x-goog-generation header for file naming
    goog_generation = response.headers.get("x-goog-generation", "unknown")
    logger.info("x-goog-generation: %s", goog_generation)
    
    # Create temp file with a name based on x-goog-generation
    temp_dir = tempfile.gettempdir()
    temp_filename = f"spur_feed_{feed_type.replace('/', '_')}_{goog_generation}.gz"
    temp_file_path = os.path.join(temp_dir, temp_filename)
    
    logger.info("Downloading feed to temp file: %s", temp_file_path)
    
    try:
        with open(temp_file_path, "wb") as temp_file:
            for chunk in response.iter_content(chunk_size=8192):
                temp_file.write(chunk)
        response.close()
        logger.info("Successfully downloaded feed to temp file")
        return temp_file_path, goog_generation
    except Exception as e:
        response.close()
        # Clean up partial file if download failed
        if os.path.exists(temp_file_path):
            os.remove(temp_file_path)
        logger.error("Error downloading feed to temp file: %s", e)
        raise e


def process_geo_feed(ctx, logger, token, feed_type, input_name, ew, checkpoint_dir):
    """
    Process the geo feed.
    """
    logger.info("Processing geo feed")
    logger.debug("feed_type: %s", feed_type)
    logger.debug("input_name: %s", input_name)
    logger.debug("ew: %s", ew)
    
    # Get lock file path and attempt to acquire lock
    lock_file_path = get_lock_file_path(checkpoint_dir, feed_type)
    logger.debug("lock_file_path: %s", lock_file_path)
    
    # Clean up stale locks (older than 24 hours)
    cleanup_stale_lock(logger, lock_file_path)
    
    # Try to acquire the lock
    lock_handle = acquire_lock(logger, lock_file_path)
    if lock_handle is None:
        logger.warning("Another instance is already processing feed type '%s', skipping", feed_type)
        return
    
    proxy_handler_config = get_proxy_settings(ctx, logger)
    logger.debug("proxy_handler_config: %s", proxy_handler_config)

    try:
        # Get the feed metadata
        try:
            feed_metadata = get_feed_metadata_mmdb(
                logger, proxy_handler_config, token, feed_type
            )
        except Exception as e:
            import traceback

            error_details = traceback.format_exc()
            notify_feed_failure(ctx, "Error getting spur %s feed metadata" % feed_type)
            logger.error("Error getting feed metadata: %s", e)
            logger.error("Full traceback: %s", error_details)

            # Provide more specific error message
            if "401" in str(e) or "Unauthorized" in str(e):
                raise Exception(
                    f"Invalid API token when getting {feed_type} metadata. Please check your API token configuration."
                )
            elif "403" in str(e) or "Forbidden" in str(e):
                raise Exception(
                    f"Access denied when getting {feed_type} metadata. Please check your API token permissions."
                )
            elif "timeout" in str(e).lower():
                raise Exception(
                    f"Timeout when getting {feed_type} metadata. Please check network connectivity."
                )
            else:
                raise Exception(
                    f"Error getting {feed_type} metadata: {str(e) or type(e).__name__}"
                )

        # Process the feed
        logger.debug("Attempting to retrieve feed with feed metadata: %s", feed_metadata)
        try:
            # Get the application path
            splunk_home = os.environ["SPLUNK_HOME"]
            app_local_path = os.path.join(
                splunk_home, "etc", "apps", "spur-enrichment-for-splunk", "local", "data"
            )
            mmdb_file_path = os.path.join(app_local_path, "mmdb", "ipgeo.mmdb")

            # create the app_local_path if it doesn't exist
            if not os.path.exists(app_local_path):
                os.makedirs(app_local_path)

            # create the mmdb directory if it doesn't exist
            if not os.path.exists(os.path.join(app_local_path, "mmdb")):
                os.makedirs(os.path.join(app_local_path, "mmdb"))

            response = get_feed_response(
                logger, proxy_handler_config, token, feed_type, feed_metadata
            )
            feed_generation_date = response.headers.get("x-feed-generation-date")
            logger.debug("Feed generation date: %s", feed_generation_date)

            # Write the feed to the mmdb file
            with open(mmdb_file_path, "wb") as f:
                f.write(response.raw.read())

            # Make the MMDB file world readable
            os.chmod(mmdb_file_path, 0o644)

            response.close()
        except Exception as e:
            import traceback

            error_details = traceback.format_exc()
            logger.error("Error processing feed: %s", e)
            logger.error("Full traceback: %s", error_details)

            # Provide more specific error message
            if "permission" in str(e).lower() or "access" in str(e).lower():
                detailed_msg = f"Permission error processing {feed_type} feed. Check file permissions for MMDB directory: {str(e)}"
            elif "disk" in str(e).lower() or "space" in str(e).lower():
                detailed_msg = f"Disk space error processing {feed_type} feed: {str(e)}"
            elif "network" in str(e).lower() or "connection" in str(e).lower():
                detailed_msg = f"Network error processing {feed_type} feed: {str(e)}"
            else:
                detailed_msg = (
                    f"Error processing {feed_type} feed: {str(e) or type(e).__name__}"
                )

            notify_feed_failure(ctx, detailed_msg)
            raise Exception(detailed_msg)

        # If we get here, we've successfully processed the feed, write out the date to the checkpoint file
        notify_geo_feed_success(ctx)
    finally:
        # Always release the lock
        release_lock(logger, lock_handle, lock_file_path)


def process_feed(
    ctx,
    logger,
    token,
    feed_type,
    input_name,
    ew,
    checkpoint_dir,
    checkpoints_enabled,
    predownload_enabled,
):
    if feed_type == "anonymous-residential/realtime":
        checkpoints_enabled = False

    # Get lock file path and attempt to acquire lock
    lock_file_path = get_lock_file_path(checkpoint_dir, feed_type)
    logger.debug("lock_file_path: %s", lock_file_path)
    
    # Clean up stale locks (older than 24 hours)
    cleanup_stale_lock(logger, lock_file_path)
    
    # Try to acquire the lock
    lock_handle = acquire_lock(logger, lock_file_path)
    if lock_handle is None:
        logger.warning("Another instance is already processing feed type '%s', skipping", feed_type)
        return

    proxy_handler_config = get_proxy_settings(ctx, logger)
    logger.debug("proxy_handler_config: %s", proxy_handler_config)

    try:
        # Get the feed metadata
        try:
            feed_metadata = get_feed_metadata(
                logger, proxy_handler_config, token, feed_type
            )
        except Exception as e:
            notify_feed_failure(ctx, "Error getting spur %s feed metadata" % feed_type)
            logger.error("Error getting feed metadata: %s", e)
            raise e

        # Get the feed identifier early to use for checkpoint naming and uniqueness
        try:
            feed_identifier = get_feed_identifier(
                logger, proxy_handler_config, token, feed_type, feed_metadata
            )
            logger.info("Feed identifier: %s", feed_identifier)
        except Exception as e:
            logger.warning("Failed to get feed identifier, using 'unknown': %s", e)
            feed_identifier = "unknown"

        # Extract the feed date from metadata
        feed_date = feed_metadata.get("date", "unknown")
        logger.info("Feed date: %s", feed_date)

        # Generate checkpoint file path using feed identifier
        checkpoint_file_path = get_checkpoint_file_path(checkpoint_dir, feed_type, feed_identifier)
        logger.debug("checkpoint_file_path: %s", checkpoint_file_path)

        # Clean up old checkpoint files for this feed type
        if checkpoints_enabled:
            cleanup_old_checkpoints(logger, checkpoint_dir, feed_type, feed_identifier)

        # Get the latest checkpoint for this specific feed identifier
        checkpoint = get_checkpoint(logger, checkpoint_file_path, checkpoints_enabled)

        # Check if we've already processed this specific feed identifier
        start_offset = 0
        today = datetime.now(timezone.utc).strftime("%Y%m%d")
        if checkpoints_enabled and checkpoint:
            # Check if this exact feed identifier was already completed
            if (checkpoint.get("feed_identifier") == feed_identifier and 
                checkpoint.get("completed_date") == today):
                logger.info("Feed identifier %s already processed today, skipping", feed_identifier)
                return
            elif (checkpoint.get("feed_identifier") == feed_identifier and 
                  checkpoint.get("last_touched_date") == today and 
                  "offset" in checkpoint):
                # Same feed identifier, same day, but not completed - resume from offset
                logger.info("Resuming processing of feed identifier %s from offset %s", 
                           feed_identifier, checkpoint["offset"])
                start_offset = checkpoint["offset"]
            else:
                # Different feed identifier or different day - start fresh
                logger.info("Starting fresh processing for feed identifier %s", feed_identifier)
                start_offset = 0
        else:
            logger.info("No checkpoint found or checkpoints disabled, starting from offset 0")

        # Process the feed
        logger.debug("Attempting to retrieve feed with feed metadata: %s", feed_metadata)
        processed = 0
        temp_file_path = None
        
        try:
            checkpoint = {
                "offset": start_offset,
                "start_time": time.time(),
                "end_time": None,
                "completed_date": None,
                "last_touched_date": today,
                "feed_metadata": feed_metadata,
                "feed_identifier": feed_identifier,
                "feed_date": feed_date,
            }
            if checkpoints_enabled:
                write_checkpoint(checkpoint_file_path, json.dumps(checkpoint))

            if predownload_enabled:
                # Download feed to temporary file first
                logger.debug("Pre-download mode enabled, downloading feed to temp file")
                temp_file_path, download_feed_identifier = download_feed_to_temp(
                    logger, proxy_handler_config, token, feed_type, feed_metadata
                )
                logger.info("Feed downloaded to temp file: %s", temp_file_path)
                
                # Handle case where we got the real feed identifier during download
                actual_feed_identifier = download_feed_identifier
                if download_feed_identifier != feed_identifier:
                    logger.info("Downloaded feed identifier (%s) differs from expected (%s), using actual identifier", 
                               download_feed_identifier, feed_identifier)
                    
                    # If we initially got "unknown" but now have the real identifier, check if we already processed it
                    if feed_identifier == "unknown" and download_feed_identifier != "unknown":
                        actual_checkpoint_file_path = get_checkpoint_file_path(checkpoint_dir, feed_type, download_feed_identifier)
                        actual_checkpoint = get_checkpoint(logger, actual_checkpoint_file_path, checkpoints_enabled)
                        
                        # Check if this actual feed identifier was already completed today
                        if (checkpoints_enabled and actual_checkpoint and 
                            actual_checkpoint.get("feed_identifier") == download_feed_identifier and 
                            actual_checkpoint.get("completed_date") == today):
                            logger.info("Feed identifier %s already processed today, cleaning up and skipping", download_feed_identifier)
                            # Clean up the temp file
                            try:
                                os.remove(temp_file_path)
                                logger.debug("Cleaned up temp file: %s", temp_file_path)
                            except Exception as cleanup_e:
                                logger.warning("Failed to clean up temp file %s: %s", temp_file_path, cleanup_e)
                            return
                        
                        # Update our checkpoint file path and checkpoint data to use the actual identifier
                        checkpoint_file_path = actual_checkpoint_file_path
                        feed_identifier = download_feed_identifier
                        checkpoint["feed_identifier"] = feed_identifier
                        logger.info("Updated checkpoint to use actual feed identifier: %s", feed_identifier)
                        
                        # Clean up old checkpoint files with the new identifier
                        if checkpoints_enabled:
                            cleanup_old_checkpoints(logger, checkpoint_dir, feed_type, feed_identifier)
                
                # Process the downloaded file
                with gzip.open(temp_file_path, 'rt', encoding='utf-8') as f:
                    for line in f:
                        try:
                            data = json.loads(line)
                            # Add feed_identifier and feed_date to the data
                            data["feed_identifier"] = feed_identifier
                            data["feed_date"] = feed_date
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
                                        checkpoint_file_path, json.dumps(checkpoint)
                                    )
                        except Exception as e:
                            logger.error("Error processing line: %s", e)
            else:
                # Stream mode (original behavior)
                response = get_feed_response(
                    logger, proxy_handler_config, token, feed_type, feed_metadata
                )
                logger.info("Got feed response")
                feed_generation_date = response.headers.get("x-feed-generation-date")
                stream_feed_identifier = response.headers.get("x-goog-generation", "unknown")
                checkpoint["feed_generation_date"] = feed_generation_date
                logger.info("Feed generation date: %s", feed_generation_date)
                logger.info("x-goog-generation: %s", stream_feed_identifier)
                
                # Handle case where we got the real feed identifier during streaming
                if stream_feed_identifier != feed_identifier:
                    logger.info("Stream feed identifier (%s) differs from expected (%s), using actual identifier", 
                               stream_feed_identifier, feed_identifier)
                    
                    # If we initially got "unknown" but now have the real identifier, check if we already processed it
                    if feed_identifier == "unknown" and stream_feed_identifier != "unknown":
                        actual_checkpoint_file_path = get_checkpoint_file_path(checkpoint_dir, feed_type, stream_feed_identifier)
                        actual_checkpoint = get_checkpoint(logger, actual_checkpoint_file_path, checkpoints_enabled)
                        
                        # Check if this actual feed identifier was already completed today
                        if (checkpoints_enabled and actual_checkpoint and 
                            actual_checkpoint.get("feed_identifier") == stream_feed_identifier and 
                            actual_checkpoint.get("completed_date") == today):
                            logger.info("Feed identifier %s already processed today, closing response and skipping", stream_feed_identifier)
                            response.close()
                            return
                        
                        # Update our checkpoint file path and checkpoint data to use the actual identifier
                        checkpoint_file_path = actual_checkpoint_file_path
                        feed_identifier = stream_feed_identifier
                        checkpoint["feed_identifier"] = feed_identifier
                        logger.info("Updated checkpoint to use actual feed identifier: %s", feed_identifier)
                        
                        # Clean up old checkpoint files with the new identifier
                        if checkpoints_enabled:
                            cleanup_old_checkpoints(logger, checkpoint_dir, feed_type, feed_identifier)
                
                with gzip.GzipFile(fileobj=response.raw) as f:
                    for line in f:
                        try:
                            data = json.loads(line.decode("utf-8"))
                            # Add feed_identifier and feed_date to the data
                            data["feed_identifier"] = feed_identifier
                            data["feed_date"] = feed_date
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
                                        checkpoint_file_path, json.dumps(checkpoint)
                                    )
                        except Exception as e:
                            logger.error("Error processing line: %s", e)
                response.close()
                
            checkpoint["offset"] = processed
        except Exception as e:
            checkpoint["offset"] = processed
            if checkpoints_enabled:
                write_checkpoint(checkpoint_file_path, json.dumps(checkpoint))
            logger.error("Error processing feed: %s", e)
            notify_feed_failure(ctx, "Error processing spur %s feed: %s" % (feed_type, e))
            # Clean up temp file if it exists
            if temp_file_path and os.path.exists(temp_file_path):
                try:
                    os.remove(temp_file_path)
                    logger.debug("Cleaned up temp file: %s", temp_file_path)
                except Exception as cleanup_e:
                    logger.warning("Failed to clean up temp file %s: %s", temp_file_path, cleanup_e)
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
            write_checkpoint(checkpoint_file_path, checkpoint_file_new_contents)
        
        # Clean up temp file if it exists
        if temp_file_path and os.path.exists(temp_file_path):
            try:
                os.remove(temp_file_path)
                logger.debug("Cleaned up temp file: %s", temp_file_path)
            except Exception as cleanup_e:
                logger.warning("Failed to clean up temp file %s: %s", temp_file_path, cleanup_e)
    finally:
        # Always release the lock
        release_lock(logger, lock_handle, lock_file_path)


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
        scheme.description = (
            "Downloads the latest spur feed and indexes it into Splunk."
        )
        scheme.use_external_validation = True

        feed_type_argument = Argument("feed_type")
        feed_type_argument.title = "Feed Type"
        feed_type_argument.data_type = Argument.data_type_string
        feed_type_argument.description = "The type of feed to download. Must be one of 'anonymous, anonymous-ipv6, anonymous-residential, anonymous-residential-ipv6, anonymous-residential/realtime, ipgeo'"
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

        # Pre-download settings
        predownload_argument = Argument("enable_predownload")
        predownload_argument.title = "Enable Pre-download"
        predownload_argument.data_type = Argument.data_type_boolean
        predownload_argument.description = "Download the full feed file to a temporary location before processing instead of streaming directly."
        predownload_argument.required_on_create = True
        predownload_argument.required_on_edit = True
        scheme.add_argument(predownload_argument)

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
        if feed_type not in [
            "anonymous",
            "anonymous-ipv6",
            "anonymous-residential",
            "anonymous-residential-ipv6",
            "anonymous-residential/realtime",
            "ipgeo",
        ]:
            raise ValueError(
                f"feed_type must be one of 'anonymous, anonymous-ipv6, anonymous-residential, anonymous-residential-ipv6, anonymous-residential/realtime, ipgeo'; found {feed_type}"
            )

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
            if feed_type not in [
                "anonymous",
                "anonymous-ipv6",
                "anonymous-residential",
                "anonymous-residential-ipv6",
                "anonymous-residential/realtime",
                "ipgeo",
            ]:
                notify_feed_failure(
                    self,
                    f"feed_type must be one of 'anonymous, anonymous-ipv6, anonymous-residential, anonymous-residential-ipv6, anonymous-residential/realtime, ipgeo'; found {feed_type}",
                )
                raise ValueError(
                    f"feed_type must be one of 'anonymous, anonymous-ipv6, anonymous-residential, anonymous-residential-ipv6, anonymous-residential/realtime, ipgeo'; found {feed_type}"
                )
            logger.debug("feed_type: %s", feed_type)

            checkpoints_enabled = bool(int(input_item["enable_checkpoint"]))
            logger.debug("checkpoints_enabled: %s", checkpoints_enabled)
            
            predownload_enabled = bool(int(input_item["enable_predownload"]))
            logger.debug("predownload_enabled: %s", predownload_enabled)

            checkpoint_dir = inputs.metadata["checkpoint_dir"]
            logger.debug("checkpoint_dir: %s", checkpoint_dir)

            try:
                if feed_type == "ipgeo":
                    process_geo_feed(self, logger, token, feed_type, input_name, ew, checkpoint_dir)
                else:
                    process_feed(
                        self,
                        logger,
                        token,
                        feed_type,
                        input_name,
                        ew,
                        checkpoint_dir,
                        checkpoints_enabled,
                        predownload_enabled,
                    )
            except Exception as e:
                logger.error("Error processing feed: %s", e)
                notify_feed_failure(
                    self, "Error processing spur %s feed: %s" % (feed_type, e)
                )
                raise e


if __name__ == "__main__":
    sys.exit(SpurFeed().run(sys.argv))
