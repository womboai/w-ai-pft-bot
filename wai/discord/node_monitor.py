import asyncio
import os
import time
import random
from typing import Any, Dict
import discord
from nodetools.configuration.configuration import XRPL_MAINNET, XRPL_TESTNET
from xrpl.asyncio.clients import AsyncWebsocketClient
from xrpl.models import StreamParameter
import xrpl.models.requests
from loguru import logger
import traceback


# TODO: refactor
class NodeMonitor:
    """Monitors XRPL websocket for real-time transaction updates"""
    def __init__(self, bot: discord.Client):
        ENV = os.getenv("ENV")
        NODE_ADDRESS = os.getenv("NODE_ADDRESS")

        self.network_config = XRPL_TESTNET if ENV != "production" else XRPL_MAINNET
        self.node_address = NODE_ADDRESS or ""
        self.bot = bot

        # Websocket configuration
        self.ws_urls = self.network_config.websockets
        self.ws_url_index = 0
        self.url = self.ws_urls[self.ws_url_index]
        logger.debug(f"Using wss endpoint: {self.url}")

        # Client and queue
        self.client = None
        self.monitor_task = None
        self._shutdown = False

        # Error handling parameters
        self.reconnect_delay = 1
        self.max_reconnect_delay = 30
        self.reconnect_attempts = 0
        self.max_reconnect_attempts = 5

        # Ledger monitoring
        self.last_ledger_time = None
        self.LEDGER_TIMEOUT = 30  # seconds
        self.CHECK_INTERVAL = 4  # match XRPL block time
        self.PING_INTERVAL = 60  # Send ping every 60 seconds
        self.PING_TIMEOUT = 10  # Wait up to 10 seconds for pong

    def start(self):
        """Start the monitor as an asyncio task"""
        self._shutdown = False
        self.monitor_task = asyncio.create_task(
            self.monitor(), name="XRPLWebSocketMonitor"
        )
        return self.monitor_task

    async def stop(self):
        """Signal the monitor to stop and wait for it to complete"""
        self._shutdown = True
        if self.monitor_task:
            self.monitor_task.cancel()  # Cancel the main monitoring loop
            try:
                await self.monitor_task  # Ensure it finishes gracefully
            except asyncio.CancelledError:
                pass
        logger.info("NodeMonitor stopped.")

    async def _ping_server(self):
        """Send ping and wait for response"""
        try:
            if self.client is None:
                raise Exception("Client was None when pinging server")

            response = await self.client.request(xrpl.models.requests.ServerInfo())
            return response.is_successful()
        except Exception as e:
            logger.error(f"Ping failed: {e}")
            return False

    async def _check_timeouts(self):
        """Check for ledger timeouts"""
        last_ping_time = time.time()

        while True:
            await asyncio.sleep(self.CHECK_INTERVAL)

            current_time = time.time()

            # Check ledger updates
            if self.last_ledger_time is not None:
                time_since_last_ledger = time.time() - self.last_ledger_time
                if time_since_last_ledger > self.LEDGER_TIMEOUT:
                    logger.warning(
                        f"No ledger updates for {time_since_last_ledger:.1f} seconds"
                    )
                    raise Exception(
                        f"No ledger updates received for {time_since_last_ledger:.1f} seconds"
                    )

            # Check ping response
            time_since_last_ping = current_time - last_ping_time
            if time_since_last_ping > self.PING_INTERVAL:
                try:
                    async with asyncio.timeout(self.PING_TIMEOUT):
                        is_alive = await self._ping_server()
                        if is_alive:
                            # logger.debug(f"Pinged websocket...")
                            pass
                        else:
                            raise Exception("Ping failed - no valid response")
                    last_ping_time = current_time
                except (asyncio.TimeoutError, Exception) as e:
                    logger.warning(f"Connection check failed: {e}")
                    raise Exception("Connection check failed")

    async def handle_connection_error(self, error_msg: str) -> bool:
        """Handle connection errors with exponential backoff"""
        logger.error(error_msg)

        self.reconnect_attempts += 1
        if self.reconnect_attempts > self.max_reconnect_attempts:
            self._switch_node()
            self.reconnect_attempts = 0
            self.reconnect_delay = 1
            return False

        delay = min(
            self.reconnect_delay * (1 + random.uniform(0, 0.1)),
            self.max_reconnect_delay,
        )
        logger.info(f"Reconnecting in {delay:.1f} seconds...")
        await asyncio.sleep(delay)
        self.reconnect_delay = min(self.reconnect_delay * 2, self.max_reconnect_delay)
        return True

    def _switch_node(self):
        """Switch to next available WebSocket endpoint"""
        self.ws_url_index = (self.ws_url_index + 1) % len(self.ws_urls)
        self.url = self.ws_urls[self.ws_url_index]
        logger.info(f"Switching to WebSocket endpoint: {self.url}")

    async def monitor(self):
        """Main monitoring loop with error handling"""
        while not self._shutdown:
            try:
                await self._monitor_xrpl()
                # Reset reconnection parameters on successful connection
                self.reconnect_delay = 1
                self.reconnect_attempts = 0

            except asyncio.CancelledError:
                break
            except Exception as e:
                if self._shutdown:
                    break
                should_continue = await self.handle_connection_error(
                    f"XRPL monitor error: {e}"
                )
                if not should_continue:
                    break

    async def _monitor_xrpl(self):
        """Monitor XRPL for updates"""
        self.last_ledger_time = time.time()

        async with AsyncWebsocketClient(self.url) as self.client:
            accounts = [
                # Primary node address
                self.node_address,
                self.network_config.issuer_address,
            ]

            # Subscribe to streams
            response = await self.client.request(
                xrpl.models.requests.Subscribe(
                    streams=[StreamParameter.LEDGER],
                    accounts=accounts,
                )
            )

            if not response.is_successful():
                raise Exception(f"Subscription failed: {response.result}")

            # Start timeout checking
            timeout_task = asyncio.create_task(
                self._check_timeouts(), name="XRPLWebSocketMonitorTimeoutTask"
            )

            try:
                async for message in self.client:
                    if self._shutdown:
                        break

                    try:
                        mtype = message.get("type")

                        if mtype == "ledgerClosed":
                            self.last_ledger_time = time.time()
                        elif mtype == "transaction":
                            await self._process_transaction(message)

                    except Exception as e:
                        logger.error(f"Error processing message: {e}")
                        continue

            finally:
                timeout_task.cancel()
                try:
                    await timeout_task
                except asyncio.CancelledError:
                    pass

    async def _process_transaction(self, tx_message: Dict[str, Any]):
        """Process transaction updates from websocket"""
        try:

            logger.debug(
                f"XRPLWebSocketMonitor: Received transaction {tx_message['hash']}"
            )

            # user = self.bot.fetch_user("user")
            # user.send()
            

            # TODO: implement functionality to send transactions as discord messages to user's that match the destination (and possibly sender) address
        except Exception as e:
            logger.error(f"Error processing transaction update: {e}")
            logger.error(traceback.format_exc())
