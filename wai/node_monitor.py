import asyncio
import time
import random
from typing import Any, Dict, Optional
import discord
from nodetools.configuration.configuration import get_network_config
from xrpl.asyncio.clients import AsyncWebsocketClient
from xrpl.models import StreamParameter
import xrpl.models.requests
from loguru import logger
import traceback

from xrpl.utils import hex_to_str

from wai.cache import TTLCache
from wai.config import ImageGenType, get_image_node_address, get_nft_node_address, NFTMintType
from wai.discord.chat.state import ChatHandler


class NodeMonitor:
    """Monitors XRPL websocket for real-time transaction updates"""
    def __init__(self, bot: discord.Client, chat_handler: ChatHandler, active_users: TTLCache[int]):
        self._network_config = get_network_config() 
        self._bot = bot
        self._chats = chat_handler
        self._active_users = active_users

        # Websocket configuration
        self._ws_urls = self._network_config.websockets
        self._ws_url_index = 0
        self._url = self._ws_urls[self._ws_url_index]
        logger.debug(f"Using wss endpoint: {self._url}")

        # Client and queue
        self._client = None
        self.monitor_task = None
        self._shutdown = False

        # Error handling parameters
        self.reconnect_delay = 1
        self.max_reconnect_delay = 30
        self.reconnect_attempts = 0
        self.max_reconnect_attempts = 5

        # Ledger monitoring
        self._last_ledger_time = None
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
            if self._client is None:
                raise Exception("Client was None when pinging server")

            response = await self._client.request(xrpl.models.requests.ServerInfo())
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
            if self._last_ledger_time is not None:
                time_since_last_ledger = time.time() - self._last_ledger_time
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

    async def handle_connection_error(self, error_msg: str):
        """Handle connection errors with exponential backoff"""
        logger.error(error_msg)

        self.reconnect_attempts += 1
        if self.reconnect_attempts > self.max_reconnect_attempts:
            self._switch_node()
            self.reconnect_attempts = 0
            self.reconnect_delay = 1

        delay = min(
            self.reconnect_delay * (1 + random.uniform(0, 0.1)),
            self.max_reconnect_delay,
        )
        logger.info(f"Reconnecting in {delay:.1f} seconds...")
        await asyncio.sleep(delay)
        self.reconnect_delay = min(self.reconnect_delay * 2, self.max_reconnect_delay)

    def _switch_node(self):
        """Switch to next available WebSocket endpoint"""
        self._ws_url_index = (self._ws_url_index + 1) % len(self._ws_urls)
        self._url = self._ws_urls[self._ws_url_index]
        logger.info(f"Switching to WebSocket endpoint: {self._url}")

    async def monitor(self):
        """Main monitoring loop with error handling"""
        while not self._shutdown:
            try:
                await self._monitor_xrpl()
                # Reset reconnection parameters on successful connection
                self.reconnect_delay = 1
                self.reconnect_attempts = 0
            except Exception as e:
                if self._shutdown:
                    break
                await self.handle_connection_error(
                    f"XRPL monitor error: {e}"
                )

    async def _monitor_xrpl(self):
        """Monitor XRPL for updates"""
        self._last_ledger_time = time.time()

        async with AsyncWebsocketClient(self._url) as self._client:
            accounts = [
                get_image_node_address(),
                get_nft_node_address(),
                self._network_config.issuer_address,
            ]

            # Subscribe to streams
            response = await self._client.request(
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
                async for message in self._client:
                    if self._shutdown:
                        break

                    try:
                        mtype = message.get("type")

                        if mtype == "ledgerClosed":
                            self._last_ledger_time = time.time()
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

    def parse_possible_image(self, memo_type: str, memo_data: str) -> Optional[str]:
        hash: str | None = None
        # NOTE: this is highly dependent on the IMAGE RESPONSE format
        if ImageGenType.IMAGE_GEN_RESPONSE.value in memo_type:
            hash = (
                memo_data.split("Here is your image's IPFS hash: ")[1].strip("`")
            )

        image_string = (
            None if hash is None else (
                    f"Image: https://gateway.pinata.cloud/ipfs/{hash}\n"
                    f"NFT mint URI: ipfs://{hash}"
            )
        )

        return image_string

    def parse_possible_nft(self, memo_type: str, memo_data: str) -> Optional[str]:
        if NFTMintType.NFT_MINT_RESPONSE.value in memo_type:
            return memo_data 

        return None 

    def format_notification(self, tx: Dict[str, Any]) -> str | None:
        """Format the reviewing result for Discord"""
        memos = tx.get("Memos", [])

        if len(memos) > 0:
            memo = memos[0]
            memo = memo.get("Memo", {})
            memo_type = hex_to_str(memo.get("MemoType"))
            memo_data = hex_to_str(memo.get("MemoData"))

            image = self.parse_possible_image(memo_type, memo_data)

            if image is not None:
                return image

            nft_message = self.parse_possible_nft(memo_type, memo_data)

            if nft_message is not None:
                return nft_message

        return None 

    async def _process_transaction(self, tx_message: Dict[str, Any]):
        """Process transaction updates from websocket"""
        try:
            logger.debug(
                f"XRPLWebSocketMonitor: Received transaction {tx_message["hash"]}"
            )

            dest = tx_message["tx_json"].get("Destination")
            if dest is None:
                logger.debug("Unable to find destination address. Skipping.")
                return

            discord_id = self._active_users.get(dest)

            if discord_id is None:
                logger.debug(f"Unable to find discord id for address: {dest}. Skipping.")
                return

            chat = self._chats.get_chat(discord_id)
            notif = self.format_notification(tx_message["tx_json"])

            if notif is None:
                logger.debug("Tx was not a memo tx. Skipping.")
                return

            if chat is None:
                logger.debug(f"Sending notification DM to {discord_id}")
                user = await self._bot.fetch_user(discord_id)
                await user.send(notif)
            else:
                logger.debug(f"Sending followup notification to {discord_id}")
                await chat.send_followup_message(notif)
        except Exception as e:
            logger.error(f"Error processing transaction update: {e}")
            logger.error(traceback.format_exc())
