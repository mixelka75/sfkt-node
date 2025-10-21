#!/usr/bin/env python3
"""
Node Agent - Manages Xray node and communicates with main server
"""
import asyncio
import aiohttp
import json
import os
import psutil
import logging
import subprocess
from datetime import datetime
from typing import Dict, List, Optional, Set

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


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

            # Parse output
            # Output format is one line per stat: "stat_name value"
            stats = []
            for line in stdout.decode().strip().split('\n'):
                if not line:
                    continue

                # Parse line: "user>>>uuid>>>traffic>>>uplink 12345"
                parts = line.rsplit(None, 1)  # Split from right, max 1 split
                if len(parts) == 2:
                    name, value_str = parts
                    try:
                        value = int(value_str)
                        stats.append({'name': name, 'value': value})
                    except ValueError:
                        logger.warning(f"Failed to parse value: {value_str}")

            return stats

        except Exception as e:
            logger.error(f"Error querying stats: {e}")
            return []

    async def add_user(self, inbound_tag: str, user_uuid: str, email: str = "") -> bool:
        """
        Add a user to an inbound using Xray CLI

        Args:
            inbound_tag: Tag of the inbound (e.g., "vless-in")
            user_uuid: User's UUID
            email: User email/identifier (optional, for logging)

        Returns:
            True if successful
        """
        try:
            # Build JSON for AddUser command
            # Reference: https://xtls.github.io/config/api.html#adduseroperation
            add_user_request = {
                "tag": inbound_tag,
                "user": {
                    "id": user_uuid,
                    "email": email or f"user_{user_uuid[:8]}",
                    "level": 0,
                    "alterId": 0
                }
            }

            # Use xray api adi (Add Inbound User)
            # Command format: echo '{"tag":"vless-in","user":{...}}' | xray api adi -s 127.0.0.1:10085
            cmd = [
                self.xray_binary,
                "api",
                "adi",
                "-s", self.api_address
            ]

            process = await asyncio.create_subprocess_exec(
                *cmd,
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )

            stdout, stderr = await process.communicate(input=json.dumps(add_user_request).encode())

            if process.returncode != 0:
                logger.error(f"Failed to add user {user_uuid}: {stderr.decode()}")
                return False

            logger.info(f"✓ Added user {email} ({user_uuid})")
            return True

        except Exception as e:
            logger.error(f"Error adding user {user_uuid}: {e}")
            return False

    async def remove_user(self, inbound_tag: str, user_email: str) -> bool:
        """
        Remove a user from an inbound using Xray CLI

        Args:
            inbound_tag: Tag of the inbound (e.g., "vless-in")
            user_email: User email/identifier used when adding

        Returns:
            True if successful
        """
        try:
            # Build JSON for RemoveUser command
            remove_user_request = {
                "tag": inbound_tag,
                "email": user_email
            }

            # Use xray api rmi (Remove Inbound User)
            cmd = [
                self.xray_binary,
                "api",
                "rmi",
                "-s", self.api_address
            ]

            process = await asyncio.create_subprocess_exec(
                *cmd,
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )

            stdout, stderr = await process.communicate(input=json.dumps(remove_user_request).encode())

            if process.returncode != 0:
                logger.error(f"Failed to remove user {user_email}: {stderr.decode()}")
                return False

            logger.info(f"✓ Removed user {user_email}")
            return True

        except Exception as e:
            logger.error(f"Error removing user {user_email}: {e}")
            return False


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

        # Xray stats client
        self.xray_stats = XrayStatsClient()

        # Session
        self.session: Optional[aiohttp.ClientSession] = None

        # Track current users (UUID -> email mapping)
        self.current_users: Dict[str, str] = {}

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

            # Current UUIDs in Xray
            current_uuids = set(self.current_users.keys())

            # Add new users
            users_to_add = server_uuids - current_uuids
            for uuid in users_to_add:
                user_data = server_user_map[uuid]
                email = user_data.get('email', f"user_{uuid[:8]}")

                success = await self.xray_stats.add_user(
                    inbound_tag=self.inbound_tag,
                    user_uuid=uuid,
                    email=email
                )

                if success:
                    self.current_users[uuid] = email

            # Remove users no longer on server
            users_to_remove = current_uuids - server_uuids
            for uuid in users_to_remove:
                email = self.current_users.get(uuid)
                if email:
                    success = await self.xray_stats.remove_user(
                        inbound_tag=self.inbound_tag,
                        user_email=email
                    )

                    if success:
                        del self.current_users[uuid]

            if users_to_add or users_to_remove:
                logger.info(f"✓ User sync complete: added {len(users_to_add)}, removed {len(users_to_remove)}, total {len(self.current_users)}")
            else:
                logger.debug(f"User sync: no changes (total users: {len(self.current_users)})")

        except Exception as e:
            logger.error(f"Error syncing users: {e}")


async def main():
    """Main entry point"""
    agent = NodeAgent()
    await agent.start()


if __name__ == "__main__":
    asyncio.run(main())
