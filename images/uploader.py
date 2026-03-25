import os
import tweepy

import config
from storage.database import log_api_usage


def get_v1_api():
    """Create tweepy v1.1 API client for media uploads."""
    auth = tweepy.OAuth1UserHandler(
        config.X_API_KEY,
        config.X_API_SECRET,
        config.X_ACCESS_TOKEN,
        config.X_ACCESS_TOKEN_SECRET,
    )
    return tweepy.API(auth)


def upload_media(image_path):
    """Upload image to Twitter via v1.1 API. Returns media_id."""
    api = get_v1_api()
    media = api.media_upload(filename=image_path)
    log_api_usage("x", "media_upload", cost_estimate=0.0)
    return media.media_id


def upload_and_cleanup(image_path):
    """Upload image to Twitter and delete local file. Returns [media_id] or None."""
    if not image_path or not os.path.exists(image_path):
        return None

    try:
        media_id = upload_media(image_path)
        # Cleanup local file after successful upload
        try:
            os.remove(image_path)
        except OSError:
            pass
        return [media_id]
    except Exception as e:
        print(f"  Media upload failed: {e}")
        return None
