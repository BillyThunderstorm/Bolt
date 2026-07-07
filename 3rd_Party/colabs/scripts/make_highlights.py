  import requests

   # 1️⃣ CONFIGURATION: Enter your details here
   CLIENT_ID = 0dc6qh57s99baxh1pt4do49hbddna3
   BEARER_TOKEN = 'YOUR_USER_BEARER_TOKEN_HERE'
   BROADCASER_USER_ID = 'YOUR_TWITCH_CHANNEL_USER_ID' # Not the username, the numbers (e.g. 12345)

   def get_latest_vod_id():
       """Finds the ID of your most recent past stream so we can use it."""
       url = f'https://api.twitch.tv/helix/videos?user_id={BROADCASER_USER_ID}&first=1'

       headers = {
           'Authorization': f'Bearer {BEARER_TOKEN}',
           'Client-Id': CLIENT_ID
       }

       response = requests.get(url, headers=headers)

       if response.status_code != 200:
           return None # Failed to get ID

       data = response.json().get('data')
       if data:
           return {
               'id': data[0]['id'],
               'title': data[0].get('title', 'Untitled VOD'),
               'created_at': data[0]['created_at']
           }
       else:
           return None

   def create_highlight_from_vod(video_data):
       """Sends the request to Twitch to generate the clip automatically."""

       # This is the specific endpoint that does the "Highlight" button job
       api_url = 'https://api.twitch.tv/helix/clips'

       headers = {
           'Authorization': f'Bearer {BEARER_TOKEN}',
           'Client-Id': CLIENT_ID,
           'Content-Type': 'application/json'
       }

       # We send the video ID to Twitch to tell it which past moment to grab
       payload = {
           "source_video_id": video_data['id'],
           "broadcaster_id": BROADCASER_USER_ID
       }

       print(f"⏳ Asking Twitch to make a highlight for '{video_data['title']}'...")

       # POST request creates the clip
       response = requests.post(api_url, headers=headers, json=payload)

       if response.status_code == 202:
           # 202 means it accepted the request and created the clip
           result = response.json()
           clip_link = result['data'][0]['url']
           edit_link = result['data'][0]['edit_url']

           print(f"✅ Success! Highlight Created!")
           print(f"🔗 Watch Link: {clip_link}")
           return True
       else:
           print(f"❌ Error: {response.status_code} - {response.text}")
           return False

   # --- MAIN EXECUTION ---
   if __name__ == '__main__':
       # Step 1: Find the video
       print("🔍 Searching past VODs...")
       last_video = get_latest_vod_id()

       if last_video:
           print(f"Found: {last_video['title']}")

           # Step 2: Create the highlight!
           create_highlight_from_vod(last_video)
       else:
           print("No past videos found or authentication failed.")

