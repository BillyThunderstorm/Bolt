import requests
import os
from dotenv import load_dotenv
from pathlib import Path

# Load environment variables from .env file
env_path = Path(__file__).parent.parent / ".env"
load_dotenv(env_path)

# Get credentials from .env
TWITCH_OAUTH_TOKEN = os.getenv("TWITCH_OAUTH_TOKEN")
TWITCH_CLIENT_ID = os.getenv("TWITCH_CLIENT_ID")
TWITCH_CHANNEL = os.getenv("TWITCH_CHANNEL")

# Base URL for Twitch API
TWITCH_API_URL = "https://api.twitch.tv/helix"

# Headers required for all Twitch API requests
def get_headers():
    """
    WHY: Twitch API requires specific headers for authentication.
    - Authorization: Your OAuth token (proves you're allowed to access this data)
    - Client-ID: Your app's ID (identifies which app is making the request)
    """
    return {
        "Authorization": f"Bearer {TWITCH_OAUTH_TOKEN}",
        "Client-ID": TWITCH_CLIENT_ID,
        "Content-Type": "application/json"
    }


def get_follower_count():
    """
    Fetch your Twitch follower count.

    WHY we do this:
    - Twitch doesn't return follower count directly in user info
    - We have to call the "followers" endpoint to get the total_count
    - This is useful for Bolt to announce: "I have X followers"
    """
    try:
        # Get your user ID first (needed to query followers)
        user_response = requests.get(
            f"{TWITCH_API_URL}/users",
            headers=get_headers(),
            params={"login": TWITCH_CHANNEL}
        )
        user_response.raise_for_status()
        user_id = user_response.json()["data"][0]["id"]

        # Now get follower count
        follower_response = requests.get(
            f"{TWITCH_API_URL}/channels/followers",
            headers=get_headers(),
            params={"broadcaster_id": user_id}
        )
        follower_response.raise_for_status()
        follower_count = follower_response.json()["data"][0]["total"]

        return follower_count

    except Exception as e:
        print(f"Error fetching follower count: {e}")
        return None


def get_last_stream_info():
    """
    Fetch info about your last stream.

    WHY we do this:
    - This gives us viewer count and game title from your most recent broadcast
    - Useful for: "Last stream had X viewers" and "Last game played: Y"
    - Twitch API returns streams sorted by start date (newest first)
    """
    try:
        # Get your user ID
        user_response = requests.get(
            f"{TWITCH_API_URL}/users",
            headers=get_headers(),
            params={"login": TWITCH_CHANNEL}
        )
        user_response.raise_for_status()
        user_id = user_response.json()["data"][0]["id"]

        # Get the most recent streams (first result = last stream)
        stream_response = requests.get(
            f"{TWITCH_API_URL}/videos",
            headers=get_headers(),
            params={
                "user_id": user_id,
                "type": "archive",  # Only get VODs (broadcast archives)
                "first": 1  # Only get the most recent one
            }
        )
        stream_response.raise_for_status()

        stream_data = stream_response.json()["data"]

        if not stream_data:
            return {"viewers": 0, "game": "Unknown", "title": "No recent streams"}

        stream = stream_data[0]

        # The "view_count" field shows total views on that VOD
        # Note: This is VOD views, not concurrent viewers during stream
        return {
            "viewers": stream.get("view_count", 0),
            "title": stream.get("title", "Unknown"),
            "created_at": stream.get("created_at", "Unknown")
        }

    except Exception as e:
        print(f"Error fetching last stream info: {e}")
        return {"viewers": 0, "game": "Unknown", "title": "Error fetching stream data"}


def get_current_game():
    """
    Get the game you're currently streaming (or last streamed).

    WHY we do this:
    - This tells us what game you're playing
    - Useful for: "Now playing: X" or clip categorization
    """
    try:
        # Get your user ID
        user_response = requests.get(
            f"{TWITCH_API_URL}/users",
            headers=get_headers(),
            params={"login": TWITCH_CHANNEL}
        )
        user_response.raise_for_status()
        user_id = user_response.json()["data"][0]["id"]

        # Get channel info (includes game name if currently streaming)
        channel_response = requests.get(
            f"{TWITCH_API_URL}/channels",
            headers=get_headers(),
            params={"broadcaster_id": user_id}
        )
        channel_response.raise_for_status()

        channel_data = channel_response.json()["data"][0]
        game_name = channel_data.get("game_name", "Unknown")

        return game_name

    except Exception as e:
        print(f"Error fetching current game: {e}")
        return "Unknown"


def get_all_twitch_data():
    """
    Get ALL Twitch data in one function call.

    WHY: This is what Bolt will call from bot.py
    - Returns a dictionary with everything we need
    - Bolt can then speak this data and add it to clips
    - Single function = single point of failure (easier to debug)
    """
    return {
        "followers": get_follower_count(),
        "last_stream_viewers": get_last_stream_info()["viewers"],
        "last_stream_title": get_last_stream_info()["title"],
        "current_game": get_current_game()
    }


# For testing: run this file directly to see what data we're getting
if __name__ == "__main__":
    print("Testing Twitch API connection...")
    print()

    data = get_all_twitch_data()

    print(f"✓ Followers: {data['followers']}")
    print(f"✓ Last Stream Viewers: {data['last_stream_viewers']}")
    print(f"✓ Last Stream Title: {data['last_stream_title']}")
    print(f"✓ Current Game: {data['current_game']}")
