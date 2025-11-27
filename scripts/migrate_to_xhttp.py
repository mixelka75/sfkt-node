#!/usr/bin/env python3
"""
Migration script: TCP+Vision -> XHTTP transport

This script migrates existing Xray configuration from blocked
VLESS+TCP+Reality+xtls-rprx-vision to XHTTP transport.

RKN started blocking TCP+Vision in November 2025. XHTTP transport
is currently not blocked and provides better performance.

Changes:
1. network: tcp -> xhttp
2. Add xhttpSettings with path and mode
3. Remove tcpSettings
4. Remove 'flow' parameter from all clients (XHTTP doesn't use flow)
5. Update sniffing destOverride to include 'quic'

Usage:
    python migrate_to_xhttp.py [--dry-run] [--path /custom/path]
"""
import json
import sys
import shutil
import argparse
from pathlib import Path
from datetime import datetime

CONFIG_PATH = "/usr/local/etc/xray/config.json"
DEFAULT_XHTTP_PATH = "/sfkt"


def backup_config(config_path: str) -> str:
    """Create timestamped backup of current config"""
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_path = f"{config_path}.backup_{timestamp}"
    shutil.copy2(config_path, backup_path)
    print(f"✓ Backup created: {backup_path}")
    return backup_path


def migrate_inbound_to_xhttp(inbound: dict, xhttp_path: str) -> bool:
    """
    Migrate a VLESS inbound from TCP to XHTTP transport

    Returns True if changes were made
    """
    if inbound.get("protocol") != "vless":
        return False

    stream_settings = inbound.get("streamSettings", {})
    current_network = stream_settings.get("network", "tcp")

    # Already using xhttp
    if current_network == "xhttp":
        print(f"  ℹ Inbound '{inbound.get('tag', 'unknown')}' already using XHTTP")
        return False

    # Only migrate TCP transport
    if current_network != "tcp":
        print(f"  ⚠ Skipping inbound '{inbound.get('tag', 'unknown')}' with network '{current_network}'")
        return False

    tag = inbound.get('tag', 'unknown')
    print(f"\n  Migrating inbound '{tag}' from TCP to XHTTP...")

    # 1. Change network to xhttp
    stream_settings["network"] = "xhttp"
    print(f"    + network: tcp -> xhttp")

    # 2. Add xhttpSettings
    stream_settings["xhttpSettings"] = {
        "mode": "auto",
        "path": xhttp_path
    }
    print(f"    + xhttpSettings: mode=auto, path={xhttp_path}")

    # 3. Remove tcpSettings if present
    if "tcpSettings" in stream_settings:
        del stream_settings["tcpSettings"]
        print(f"    - Removed tcpSettings")

    # 4. Remove sockopt (not needed for XHTTP, can cause issues)
    if "sockopt" in stream_settings:
        del stream_settings["sockopt"]
        print(f"    - Removed sockopt (not needed for XHTTP)")

    # 5. Update realitySettings.show to false (reduce logs)
    if "realitySettings" in stream_settings:
        stream_settings["realitySettings"]["show"] = False
        print(f"    + realitySettings.show = false")

    # 6. Update sniffing to include quic
    if "sniffing" in inbound:
        dest_override = inbound["sniffing"].get("destOverride", [])
        if "quic" not in dest_override:
            dest_override.append("quic")
            inbound["sniffing"]["destOverride"] = dest_override
            print(f"    + Added 'quic' to sniffing.destOverride")

    inbound["streamSettings"] = stream_settings
    return True


def remove_flow_from_clients(inbound: dict) -> int:
    """
    Remove 'flow' parameter from all clients in inbound

    Returns number of clients modified
    """
    clients = inbound.get("settings", {}).get("clients", [])
    modified_count = 0

    for client in clients:
        if "flow" in client:
            del client["flow"]
            modified_count += 1

    return modified_count


def update_comment(inbound: dict):
    """Update the comment about client format"""
    settings = inbound.get("settings", {})
    if "_comment" in settings:
        settings["_comment"] = (
            'Client format: {"id": "uuid", "email": "email", "level": 0}. '
            'NOTE: flow is NOT used with XHTTP transport!'
        )


def main():
    parser = argparse.ArgumentParser(
        description="Migrate Xray config from TCP+Vision to XHTTP transport"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would be changed without modifying files"
    )
    parser.add_argument(
        "--path",
        default=DEFAULT_XHTTP_PATH,
        help=f"XHTTP path (default: {DEFAULT_XHTTP_PATH})"
    )
    parser.add_argument(
        "--config",
        default=CONFIG_PATH,
        help=f"Config file path (default: {CONFIG_PATH})"
    )
    args = parser.parse_args()

    print("=" * 60)
    print("XHTTP Migration Script - Bypass RKN blocking (Nov 2025)")
    print("=" * 60)
    print(f"\nXHTTP path: {args.path}")
    if args.dry_run:
        print("MODE: DRY RUN (no changes will be made)")
    print()

    # Check if config exists
    config_path = Path(args.config)
    if not config_path.exists():
        print(f"✗ Config not found: {args.config}")
        sys.exit(1)

    # Read config
    print(f"Reading config from {args.config}...")
    with open(args.config, 'r') as f:
        config = json.load(f)

    if not args.dry_run:
        # Create backup
        print("\nCreating backup...")
        backup_config(args.config)

    # Process inbounds
    print("\nProcessing inbounds...")
    inbounds_modified = 0
    clients_modified = 0

    for inbound in config.get("inbounds", []):
        if inbound.get("protocol") != "vless":
            continue

        # Migrate transport
        if migrate_inbound_to_xhttp(inbound, args.path):
            inbounds_modified += 1

        # Remove flow from clients
        flow_removed = remove_flow_from_clients(inbound)
        if flow_removed > 0:
            clients_modified += flow_removed
            print(f"    - Removed 'flow' from {flow_removed} client(s)")

        # Update comment
        update_comment(inbound)

    # Summary
    print("\n" + "=" * 60)
    print("Migration Summary")
    print("=" * 60)
    print(f"  Inbounds migrated to XHTTP: {inbounds_modified}")
    print(f"  Clients with 'flow' removed: {clients_modified}")

    if inbounds_modified == 0 and clients_modified == 0:
        print("\n✓ No changes needed - config is already migrated!")
        return

    if args.dry_run:
        print("\n⚠ DRY RUN - no changes were made")
        print("  Run without --dry-run to apply changes")
        return

    # Write updated config
    print(f"\nWriting updated config to {args.config}...")
    with open(args.config, 'w') as f:
        json.dump(config, f, indent=2)

    print("\n" + "=" * 60)
    print("✓ Migration completed successfully!")
    print("=" * 60)
    print("\nNext steps:")
    print("  1. Validate config:")
    print(f"     xray test -c {args.config}")
    print("  2. Restart Xray:")
    print("     systemctl restart xray")
    print("  3. Check status:")
    print("     systemctl status xray")
    print("  4. Monitor logs:")
    print("     tail -f /var/log/xray/error.log")
    print("\n⚠ IMPORTANT:")
    print("  Users need to update their subscriptions!")
    print("  The VPN client will automatically get new config on refresh.")


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
