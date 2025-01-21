from typing import TYPE_CHECKING 

from loguru import logger
from nodetools.protocols.generic_pft_utilities import GenericPFTUtilities
from nodetools.protocols.openrouter import OpenRouterTool
from tasknode.discord.wallet_seed_manager import WalletSeedManager
from wai.cache import TTLCache
from wai.command import WAICommand
from wai.node_monitor import NodeMonitor

if TYPE_CHECKING:
    from tasknode.discord.pft_discord import TaskNodeDiscordBot


class WAIHandler:
    def __init__(
            self, 
            openrouter: OpenRouterTool, 
            wallet_seed_manager: WalletSeedManager, 
            generic_pft_utilities: GenericPFTUtilities
    ):
        # needs to be at least the length of an active chat
        self._active_users = TTLCache[int](expiration_time=180)
        self._command = WAICommand(
            openrouter, 
            wallet_seed_manager, 
            generic_pft_utilities, 
            self._active_users
        )

    def setup(self, client: "TaskNodeDiscordBot"):
        self._node_monitor = NodeMonitor(
            client, 
            self._command,
            self._active_users
        )
        logger.debug("Start node monitoring")
        self._node_monitor.start()
        self._command.setup(client)
