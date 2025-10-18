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
from datetime import datetime
from typing import Dict, List, Optional

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class XrayStatsClient:
    """Client for Xray stats API"""

    def __init__(self, api_url: str = "http://127.0.0.1:10085"):
        self.api_url = api_url

    async def get_stats(self, name: str, reset: bool = False) -> int:
        """
        Get traffic stats for a specific user or inbound

        Args:
            name: Stats name (e.g., "user>>>uuid>>>traffic>>>uplink")
            reset: Whether to reset the counter after reading

        Returns:
            Traffic value in bytes
        """
        try:
            async with aiohttp.ClientSession() as session:
                payload = {
                    "name": name,
                    "reset": reset
                }
                async with session.post(
                    f"{self.api_url}/command/GetStats",
                    json=payload
                ) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        return data.get('stat', {}).get('value', 0)
                    return 0
        except Exception as e:
            logger.error(f"Error getting stats for {name}: {e}")
            return 0

    async def query_stats(self, pattern: str = "", reset: bool = False) -> List[Dict]:
        """
        Query all stats matching a pattern

        Args:
            pattern: Pattern to match stats names
            reset: Whether to reset counters

        Returns:
            List of stats
        """
        try:
            async with aiohttp.ClientSession() as session:
                payload = {
                    "pattern": pattern,
                    "reset": reset
                }
                async with session.post(
                    f"{self.api_url}/command/QueryStats",
                    json=payload
                ) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        return data.get('stat', [])
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

        # Xray stats client
        self.xray_stats = XrayStatsClient()

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
        """Sync traffic statistics to main server"""
        # Query all user stats
        stats = await self.xray_stats.query_stats(pattern="user>>>", reset=True)

        if not stats:
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
                        logger.debug(f"Synced traffic for {len(user_traffic)} users")
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
                    logger.debug("Health check sent successfully")
                else:
                    logger.warning(f"Failed to send health check: {resp.status}")
        except Exception as e:
            logger.error(f"Error sending health check: {e}")


async def main():
    """Main entry point"""
    agent = NodeAgent()
    await agent.start()


if __name__ == "__main__":
    asyncio.run(main())
