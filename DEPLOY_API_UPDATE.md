# Deploy Xray API-Based User Management

This update enables zero-downtime user management by using Xray's HandlerService API instead of restarting the service.

## What Changed

### Benefits
- **Zero downtime**: Users are added/removed instantly without disconnecting existing connections
- **Faster synchronization**: No need to wait for Xray restart (2-3 seconds)
- **Better user experience**: Premium users get access immediately after payment

### Technical Changes
1. **Xray config**: Added `HandlerService` to API services
2. **node_agent.py**:
   - `add_user()` now uses `xray api adi` command
   - `remove_user()` now uses `xray api rmi` command
   - Config file is still updated for persistence after restarts
   - `reload_xray()` no longer restarts the service

## Deployment Steps

### On Main Server (sfktmain)

```bash
cd /opt/sfkt
git pull
# No changes needed on main server - only node service changed
```

### On VPN Node (sfktnodesw)

**1. Backup current configuration:**
```bash
cd /opt/sfkt-node
cp /usr/local/etc/xray/config.json /root/xray_config_backup_$(date +%Y%m%d).json
```

**2. Pull latest changes:**
```bash
git pull
# OR if you deployed manually, copy the updated files:
# - node-service/node_agent.py
# - node-service/config/xray_template.json
```

**3. Update Xray configuration to add HandlerService:**
```bash
# Edit the live Xray config
nano /usr/local/etc/xray/config.json
```

Find the `"api"` section and change from:
```json
"api": {
  "tag": "api",
  "services": [
    "StatsService"
  ]
},
```

To:
```json
"api": {
  "tag": "api",
  "services": [
    "StatsService",
    "HandlerService"
  ]
},
```

**4. Restart Xray to load HandlerService:**
```bash
systemctl restart xray
systemctl status xray
# Should show "active (running)"
```

**5. Update and restart node-agent:**
```bash
cd /opt/sfkt-node

# Rebuild the node-agent container with new code
docker compose build node-agent

# Restart the container
docker compose up -d node-agent

# Watch logs to verify it's working
docker compose logs node-agent -f --tail=50
```

**6. Verify the update:**

You should see logs like:
```
✓ Added user <uuid> via API (no restart)
✓ Removed user <uuid> via API (no restart)
✓ User sync complete: added 1, removed 0, total 2 (via API, no downtime)
```

## Testing

### Test 1: Add User Without Restart

**On main server**, grant premium to a test user through admin panel.

**On node**, watch logs:
```bash
docker compose logs node-agent -f | grep -E "Added|Removed|sync complete"
```

Expected within 60 seconds:
```
✓ Added user <uuid> via API (no restart)
✓ User sync complete: added 1, removed 0, total X (via API, no downtime)
```

**Verify**: User should be able to connect immediately without Xray restart.

### Test 2: Remove User Without Restart

**On main server**, cancel user subscription or wait for traffic limit.

**On node**, watch logs:
```bash
docker compose logs node-agent -f | grep -E "Added|Removed|sync complete"
```

Expected within 60 seconds:
```
✓ Removed user <uuid> via API (no restart)
✓ User sync complete: added 0, removed 1, total X (via API, no downtime)
```

**Verify**: User's existing connection may continue briefly, but new connections should fail immediately.

### Test 3: Verify Xray Uptime

```bash
systemctl status xray
```

The "Active" line should show the service has been running continuously (not restarted every minute).

### Test 4: Check Xray API Commands

Test the API commands directly:

```bash
# List current users (through config file)
cat /usr/local/etc/xray/config.json | grep '"id"'

# Try adding a test user manually
/usr/local/bin/xray api adi -s 127.0.0.1:10085 -tag vless-in \
  -uuid "test-1234-5678-90ab-cdef01234567" \
  -email "test@example.com"

# Try removing the test user
/usr/local/bin/xray api rmi -s 127.0.0.1:10085 -tag vless-in \
  -uuid "test-1234-5678-90ab-cdef01234567"
```

## Troubleshooting

### "Failed to add user via API"

**Check if HandlerService is enabled:**
```bash
cat /usr/local/etc/xray/config.json | grep -A 5 '"api"'
```

Should show:
```json
"services": [
  "StatsService",
  "HandlerService"
]
```

If not, add `"HandlerService"` and restart Xray.

### "Cannot execute /usr/local/bin/xray from container"

The Docker container may not have access to the host's xray binary. Verify:

```bash
docker compose exec node-agent ls -la /usr/local/bin/xray
```

If file not found, you need to mount the xray binary or install xray in the container.

**Solution**: Update `docker-compose.yml` to mount xray binary:
```yaml
volumes:
  - /usr/local/bin/xray:/usr/local/bin/xray:ro
```

### User still connects after removal

**Wait 30 seconds** for next traffic sync. The node_agent syncs every 60 seconds by default.

To force immediate sync:
```bash
docker compose restart node-agent
```

### Xray not starting after adding HandlerService

**Check for config syntax errors:**
```bash
/usr/local/bin/xray run -test -config /usr/local/etc/xray/config.json
```

Fix any JSON syntax errors (missing commas, brackets, etc).

## Rollback

If something goes wrong:

**1. Restore backup config:**
```bash
cp /root/xray_config_backup_YYYYMMDD.json /usr/local/etc/xray/config.json
systemctl restart xray
```

**2. Restore old node-agent code:**
```bash
cd /opt/sfkt-node
git checkout HEAD~1 node-service/node_agent.py
docker compose build node-agent
docker compose up -d node-agent
```

## Performance Impact

- **Before**: User changes caused 2-3 second service restart every 60 seconds (if there were changes)
- **After**: User changes happen instantly with zero downtime
- **Config file**: Still updated for persistence, but Xray not restarted
- **API overhead**: Minimal - single gRPC call per add/remove operation

## Next Steps

After successful deployment:
1. Monitor logs for 24 hours to ensure stability
2. Check user connection success rate in Telegram bot
3. Consider reducing `USER_SYNC_INTERVAL` from 60s to 30s for faster updates

## Related Documentation

- Xray API: https://xtls.github.io/en/config/api.html
- HandlerService: https://xtls.github.io/en/config/api.html#handlerservice
