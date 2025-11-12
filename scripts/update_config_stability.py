#!/usr/bin/env python3
"""
Script to update existing Xray config with stability improvements:
- Add policy timeouts (handshake, connIdle, uplinkOnly, downlinkOnly, bufferSize)
- Add sockopt for TCP keepalive on inbound
- Add sockopt and settings for outbound
"""
import json
import sys
import shutil
from pathlib import Path

CONFIG_PATH = "/usr/local/etc/xray/config.json"

def backup_config(config_path: str):
    """Create backup of current config"""
    backup_path = f"{config_path}.backup"
    shutil.copy2(config_path, backup_path)
    print(f"✓ Backup created: {backup_path}")
    return backup_path

def update_policy(config: dict) -> bool:
    """Add timeout settings to policy"""
    modified = False

    if "policy" not in config:
        config["policy"] = {"levels": {}, "system": {}}

    if "levels" not in config["policy"]:
        config["policy"]["levels"] = {}

    if "0" not in config["policy"]["levels"]:
        config["policy"]["levels"]["0"] = {}

    level_0 = config["policy"]["levels"]["0"]

    # Add timeout settings if missing
    updates = {
        "handshake": 8,
        "connIdle": 600,
        "uplinkOnly": 5,
        "downlinkOnly": 10,
        "bufferSize": 512
    }

    for key, value in updates.items():
        if key not in level_0:
            level_0[key] = value
            modified = True
            print(f"  + Added policy.levels.0.{key} = {value}")

    return modified

def update_inbound_sockopt(config: dict) -> bool:
    """Add sockopt to inbound streamSettings"""
    modified = False

    if "inbounds" not in config:
        return False

    for inbound in config["inbounds"]:
        # Only update VLESS inbound
        if inbound.get("protocol") != "vless":
            continue

        if "streamSettings" not in inbound:
            inbound["streamSettings"] = {}

        stream_settings = inbound["streamSettings"]

        # Add sockopt if missing
        if "sockopt" not in stream_settings:
            stream_settings["sockopt"] = {
                "tcpNoDelay": True,
                "tcpKeepAliveIdle": 300,
                "tcpKeepAliveInterval": 30,
                "tcpUserTimeout": 10000,
                "tcpFastOpen": False,
                "mark": 0
            }
            modified = True
            print(f"  + Added sockopt to inbound '{inbound.get('tag', 'unknown')}'")

    return modified

def update_outbound_settings(config: dict) -> bool:
    """Add settings and sockopt to outbound"""
    modified = False

    if "outbounds" not in config:
        return False

    for outbound in config["outbounds"]:
        # Only update 'direct' outbound
        if outbound.get("tag") != "direct":
            continue

        # Add settings
        if "settings" not in outbound:
            outbound["settings"] = {
                "domainStrategy": "UseIPv4"
            }
            modified = True
            print(f"  + Added settings to outbound 'direct'")

        # Add streamSettings with sockopt
        if "streamSettings" not in outbound:
            outbound["streamSettings"] = {
                "sockopt": {
                    "tcpNoDelay": True,
                    "tcpKeepAliveIdle": 300,
                    "tcpKeepAliveInterval": 30,
                    "tcpFastOpen": False
                }
            }
            modified = True
            print(f"  + Added sockopt to outbound 'direct'")

    return modified

def main():
    print("=" * 60)
    print("Xray Config Stability Update Script")
    print("=" * 60)

    # Check if config exists
    if not Path(CONFIG_PATH).exists():
        print(f"✗ Config not found: {CONFIG_PATH}")
        sys.exit(1)

    # Read config
    print(f"\nReading config from {CONFIG_PATH}...")
    with open(CONFIG_PATH, 'r') as f:
        config = json.load(f)

    # Backup
    print("\nCreating backup...")
    backup_config(CONFIG_PATH)

    # Apply updates
    print("\nApplying updates...")
    modified = False

    print("\n1. Updating policy...")
    if update_policy(config):
        modified = True
    else:
        print("  ✓ Policy already up to date")

    print("\n2. Updating inbound sockopt...")
    if update_inbound_sockopt(config):
        modified = True
    else:
        print("  ✓ Inbound sockopt already up to date")

    print("\n3. Updating outbound settings...")
    if update_outbound_settings(config):
        modified = True
    else:
        print("  ✓ Outbound settings already up to date")

    if not modified:
        print("\n✓ No changes needed, config is already up to date!")
        return

    # Write updated config
    print(f"\nWriting updated config to {CONFIG_PATH}...")
    with open(CONFIG_PATH, 'w') as f:
        json.dump(config, f, indent=2)

    print("\n" + "=" * 60)
    print("✓ Config updated successfully!")
    print("=" * 60)
    print("\nNext steps:")
    print("1. Validate config: xray test -c /usr/local/etc/xray/config.json")
    print("2. Restart Xray: systemctl restart xray")
    print("3. Check status: systemctl status xray")
    print("4. Monitor logs: tail -f /var/log/xray/error.log")

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n\n✗ Cancelled by user")
        sys.exit(1)
    except Exception as e:
        print(f"\n✗ Error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
