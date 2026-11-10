#!/usr/bin/env bash
# Start on the local network so a phone on the same Wi-Fi can open http://<laptop-ip>:8000
cd "$(dirname "$0")"
IP=$( (hostname -I 2>/dev/null | awk '{print $1}') || true )
[ -z "$IP" ] && IP=$(ipconfig getifaddr en0 2>/dev/null || echo "<your-laptop-ip>")
echo "Open on your phone (same Wi-Fi): http://$IP:8000"
exec python3 -m uvicorn app.main:app --host 0.0.0.0 --port 8000
