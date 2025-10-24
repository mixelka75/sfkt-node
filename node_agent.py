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
        """Add a user to an inbound using Xray API"""
        try:
            # First, update config file to keep it in sync (for persistence after restart)
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
                        logger.warning(f"User {user_uuid} already exists in {inbound_tag}")
                        return True

                    new_client = {
                        "id": user_uuid,
                        "email": email or user_uuid,
                        "level": 0
                    }
                    clients.append(new_client)
                    await self.write_config(config)
                    break

            # Now use Xray API to add user dynamically (no restart needed)
            # Create temporary JSON file for xray api adu command
            user_config = {
                "tag": inbound_tag,
                "protocol": "vless",
                "settings": {
                    "clients": [
                        {
                            "id": user_uuid,
                            "email": email or user_uuid,
                            "level": 0
                        }
                    ]
                }
            }

            with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
                json.dump(user_config, f)
                temp_file = f.name

            try:
                cmd = [
                    "/usr/local/bin/xray",
                    "api",
                    "adu",
                    "-s", "127.0.0.1:10085",
                    temp_file
                ]

                process = await asyncio.create_subprocess_exec(
                    *cmd,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE
                )

                stdout, stderr = await process.communicate()

                if process.returncode == 0:
                    logger.info(f"✓ Added user {email or user_uuid} ({user_uuid}) to {inbound_tag} via API (no restart)")
                    return True
                else:
                    error_msg = stderr.decode() if stderr else stdout.decode()
                    logger.error(f"Failed to add user via API: {error_msg}")
                    return False
            finally:
                # Clean up temp file
                try:
                    os.unlink(temp_file)
                except:
                    pass

        except Exception as e:
            logger.error(f"Error adding user via API: {e}")
            return False

    async def remove_user(self, inbound_tag: str, user_uuid: str) -> bool:
        """Remove a user from an inbound using Xray API"""
        try:
            # First, get user email from config before removing
            config = await self.read_config()
            inbounds = config.get('inbounds', [])
            user_email = user_uuid  # Default to UUID as email

            for inbound in inbounds:
                if inbound.get('tag') == inbound_tag:
                    clients = inbound.get('settings', {}).get('clients', [])

                    # Find the user's email
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
                        await self.write_config(config)
                    break

            # Now use Xray API to remove user dynamically (no restart needed)
            # Command: xray api rmu -s 127.0.0.1:10085 -tag="vless-in" "email@example.com"
            cmd = [
                "/usr/local/bin/xray",
                "api",
                "rmu",
                "-s", "127.0.0.1:10085",
                f"-tag={inbound_tag}",
                user_email
            ]

            process = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )

            stdout, stderr = await process.communicate()

            if process.returncode == 0:
                logger.info(f"✓ Removed user {user_email} ({user_uuid}) from {inbound_tag} via API (no restart)")
                return True
            else:
                error_msg = stderr.decode() if stderr else stdout.decode()
                logger.error(f"Failed to remove user via API: {error_msg}")
                return False

        except Exception as e:
            logger.error(f"Error removing user via API: {e}")
            return False

    async def reload_xray(self) -> bool:
        """Reload Xray configuration - NO LONGER NEEDED with API-based user management"""
        # With HandlerService API, we don't need to restart Xray
        # Users are added/removed dynamically without service interruption
        logger.info("✓ Using API for user management - no restart required")
        return True


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

        # Register node if not registered
        if not self.node_id:
            await self.register_node()

        # Start background tasks
        tasks = [
            asyncio.create_task(self.sync_traffic_loop()),
            asyncio.create_task(self.health_check_loop()),
            asyncio.create_task(self.sync_users_loop()),
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

            # Log results (no reload needed with API-based management)
            if added_count > 0 or removed_count > 0:
                logger.info(f"✓ User sync complete: added {added_count}, removed {removed_count}, total {len(current_uuids) + added_count - removed_count} (via API, no downtime)")
            else:
                logger.debug(f"User sync: no changes (total users: {len(current_uuids)})")

        except Exception as e:
            logger.error(f"Error syncing users: {e}")


async def main():
    """Main entry point"""
    agent = NodeAgent()
    await agent.start()


if __name__ == "__main__":
    asyncio.run(main())