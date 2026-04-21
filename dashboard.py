"""
Bolt Dashboard - A simple web interface to view your Twitch stats and bot status.

WHY this exists:
- Gives Billy a visual way to see stream stats without opening Terminal
- Can be opened in any web browser
- Shows data in real-time as Bolt processes clips

HOW to use:
- Run: python3 dashboard.py
- Open: http://localhost:5000 in your browser
- The page auto-refreshes every 10 seconds to show latest data
"""

from flask import Flask, render_template, jsonify
from pathlib import Path
import sys
import os
from dotenv import load_dotenv

# Add the Bolt root to Python path so we can import our modules
Bolt_root = Path(__file__).resolve().parent
sys.path.insert(0, str(Bolt_root))

# Load environment variables
load_dotenv(Bolt_root / ".env")

# Import our Twitch API module
try:
    from modules.Twitch_API import get_all_twitch_data
    TWITCH_AVAILABLE = True
except ImportError:
    TWITCH_AVAILABLE = False

app = Flask(__name__)

# HTML Template
DASHBOARD_HTML = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Bolt Dashboard</title>
    <style>
        * {
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }

        body {
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            min-height: 100vh;
            padding: 20px;
        }

        .container {
            max-width: 1000px;
            margin: 0 auto;
        }

        header {
            text-align: center;
            color: white;
            margin-bottom: 30px;
        }

        h1 {
            font-size: 2.5em;
            margin-bottom: 10px;
        }

        .status {
            font-size: 1.1em;
            opacity: 0.9;
        }

        .status-online {
            color: #4ade80;
        }

        .stats-grid {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(250px, 1fr));
            gap: 20px;
            margin-bottom: 30px;
        }

        .stat-card {
            background: white;
            border-radius: 12px;
            padding: 20px;
            box-shadow: 0 10px 30px rgba(0, 0, 0, 0.2);
            transition: transform 0.3s ease;
        }

        .stat-card:hover {
            transform: translateY(-5px);
        }

        .stat-label {
            color: #666;
            font-size: 0.9em;
            text-transform: uppercase;
            letter-spacing: 0.05em;
            margin-bottom: 10px;
        }

        .stat-value {
            font-size: 2.5em;
            font-weight: bold;
            color: #667eea;
        }

        .stat-game {
            font-size: 1.5em;
            color: #667eea;
            font-weight: 600;
        }

        .refresh-info {
            text-align: center;
            color: white;
            font-size: 0.9em;
            opacity: 0.8;
        }

        .error-state {
            background: white;
            border-radius: 12px;
            padding: 30px;
            text-align: center;
            color: #dc2626;
        }

        .error-state p {
            margin-bottom: 10px;
        }

        footer {
            text-align: center;
            color: white;
            margin-top: 40px;
            opacity: 0.7;
            font-size: 0.9em;
        }
    </style>
</head>
<body>
    <div class="container">
        <header>
            <h1>🦊 Bolt Dashboard</h1>
            <div class="status">
                <span class="status-online">● Online</span>
                <span> | Last refresh: <span id="refresh-time">just now</span></span>
            </div>
        </header>

        <div id="stats-container" class="stats-grid">
            <!-- Stats will be loaded here by JavaScript -->
        </div>

        <div class="refresh-info">
            Auto-refreshing every 10 seconds
        </div>

        <footer>
            Built with ❤️ for Billy | Part of the Bolt content creation bot
        </footer>
    </div>

    <script>
        // Function to format large numbers
        function formatNumber(num) {
            if (!num) return "—";
            if (num >= 1000) {
                return (num / 1000).toFixed(1) + "K";
            }
            return num.toString();
        }

        // Function to update the dashboard
        async function updateStats() {
            try {
                const response = await fetch('/api/stats');
                const data = await response.json();

                const container = document.getElementById('stats-container');

                if (data.error) {
                    container.innerHTML = `<div class="error-state"><p>⚠️ ${data.error}</p><p>Make sure Twitch credentials are set in .env</p></div>`;
                    return;
                }

                // Build stat cards
                container.innerHTML = `
                    <div class="stat-card">
                        <div class="stat-label">Followers</div>
                        <div class="stat-value">${formatNumber(data.followers)}</div>
                    </div>
                    <div class="stat-card">
                        <div class="stat-label">Last Stream Viewers</div>
                        <div class="stat-value">${formatNumber(data.last_stream_viewers)}</div>
                    </div>
                    <div class="stat-card">
                        <div class="stat-label">Last Stream Title</div>
                        <div class="stat-value" style="font-size: 1.2em;">"${data.last_stream_title || 'N/A'}"</div>
                    </div>
                    <div class="stat-card">
                        <div class="stat-label">Current Game</div>
                        <div class="stat-game">${data.current_game || 'Unknown'}</div>
                    </div>
                `;

                // Update refresh time
                const now = new Date();
                document.getElementById('refresh-time').textContent =
                    now.toLocaleTimeString('en-US', {
                        hour: '2-digit',
                        minute: '2-digit',
                        second: '2-digit'
                    });

            } catch (error) {
                console.error('Error fetching stats:', error);
                document.getElementById('stats-container').innerHTML =
                    '<div class="error-state"><p>❌ Error fetching data</p><p>Make sure the server is running and connected to the internet</p></div>';
            }
        }

        // Update immediately on load, then every 10 seconds
        updateStats();
        setInterval(updateStats, 10000);
    </script>
</body>
</html>
"""


@app.route('/')
def dashboard():
    """Serve the dashboard HTML."""
    return DASHBOARD_HTML


@app.route('/api/stats')
def api_stats():
    """
    API endpoint that returns current Twitch stats as JSON.

    WHY a separate endpoint:
    - Frontend JavaScript can call this to get fresh data
    - The page auto-refreshes without reloading
    - Easier to add more data sources later (OBS, YouTube, etc.)
    """
    try:
        if not TWITCH_AVAILABLE:
            return jsonify({
                "error": "Twitch API module not available"
            }), 500

        # Get the Twitch data
        data = get_all_twitch_data()

        # Return as JSON
        return jsonify({
            "followers": data.get("followers"),
            "last_stream_viewers": data.get("last_stream_viewers"),
            "last_stream_title": data.get("last_stream_title"),
            "current_game": data.get("current_game")
        })

    except Exception as e:
        return jsonify({
            "error": f"Error fetching Twitch stats: {str(e)}"
        }), 500


if __name__ == "__main__":
    # Check if Flask is installed
    try:
        import flask
    except ImportError:
        print("Error: Flask is not installed.")
        print("Install it with: pip install flask")
        sys.exit(1)

    print("🦊 Bolt Dashboard starting...")
    print("Open http://localhost:5000 in your browser")
    print("Press Ctrl+C to stop")

    # Run on localhost, accessible from browser
    app.run(
        host='localhost',
        port=5000,
        debug=True,  # Auto-reloads when code changes
        use_reloader=False  # Disable reloader to avoid import issues
    )
