#!/usr/bin/env python3
"""
Node Agent - Manages Xray node and communicates with main server
"""
import asyncio
import aiohttp
import json
import os
import tempfile
import subprocess
import psutil
import logging
from datetime import datetime
from typing import Dict, List, Optional, Set

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class XrayConfigManager:
    """Manager for Xray configuration file"""

    def __init__(self, config_path: str = "/usr/local/etc/xray/config.json"):
        self.config_path = config_path
        self.config_needs_reload = False  # Flag to track if config changed

    async def read_config(self) -> dict:
        """Read Xray configuration"""
        try:
            with open(self.config_path, 'r') as f:
                return json.load(f)
        except Exception as e:
            logger.error(f"Failed to read config: {e}")
            return {}

    async def write_config(self, config: dict) -> bool:
        """Write Xray configuration"""
        try:
            with open(self.config_path, 'w') as f:
                json.dump(config, f, indent=2)
            return True
        except Exception as e:
            logger.error(f"Failed to write config: {e}")
            return False

    async def get_inbound_users(self, inbound_tag: str) -> Set[str]:
        """Get list of user UUIDs in an inbound"""
        config = await self.read_config()
        inbounds = config.get('inbounds', [])

        for inbound in inbounds:
            if inbound.get('tag') == inbound_tag:
                clients = inbound.get('settings', {}).get('clients', [])
                return {client.get('id') for client in clients if client.get('id')}

        return set()

    async def add_user(self, inbound_tag: str, user_uuid: str, email: str = "", flow: str = "") -> bool:
        """Add a user to an inbound by updating config file"""
        try:
            config = await self.read_config()
            inbounds = config.get('inbounds', [])

            for inbound in inbounds:
                if inbound.get('tag') == inbound_tag:
                    if 'settings' not in inbound:
                        inbound['settings'] = {}
                    if 'clients' not in inbound['settings']:
                        inbound['settings']['clients'] = []

                    clients = inbound['settings']['clients']
                    if any(client.get('id') == user_uuid for client in clients):
                        logger.debug(f"User {user_uuid} already exists in {inbound_tag}")
                        return True

                    new_client = {
                        "id": user_uuid,
                        "email": email or user_uuid,
                        "level": 0,
                        "flow": "xtls-rprx-vision"
                    }
                    clients.append(new_client)

                    if await self.write_config(config):
                        self.config_needs_reload = True  # Mark config as needing reload
                        logger.info(f"✓ Added user {email or user_uuid} to config (reload pending)")
                        return True
                    else:
                        logger.error(f"Failed to write config when adding user {user_uuid}")
                        return False

            logger.error(f"Inbound {inbound_tag} not found in config")
            return False

        except Exception as e:
            logger.error(f"Error adding user: {e}")
            return False

    async def remove_user(self, inbound_tag: str, user_uuid: str) -> bool:
        """Remove a user from an inbound by updating config file"""
        try:
            config = await self.read_config()
            inbounds = config.get('inbounds', [])
            user_email = user_uuid

            for inbound in inbounds:
                if inbound.get('tag') == inbound_tag:
                    clients = inbound.get('settings', {}).get('clients', [])

                    # Find the user's email for logging
                    for client in clients:
                        if client.get('id') == user_uuid:
                            user_email = client.get('email', user_uuid)
                            break

                    # Remove from config
                    original_count = len(clients)
                    inbound['settings']['clients'] = [
                        client for client in clients
                        if client.get('id') != user_uuid
                    ]

                    if len(inbound['settings']['clients']) < original_count:
                        if await self.write_config(config):
                            self.config_needs_reload = True  # Mark config as needing reload
                            logger.info(f"✓ Removed user {user_email} from config (reload pending)")
                            return True
                        else:
                            logger.error(f"Failed to write config when removing user {user_uuid}")
                            return False
                    else:
                        logger.debug(f"User {user_uuid} not found in {inbound_tag}")
                        return True

            logger.error(f"Inbound {inbound_tag} not found in config")
            return False

        except Exception as e:
            logger.error(f"Error removing user: {e}")
            return False

    async def reload_xray(self) -> bool:
        """
        Reload Xray configuration by restarting the service.

        Note: Xray doesn't support graceful reload via SIGHUP. We use restart which
        causes ~1-2s downtime, but this happens max once per 3 minutes (batched changes).
        """
        try:
            # Use nsenter to execute systemctl on host from Docker container
            # This works with privileged: true and pid: host

            # Method 1: Try nsenter to host PID namespace
            cmd = [
                "nsenter", "-t", "1", "-m", "-u", "-i", "-n",
                "systemctl", "restart", "xray"
            ]

            process = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )

            stdout, stderr = await process.communicate()

            if process.returncode == 0:
                self.config_needs_reload = False
                logger.info("✓ Restarted Xray via nsenter systemctl (~1-2s downtime)")
                # Wait a bit for Xray to fully start
                await asyncio.sleep(2)
                return True
            else:
                # Fallback: Try direct systemctl
                logger.warning("nsenter failed, trying direct systemctl...")
                cmd = ["systemctl", "restart", "xray"]

                process = await asyncio.create_subprocess_exec(
                    *cmd,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE
                )

                stdout, stderr = await process.communicate()

                if process.returncode == 0:
                    self.config_needs_reload = False
                    logger.info("✓ Restarted Xray via systemctl (~1-2s downtime)")
                    await asyncio.sleep(2)
                    return True
                else:
                    error_msg = stderr.decode() if stderr else "unknown error"
                    logger.error(f"Failed to restart Xray: {error_msg}")
                    return False

        except Exception as e:
            logger.error(f"Error reloading Xray: {e}")
            return False

    async def validate_and_fix_config(self) -> bool:
        """
        Validate Xray configuration and fix common issues.

        Checks:
        1. All VLESS clients have "flow" parameter set to "xtls-rprx-vision"
        2. Adds missing flow parameters to existing clients

        Returns:
            True if config was modified and fixed, False if no changes needed
        """
        try:
            config = await self.read_config()
            inbounds = config.get('inbounds', [])
            config_modified = False
            fixed_clients = []

            for inbound in inbounds:
                # Only validate VLESS inbounds
                if inbound.get('protocol') != 'vless':
                    continue

                inbound_tag = inbound.get('tag', 'unknown')
                clients = inbound.get('settings', {}).get('clients', [])

                for client in clients:
                    client_id = client.get('id', 'unknown')
                    client_email = client.get('email', client_id)

                    # Check if flow parameter is missing or incorrect
                    current_flow = client.get('flow')

                    if current_flow != 'xtls-rprx-vision':
                        # Fix: add or update flow parameter
                        client['flow'] = 'xtls-rprx-vision'
                        config_modified = True
                        fixed_clients.append(f"{client_email} ({client_id[:8]}...)")

                        if current_flow is None:
                            logger.warning(f"⚠ Fixed missing 'flow' parameter for user {client_email} in {inbound_tag}")
                        else:
                            logger.warning(f"⚠ Fixed incorrect 'flow' parameter for user {client_email} in {inbound_tag}: '{current_flow}' -> 'xtls-rprx-vision'")

            # Write config if modified
            if config_modified:
                if await self.write_config(config):
                    logger.info(f"✓ Config validation complete: Fixed {len(fixed_clients)} client(s)")
                    for client_info in fixed_clients:
                        logger.info(f"  - {client_info}")
                    return True
                else:
                    logger.error("Failed to write fixed config")
                    return False
            else:
                logger.info("✓ Config validation complete: No issues found")
                return False

        except Exception as e:
            logger.error(f"Error validating config: {e}")
            return False

    async def update_sni(self, new_sni: str, inbound_tag: str = "vless-in") -> bool:
        """
        Update SNI in Xray configuration for REALITY

        Args:
            new_sni: New SNI value (e.g., "vk.com")
            inbound_tag: Xray inbound tag to update

        Returns:
            True if updated successfully, False otherwise
        """
        try:
            config = await self.read_config()
            inbounds = config.get('inbounds', [])

            for inbound in inbounds:
                if inbound.get('tag') == inbound_tag:
                    # Update SNI in REALITY settings
                    stream_settings = inbound.get('streamSettings', {})
                    reality_settings = stream_settings.get('realitySettings', {})

                    current_sni = reality_settings.get('serverNames', [])
                    if current_sni and len(current_sni) > 0:
                        current_sni = current_sni[0]
                    else:
                        current_sni = None

                    if current_sni == new_sni:
                        logger.info(f"SNI already set to '{new_sni}', no change needed")
                        return True

                    # Update serverNames
                    reality_settings['serverNames'] = [new_sni]
                    stream_settings['realitySettings'] = reality_settings
                    inbound['streamSettings'] = stream_settings

                    # Write config
                    if await self.write_config(config):
                        self.config_needs_reload = True
                        logger.info(f"✓ Updated SNI from '{current_sni}' to '{new_sni}' (reload pending)")
                        return True
                    else:
                        logger.error("Failed to write config when updating SNI")
                        return False

            logger.error(f"Inbound {inbound_tag} not found in config")
            return False

        except Exception as e:
            logger.error(f"Error updating SNI: {e}")
            return False


