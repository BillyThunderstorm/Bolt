"""
Get Twitch User Access Token - The Easy Way

WHY this exists:
- The Twitch CLI method is unreliable (browser redirect issues)
- This Python script handles the OAuth flow directly
- More transparent — you see exactly what's happening

HOW IT WORKS:
1. You provide your Client ID and Client Secret
2. Script opens a browser window
3. You click "Authorize"
4. Script captures the code and exchanges it for a token
5. Token is printed and ready to add to .env

WHAT YOU NEED:
- Your Client ID (from Twitch Console)
- Your Client Secret (from Twitch Console)
"""

import webbrowser
import requests
from urllib.parse import urlencode, parse_qs, urlparse
from https.server import HTTPServer, BaseHTTPSRequestHandler
import threading
import time
import sys

# Configuration
REDIRECT_URI = "https://localhost:3000/callback"  # Must match what you set in Twitch Console
SCOPES = "user:read:email channel:read:stream_key"  # Permissions Billy needs

# Global variable to store the auth code
auth_code = None
server_thread = None


class AuthCallbackHandler(BaseHTTPRequestHandler):
    """
    WHY: This catches the browser redirect from Twitch with the auth code.
    Twitch redirects to https://localhost:3000/callback?code=XXXXX after user authorizes.
    We catch that and extract the code.
    """

    def do_GET(self):
        global auth_code

        # Parse the redirect URL
        parsed = urlparse(self.path)

        if parsed.path == "/callback":
            # Extract the auth code from the URL
            query_params = parse_qs(parsed.query)

            if "code" in query_params:
                auth_code = query_params["code"][0]

                # Send success response to browser
                self.send_response(200)
                self.send_header("Content-type", "text/html")
                self.end_headers()
                self.wfile.write(
                    b"""
                <html>
                <head><title>Bolt - Twitch Authorization</title></head>
                <body style="font-family: sans-serif; padding: 40px; text-align: center;">
                    <h1>✅ Authorization Successful!</h1>
                    <p>You can close this window.</p>
                    <p>Your token is being generated...</p>
                </body>
                </html>
                """
                )
            else:
                # Error response
                self.send_response(400)
                self.send_header("Content-type", "text/html")
                self.end_headers()
                self.wfile.write(
                    b"""
                <html>
                <body style="font-family: sans-serif; padding: 40px; text-align: center;">
                    <h1>❌ Authorization Failed</h1>
                    <p>No authorization code received.</p>
                </body>
                </html>
                """
                )
        else:
            self.send_response(404)
            self.end_headers()

    def log_message(self, format, *args):
        """Suppress server logging"""
        pass


def start_callback_server():
    """Start the local server to catch the redirect."""
    server = HTTPServer(("localhost", 3000), AuthCallbackHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return server


def get_twitch_user_token(client_id, client_secret):
    """
    Main function to get the user access token.

    WHY we do this in steps:
    1. Get auth code from user via browser
    2. Exchange code for access token
    3. Return token to user
    """

    print("\n🦊 Bolt Twitch Token Generator\n")
    print("=" * 50)

    # Step 1: Start local callback server
    print("Step 1: Starting local callback server...")
    server = start_callback_server()
    print("✓ Server listening on https://localhost:3000")

    # Step 2: Build the authorization URL
    auth_url = "https://id.twitch.tv/oauth2/authorize?" + urlencode(
        {
            "client_id": client_id,
            "redirect_uri": REDIRECT_URI,
            "response_type": "code",
            "scope": SCOPES,
        }
    )

    print("\nStep 2: Opening browser for authorization...")
    print("(If browser doesn't open, copy this link manually:)")
    print(f"\n{auth_url}\n")

    # Open browser
    webbrowser.open(auth_url)

    # Step 3: Wait for callback
    print("Step 3: Waiting for authorization...")
    print("(You should see a browser window. Click 'Authorize')\n")

    # Wait for auth code (max 2 minutes)
    timeout = 120
    elapsed = 0
    while auth_code is None and elapsed < timeout:
        time.sleep(1)
        elapsed += 1

        # Show progress
        if elapsed % 10 == 0:
            print(f"  Still waiting... ({elapsed}s)")

    if auth_code is None:
        print("❌ Timeout: No authorization received")
        server.shutdown()
        return None

    print(f"✓ Authorization code received!")

    # Step 4: Exchange code for access token
    print("\nStep 4: Exchanging code for access token...")

    token_url = "https://id.twitch.tv/oauth2/token"
    token_payload = {
        "client_id": client_id,
        "client_secret": client_secret,
        "code": auth_code,
        "grant_type": "authorization_code",
        "redirect_uri": REDIRECT_URI,
    }

    try:
        response = requests.post(token_url, data=token_payload)
        response.raise_for_status()
        token_data = response.json()

        access_token = token_data.get("access_token")
        refresh_token = token_data.get("refresh_token")

        if access_token:
            print("✓ Token generated successfully!\n")
            print("=" * 50)
            print("\n🎯 YOUR TWITCH ACCESS TOKEN:\n")
            print(access_token)
            print("\n" + "=" * 50)
            print("\nAdd this to your .env file as:")
            print('TWITCH_OAUTH_TOKEN=' + access_token)

            if refresh_token:
                print("\nRefresh Token (keep safe):")
                print('TWITCH_REFRESH_TOKEN=' + refresh_token)

            return access_token
        else:
            print("❌ No access token in response")
            print("Response:", token_data)
            return None

    except Exception as e:
        print(f"❌ Error exchanging code: {e}")
        return None

    finally:
        server.shutdown()


if __name__ == "__main__":
    # Get credentials from user
    print("You need your Twitch Client ID and Secret.")
    print("Get them from: https://dev.twitch.tv/console/apps\n")

    client_id = input("Enter your Twitch Client ID: ").strip()
    client_secret = input("Enter your Twitch Client Secret: ").strip()

    if not client_id or not client_secret:
        print("❌ Client ID and Secret required")
        sys.exit(1)

    # Get token
    token = get_twitch_user_token(client_id, client_secret)

    if token:
        print("\n✅ Done! Copy the token above and add it to your .env file.\n")
    else:
        print("\n❌ Failed to get token.\n")
