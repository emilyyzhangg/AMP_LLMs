Setup Server
# 1. Install Cloudflare Tunnel
brew install cloudflared

# 2. Login
cloudflared tunnel login

# 3. Create tunnel
cloudflared tunnel create amp-llm

# Save the tunnel ID shown!
amphoraxe@AmphoraxeMacBox ~ % cloudflared tunnel create amp-llm
Tunnel credentials written to /Users/amphoraxe/.cloudflared/83fa7b4f-2f7b-4afc-99d7-57ea2e6ac39e.json. cloudflared chose this file based on where your origin certificate was found. Keep this file secret. To revoke these credentials, delete the tunnel.

Created tunnel amp-llm with id 83fa7b4f-2f7b-4afc-99d7-57ea2e6ac39e

# Create config file ~/.cloudflared/config.yml
tunnel: YOUR-TUNNEL-ID-HERE
credentials-file: /Users/emilyzhang/.cloudflared/YOUR-TUNNEL-ID-HERE.json

ingress:
  - hostname: llm.amphoraxe.ca
    service: http://localhost:8000
  - service: http_status:404
# bash
# 5. Route DNS
cloudflared tunnel route dns amp-llm llm.amphoraxe.ca

# 6. Install as service
sudo cloudflared service install

# 7. Start service
sudo launchctl start com.cloudflare.cloudflared

# 8. Check status
sudo launchctl list | grep cloudflared

Step 8: Cloudflare Access (Web Dashboard)

Go to Cloudflare Dashboard → Zero Trust
Navigate to Access → Applications
Click Add an Application → Self-hosted
Configure:

Application name: AMP LLM
Subdomain: llm
Domain: amphoraxe.ca
Session Duration: 24 hours


Add Policy:

Policy name: Authorized Users Only
Action: Allow
Include: Emails → Add your email(s)


Save

# Step 9: Run the Server
Manual start:
cd /path/to/amp_llm_v3
python -m uvicorn webapp.server:app --host 0.0.0.0 --port 8000

Or create launch daemon ('LaunchAgent' because Mac likes to be different and special)
vim ~/Library/LaunchAgents/com.amplm.webapp.plist:
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>com.amplm.webapp</string>
    <key>ProgramArguments</key>
    <array>
        <string>/usr/local/bin/python3</string>
        <string>-m</string>
        <string>uvicorn</string>
        <string>webapp.server:app</string>
        <string>--host</string>
        <string>0.0.0.0</string>
        <string>--port</string>
        <string>8000</string>
    </array>
    <key>WorkingDirectory</key>
    <string>/Users/emilyzhang/amp_llm_v3</string>
    <key>EnvironmentVariables</key>
    <dict>
        <key>PATH</key>
        <string>/usr/local/bin:/usr/bin:/bin</string>
    </dict>
    <key>RunAtLoad</key>
    <true/>
    <key>KeepAlive</key>
    <true/>
    <key>StandardOutPath</key>
    <string>/Users/emilyzhang/amp_llm_v3/webapp.log</string>
    <key>StandardErrorPath</key>
    <string>/Users/emilyzhang/amp_llm_v3/webapp.error.log</string>
</dict>
</plist>

# Load Service
launchctl load ~/Library/LaunchAgents/com.amplm.webapp.plist
launchctl start com.amplm.webapp

# Access Webpage
Step 10: Usage
Access the App:

Go to https://llm.amphoraxe.ca
Cloudflare will ask you to login (enter your email)
Once authenticated, enter your API key
Start chatting!

# Step 10: Usage
Access the App:

Go to https://llm.amphoraxe.ca
Cloudflare will ask you to login (enter your email)
Once authenticated, enter your API key
Start chatting!

API Usage (for scripts):
bash# Get API key from .env file
curl -X POST https://llm.amphoraxe.ca/chat \
  -H "Authorization: Bearer your-api-key-here" \
  -H "Content-Type: application/json" \
  -d '{"query": "What are AMP trials?", "model": "llama3.2"}'

Python Client:
import requests

API_KEY = "your-api-key-here"
API_URL = "https://llm.amphoraxe.ca"

def chat(query: str, model: str = "llama3.2"):
    response = requests.post(
        f"{API_URL}/chat",
        headers={"Authorization": f"Bearer {API_KEY}"},
        json={"query": query, "model": model}
    )
    return response.json()

result = chat("Tell me about clinical trials")
print(result["response"])