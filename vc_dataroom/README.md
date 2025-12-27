# VC Data Room

Secure file sharing platform for investor access at https://vc.amphoraxe.ca

## Features

- **Secure Authentication**: JWT-based login with secure password hashing
- **Role-Based Access Control**: Admin and viewer roles
- **File-Level Permissions**: Grant/revoke access to specific files per user
- **Comprehensive Audit Logging**: All actions logged with IP, user agent, timestamps
- **Auto-Update**: Automatically pulls from git and restarts services on commit

## Quick Start

```bash
# Clone the repo
git clone <your-repo-url> ~/Developer/vc_dataroom
cd ~/Developer/vc_dataroom

# Run setup
chmod +x setup.sh
./setup.sh
```

## Architecture

```
vc_dataroom/
├── app/
│   └── main.py              # FastAPI application
├── data/
│   ├── dataroom.db          # SQLite database
│   └── uploads/             # Uploaded files
├── logs/
│   ├── webapp.log
│   └── webapp.error.log
├── infrastructure/
│   ├── plists/              # LaunchAgent configurations
│   ├── scripts/             # Auto-update scripts
│   └── cloudflare/          # Tunnel configuration
├── requirements.txt
├── setup.sh
└── README.md
```

## Port Allocation

| Service | Port |
|---------|------|
| VC Data Room | 8010 |
| (AMP LLM uses 8000-8004) |
| (AMP LLM Dev uses 9000-9004) |

## API Endpoints

### Authentication
- `POST /api/auth/login` - Login and get JWT token
- `POST /api/auth/logout` - Logout and clear session
- `GET /api/auth/me` - Get current user info

### Files
- `GET /api/files` - List accessible files
- `POST /api/files/upload` - Upload file (admin only)
- `GET /api/files/{id}/download` - Download file
- `DELETE /api/files/{id}` - Delete file (admin only)

### Permissions (Admin only)
- `POST /api/files/{id}/permissions` - Grant user access
- `DELETE /api/files/{id}/permissions/{user_id}` - Revoke access
- `GET /api/files/{id}/permissions` - List file permissions

### Users (Admin only)
- `GET /api/users` - List all users
- `POST /api/users` - Create new user
- `DELETE /api/users/{id}` - Deactivate user

### Audit (Admin only)
- `GET /api/audit` - Get audit log entries

## Management

### Check service status
```bash
launchctl list | grep amphoraxe.vc
```

### Restart services
```bash
launchctl unload ~/Library/LaunchAgents/com.amphoraxe.vc.webapp.plist
launchctl load ~/Library/LaunchAgents/com.amphoraxe.vc.webapp.plist
```

### View logs
```bash
tail -f ~/Developer/vc_dataroom/logs/webapp.log
tail -f ~/Developer/vc_dataroom/logs/webapp.error.log
```

### Check auto-update logs
```bash
tail -f /tmp/vc_autoupdate.log
```

## Security Notes

1. Change the default admin password immediately after setup
2. The `VC_SECRET_KEY` environment variable should be kept secure
3. All login attempts (successful and failed) are logged
4. File downloads are logged with user info and IP address
5. SQLite database and uploaded files are stored locally

## Cloudflare Tunnel

The service is exposed via Cloudflare Tunnel. To add the DNS route:

```bash
cloudflared tunnel route dns <tunnel-id> vc.amphoraxe.ca
```

## License

Private - Amphoraxe