class XrayStatsClient:
    """Client for Xray stats API using CLI"""

    def __init__(self, xray_binary: str = "/usr/local/bin/xray", api_address: str = "127.0.0.1:10085"):
        self.xray_binary = xray_binary
        self.api_address = api_address

    async def query_stats(self, pattern: str = "", reset: bool = False) -> List[Dict]:
        """
        Query all stats matching a pattern using Xray CLI

        Args:
            pattern: Pattern to match stats names (e.g., "user>>>")
            reset: Whether to reset counters

        Returns:
            List of stats dicts with 'name' and 'value' keys
        """
        try:
            # Build command: xray api statsquery -s 127.0.0.1:10085 -pattern "user>>>" -reset
            cmd = [
                self.xray_binary,
                "api",
                "statsquery",
                "-s", self.api_address,
                "-pattern", pattern
            ]

            if reset:
                cmd.append("-reset")

            # Run command
            process = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )

            stdout, stderr = await process.communicate()

            if process.returncode != 0:
                logger.error(f"Xray statsquery failed: {stderr.decode()}")
                return []

            # Parse JSON output
            # Xray returns JSON format: {"stat": [{"name": "...", "value": 123}, ...]}
            try:
                data = json.loads(stdout.decode())
                stats = data.get('stat', [])

                # Filter out stats without values and ensure value is present
                result = []
                for stat in stats:
                    name = stat.get('name', '')
                    # value may be missing if counter is 0 or not initialized
                    value = stat.get('value', 0)
                    if name:
                        result.append({'name': name, 'value': value})

                return result
            except json.JSONDecodeError as e:
                logger.error(f"Failed to parse JSON from xray statsquery: {e}")
                return []

        except Exception as e:
            logger.error(f"Error querying stats: {e}")
            return []


