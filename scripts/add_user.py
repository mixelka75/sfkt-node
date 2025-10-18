#!/usr/bin/env python3
"""
Script to add user to Xray configuration
"""
import json
import sys
import uuid
from pathlib import Path


def add_user_to_config(config_path: str, user_uuid: str, email: str = None):
    """
    Add a user to Xray configuration

    Args:
        config_path: Path to Xray config file
        user_uuid: User UUID
        email: Optional email/identifier for the user
    """
    config_file = Path(config_path)

    if not config_file.exists():
        print(f"Error: Config file not found: {config_path}")
        sys.exit(1)

    # Load config
    with open(config_file, 'r') as f:
        config = json.load(f)

    # Find VLESS inbound
    vless_inbound = None
    for inbound in config.get('inbounds', []):
        if inbound.get('protocol') == 'vless':
            vless_inbound = inbound
            break

    if not vless_inbound:
        print("Error: No VLESS inbound found in config")
        sys.exit(1)

    # Check if user already exists
    clients = vless_inbound.get('settings', {}).get('clients', [])
    for client in clients:
        if client.get('id') == user_uuid:
            print(f"User {user_uuid} already exists")
            return

    # Add new user
    new_client = {
        "id": user_uuid,
        "flow": "xtls-rprx-vision",
        "level": 0
    }

    if email:
        new_client['email'] = email

    clients.append(new_client)
    vless_inbound['settings']['clients'] = clients

    # Save config
    with open(config_file, 'w') as f:
        json.dump(config, f, indent=2)

    print(f"✓ Added user {user_uuid}")
    if email:
        print(f"  Email: {email}")


def remove_user_from_config(config_path: str, user_uuid: str):
    """
    Remove a user from Xray configuration

    Args:
        config_path: Path to Xray config file
        user_uuid: User UUID to remove
    """
    config_file = Path(config_path)

    if not config_file.exists():
        print(f"Error: Config file not found: {config_path}")
        sys.exit(1)

    # Load config
    with open(config_file, 'r') as f:
        config = json.load(f)

    # Find VLESS inbound
    vless_inbound = None
    for inbound in config.get('inbounds', []):
        if inbound.get('protocol') == 'vless':
            vless_inbound = inbound
            break

    if not vless_inbound:
        print("Error: No VLESS inbound found in config")
        sys.exit(1)

    # Remove user
    clients = vless_inbound.get('settings', {}).get('clients', [])
    new_clients = [c for c in clients if c.get('id') != user_uuid]

    if len(clients) == len(new_clients):
        print(f"User {user_uuid} not found")
        return

    vless_inbound['settings']['clients'] = new_clients

    # Save config
    with open(config_file, 'w') as f:
        json.dump(config, f, indent=2)

    print(f"✓ Removed user {user_uuid}")


if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("Usage:")
        print("  Add user:    python add_user.py /path/to/config.json <uuid> [email]")
        print("  Remove user: python add_user.py /path/to/config.json <uuid> --remove")
        sys.exit(1)

    config_path = sys.argv[1]
    user_uuid = sys.argv[2]

    if len(sys.argv) > 3 and sys.argv[3] == '--remove':
        remove_user_from_config(config_path, user_uuid)
    else:
        email = sys.argv[3] if len(sys.argv) > 3 else None
        add_user_to_config(config_path, user_uuid, email)
