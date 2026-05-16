 # Setting Up Phone for JARVIS Remote Control

## Android + Termux (Recommended)

### Step 1: Install Termux
1. Download Termux from F-Droid (not Play Store - it's outdated)
2. Open Termux

### Step 2: Install SSH Server
```bash
# Update packages
pkg update && pkg upgrade -y

# Install OpenSSH
pkg install openssh -y

# Set password
passwd

# Get your username
whoami
# Usually: u0_aXXX

# Start SSH server
sshd

# Check IP on Tailscale
tailscale ip -4
```

from backend.remote_admin import add_remote_device

add_remote_device(
    name="samsung",           # Simple, no spaces
    host="100.89.159.84",     # Your Tailscale IP
    user="u0_a404",           # Your Termux username
    auth_method="password",   # Just the word "password", not your actual password
    device_type="android"
)
```

### Step 4: Test Commands
- "Jarvis, check disk on samsung"
- "Jarvis, check memory on samsung"

---

## iPhone (Limited)
iOS doesn't allow SSH servers in background. Alternative:

### Option A: Use as Control Endpoint Only
Your iPhone can:
- Access JARVIS dashboard via Tailscale (http://your-pc:8081)
- Send voice commands
- Receive notifications

### Option B: Shortcuts Automation
Create iOS Shortcuts that send HTTP requests to JARVIS API:
```
URL: http://your-pc:5050/api/command
Method: POST
Body: {"command": "check weather"}
```

---

## What You Can Do Once Connected

| Command | What Happens |
|---------|---------------|
| "check disk on samsung" | Shows phone storage |
| "check memory on samsung" | Shows RAM usage |
| "check battery on samsung" | Shows battery level |

Note: Advanced control (restart, etc.) requires root on Android.
