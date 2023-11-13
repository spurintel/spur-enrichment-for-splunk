"""
This module contains functions for retrieving secrets from Splunk.
"""

SECRET_REALM = "spur_splunk_realm"
SECRET_NAME = "token"

def get_encrypted_context_api_token(ctx):
    """
    Retrieve the encrypted token from the Splunk storage/passwords endpoint.
    """
    secrets = ctx.service.storage_passwords
    return next(secret for secret in secrets if (secret.realm == SECRET_REALM and secret.username == SECRET_NAME)).clear_password