class NodeAgent:
    """Node agent for managing Xray and reporting to main server"""

    def __init__(self):
        # Configuration from environment
        self.node_id = os.getenv('NODE_ID')
        self.main_server_url = os.getenv('MAIN_SERVER_URL', 'http://localhost:8000')
        self.api_key = os.getenv('NODE_API_KEY')
        self.sync_interval = int(os.getenv('SYNC_INTERVAL', '30'))  # seconds
        self.health_check_interval = int(os.getenv('HEALTH_CHECK_INTERVAL', '60'))
        self.user_sync_interval = int(os.getenv('USER_SYNC_INTERVAL', '60'))  # seconds
        self.inbound_tag = os.getenv('INBOUND_TAG', 'vless-in')  # Xray inbound tag

        # Xray managers
        self.xray_stats = XrayStatsClient()
        self.xray_config = XrayConfigManager()

        # Session
        self.session: Optional[aiohttp.ClientSession] = None

    async def start(self):
        """Start the node agent"""
        logger.info("Starting Node Agent...")

        # Create aiohttp session
        self.session = aiohttp.ClientSession(
            headers={
                'X-API-Key': self.api_key,
                'Content-Type': 'application/json'
            }
        )

        # Validate and fix Xray configuration on startup
        logger.info("Validating Xray configuration...")
        await self.xray_config.validate_and_fix_config()

        # Register node if not registered
        if not self.node_id:
            await self.register_node()

        # Start background tasks
        tasks = [
            asyncio.create_task(self.sync_traffic_loop()),
            asyncio.create_task(self.health_check_loop()),
            asyncio.create_task(self.sync_users_loop()),
            asyncio.create_task(self.sync_sni_loop()),
            asyncio.create_task(self.reload_xray_loop()),
        ]

        try:
            await asyncio.gather(*tasks)
        except KeyboardInterrupt:
            logger.info("Shutting down...")
        finally:
            await self.session.close()

    async def register_node(self):
        """Register node with main server"""
        logger.info("Registering node with main server...")

        # Get node info
        node_info = {
            'hostname': os.getenv('NODE_HOSTNAME', 'localhost'),
            'ip_address': os.getenv('NODE_IP', '0.0.0.0'),
            'port': int(os.getenv('NODE_PORT', '443')),
            'country': os.getenv('NODE_COUNTRY', 'RU'),
            'country_code': os.getenv('NODE_COUNTRY_CODE', 'RU'),
            'city': os.getenv('NODE_CITY'),
            'name': os.getenv('NODE_NAME', 'Default Node'),
            'public_key': os.getenv('REALITY_PUBLIC_KEY'),
            'short_id': os.getenv('REALITY_SHORT_ID'),
            'sni': os.getenv('NODE_SNI', 'vk.com'),
            'api_url': 'http://node-agent:10085',
        }

        try:
            async with self.session.post(
                f"{self.main_server_url}/api/v1/nodes/register",
                json=node_info
            ) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    self.node_id = data.get('id')
                    logger.info(f"✓ Registered as node {self.node_id}")
                else:
                    logger.error(f"Failed to register node: {resp.status}")
        except Exception as e:
            logger.error(f"Error registering node: {e}")

    async def sync_traffic_loop(self):
        """Periodically sync traffic stats with main server"""
        logger.info(f"Starting traffic sync loop (interval: {self.sync_interval}s)")

        while True:
            try:
                await self.sync_traffic()
                await asyncio.sleep(self.sync_interval)
            except Exception as e:
                logger.error(f"Error in traffic sync loop: {e}")
                await asyncio.sleep(self.sync_interval)

    async def sync_traffic(self):
        """Sync traffic statistics to main server using Xray CLI"""
        if not self.node_id:
            logger.warning("Node not registered, skipping traffic sync")
            return

        # Query all user stats using CLI
        stats = await self.xray_stats.query_stats(pattern="user>>>", reset=True)

        if not stats:
            logger.debug("No traffic stats to sync")
            return

        # Parse stats
        user_traffic = {}
        for stat in stats:
            name = stat.get('name', '')
            value = stat.get('value', 0)

            # Parse: user>>>UUID>>>traffic>>>uplink or downlink
            parts = name.split('>>>')
            if len(parts) != 4 or parts[0] != 'user':
                continue

            user_uuid = parts[1]
            direction = parts[3]  # uplink or downlink

            if user_uuid not in user_traffic:
                user_traffic[user_uuid] = {'upload': 0, 'download': 0}

            if direction == 'uplink':
                user_traffic[user_uuid]['upload'] = value
            elif direction == 'downlink':
                user_traffic[user_uuid]['download'] = value

        # Send to main server
        if user_traffic:
            payload = {
                'node_id': self.node_id,
                'timestamp': datetime.utcnow().isoformat(),
                'user_traffic': user_traffic
            }

            # Log traffic data for debugging
            total_bytes = sum(t['upload'] + t['download'] for t in user_traffic.values())
            logger.info(f"Syncing {len(user_traffic)} users, total: {total_bytes} bytes, data: {user_traffic}")

            try:
                async with self.session.post(
                    f"{self.main_server_url}/api/v1/nodes/{self.node_id}/traffic",
                    json=payload
                ) as resp:
                    if resp.status == 200:
                        logger.info(f"✓ Synced traffic for {len(user_traffic)} users")
                    else:
                        logger.warning(f"Failed to sync traffic: {resp.status}")
            except Exception as e:
                logger.error(f"Error syncing traffic: {e}")

    async def health_check_loop(self):
        """Periodically send health check to main server"""
        logger.info(f"Starting health check loop (interval: {self.health_check_interval}s)")

        while True:
            try:
                await self.send_health_check()
                await asyncio.sleep(self.health_check_interval)
            except Exception as e:
                logger.error(f"Error in health check loop: {e}")
                await asyncio.sleep(self.health_check_interval)

    async def send_health_check(self):
        """Send health check and system stats to main server"""
        if not self.node_id:
            logger.warning("Node not registered, skipping health check")
            return

        # Get system stats
        cpu_percent = psutil.cpu_percent(interval=1)
        memory = psutil.virtual_memory()
        network = psutil.net_io_counters()

        # Count active connections (approximate)
        connections = len(psutil.net_connections(kind='inet'))

        payload = {
            'node_id': self.node_id,
            'timestamp': datetime.utcnow().isoformat(),
            'cpu_usage': cpu_percent,
            'memory_usage': memory.percent,
            'active_connections': connections,
            'is_healthy': True
        }

        try:
            async with self.session.post(
                f"{self.main_server_url}/api/v1/nodes/{self.node_id}/health",
                json=payload
            ) as resp:
                if resp.status == 200:
                    logger.debug("✓ Health check sent successfully")
                else:
                    logger.warning(f"Failed to send health check: {resp.status}")
        except Exception as e:
            logger.error(f"Error sending health check: {e}")

    async def sync_users_loop(self):
        """Periodically sync users from main server to Xray"""
        logger.info(f"Starting user sync loop (interval: {self.user_sync_interval}s)")

        # Initial sync immediately
        await asyncio.sleep(5)  # Wait for registration to complete

        while True:
            try:
                await self.sync_users()
                await asyncio.sleep(self.user_sync_interval)
            except Exception as e:
                logger.error(f"Error in user sync loop: {e}")
                await asyncio.sleep(self.user_sync_interval)

    async def sync_users(self):
        """Sync users from main server and update Xray configuration"""
        if not self.node_id:
            logger.warning("Node not registered, skipping user sync")
            return

        try:
            # Get user list from main server
            async with self.session.get(
                f"{self.main_server_url}/api/v1/nodes/{self.node_id}/users"
            ) as resp:
                if resp.status != 200:
                    logger.error(f"Failed to get users from server: {resp.status}")
                    return

                data = await resp.json()
                server_users = data.get('users', [])

            # Build set of UUIDs from server
            server_uuids: Set[str] = set()
            server_user_map: Dict[str, Dict] = {}  # uuid -> user data

            for user in server_users:
                uuid = user.get('uuid')
                if uuid:
                    server_uuids.add(uuid)
                    server_user_map[uuid] = user

            # Get current users from Xray config
            current_uuids = await self.xray_config.get_inbound_users(self.inbound_tag)

            # Add new users
            users_to_add = server_uuids - current_uuids
            added_count = 0
            for uuid in users_to_add:
                user_data = server_user_map[uuid]
                # Use UUID as email for traffic tracking
                email = uuid

                if await self.xray_config.add_user(
                    inbound_tag=self.inbound_tag,
                    user_uuid=uuid,
                    email=email
                ):
                    added_count += 1

            # Remove users no longer on server
            users_to_remove = current_uuids - server_uuids
            removed_count = 0
            for uuid in users_to_remove:
                if await self.xray_config.remove_user(
                    inbound_tag=self.inbound_tag,
                    user_uuid=uuid
                ):
                    removed_count += 1

            # Log results (reload will happen in periodic reload loop)
            if added_count > 0 or removed_count > 0:
                logger.info(f"✓ User sync complete: added {added_count}, removed {removed_count}, total {len(current_uuids) + added_count - removed_count} (reload scheduled)")
            else:
                logger.debug(f"User sync: no changes (total users: {len(current_uuids)})")

        except Exception as e:
            logger.error(f"Error syncing users: {e}")

    async def sync_sni_loop(self):
        """Periodically sync SNI from main server (every 5 minutes)"""
        sync_interval = 300  # 5 minutes
        logger.info(f"Starting SNI sync loop (interval: {sync_interval}s)")

        # Wait a bit before first check
        await asyncio.sleep(30)

        while True:
            try:
                await self.sync_sni()
                await asyncio.sleep(sync_interval)
            except Exception as e:
                logger.error(f"Error in SNI sync loop: {e}")
                await asyncio.sleep(sync_interval)

    async def sync_sni(self):
        """Sync SNI from main server and update Xray config if changed"""
        if not self.node_id:
            logger.warning("Node not registered, skipping SNI sync")
            return

        try:
            # Get node info from main server
            async with self.session.get(
                f"{self.main_server_url}/api/v1/nodes/{self.node_id}"
            ) as resp:
                if resp.status != 200:
                    logger.error(f"Failed to get node info: {resp.status}")
                    return

                node_data = await resp.json()
                server_sni = node_data.get('sni')

                if not server_sni:
                    logger.debug("No SNI set on server")
                    return

                # Update SNI in config
                await self.xray_config.update_sni(server_sni, self.inbound_tag)

        except Exception as e:
            logger.error(f"Error syncing SNI: {e}")

    async def reload_xray_loop(self):
        """Periodically reload Xray if config changed (every 3 minutes)"""
        reload_interval = 180  # 3 minutes = 180 seconds
        logger.info(f"Starting Xray reload loop (interval: {reload_interval}s)")

        # Wait a bit before first check
        await asyncio.sleep(reload_interval)

        while True:
            try:
                if self.xray_config.config_needs_reload:
                    logger.info("Config changes detected, reloading Xray...")
                    await self.xray_config.reload_xray()
                else:
                    logger.debug("No config changes, skipping reload")

                await asyncio.sleep(reload_interval)
            except Exception as e:
                logger.error(f"Error in reload loop: {e}")
                await asyncio.sleep(reload_interval)


async def main():
    """Main entry point"""
    agent = NodeAgent()
    await agent.start()


if __name__ == "__main__":
    asyncio.run(main())