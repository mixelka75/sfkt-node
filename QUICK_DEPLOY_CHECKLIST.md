# Quick Deploy Checklist - API-Based User Management

## Prerequisites
- [x] Code changes committed to git
- [ ] Access to VPN node server (sfktnodesw)
- [ ] Backup plan ready

## On VPN Node (sfktnodesw)

### 1. Backup (30 seconds)
```bash
cd /opt/sfkt-node
cp /usr/local/etc/xray/config.json /root/xray_backup_$(date +%Y%m%d_%H%M).json
```

### 2. Update Xray Config (1 minute)
```bash
nano /usr/local/etc/xray/config.json
```
Add `"HandlerService"` to `"services"` array:
```json
"api": {
  "tag": "api",
  "services": [
    "StatsService",
    "HandlerService"  ← ADD THIS
  ]
}
```

### 3. Restart Xray (10 seconds)
```bash
systemctl restart xray && systemctl status xray
```
✅ Should show "active (running)"

### 4. Update Node Agent Code (1 minute)
```bash
cd /opt/sfkt-node
git pull
docker compose build node-agent
docker compose up -d node-agent
```

### 5. Verify (30 seconds)
```bash
docker compose logs node-agent --tail=50 -f
```
✅ Look for: "via API (no restart)"

## Test

**On main server** - Toggle user premium status via admin panel

**On node** - Within 60 seconds, see:
```
✓ Added user <uuid> via API (no restart)
```

## Rollback (if needed)
```bash
cp /root/xray_backup_*.json /usr/local/etc/xray/config.json
systemctl restart xray
git checkout HEAD~1 node-service/node_agent.py
docker compose build node-agent && docker compose up -d node-agent
```

---

**Total Time**: ~3 minutes  
**Downtime**: ~5 seconds (Xray restart only)

See `DEPLOY_API_UPDATE.md` for detailed documentation.
