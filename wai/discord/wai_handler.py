# standard imports
from discord import Message, Interaction
import asyncio
from typing import TYPE_CHECKING, Dict

from loguru import logger
from nodetools.protocols.generic_pft_utilities import GenericPFTUtilities
from nodetools.protocols.openrouter import OpenRouterTool
from tasknode.discord.wallet_seed_manager import WalletSeedManager
from wai.discord.chat.state import ChatState
from wai.discord.intent_classifier import IntentClassifier
from wai.discord.node_monitor import NodeMonitor

if TYPE_CHECKING:
    from tasknode.discord.pft_discord import TaskNodeDiscordBot


class WAIHandler:
    def __init__(self, openrouter: OpenRouterTool, wallet_seed_manager: WalletSeedManager, generic_pft_utilities: GenericPFTUtilities):
        self._active_chats: Dict[int, ChatState] = {}
        self._intent_classifier = IntentClassifier(openrouter, generic_pft_utilities)
        self._wallet_seed_manager = wallet_seed_manager

    def setup(self, client: "TaskNodeDiscordBot"):
        # self._node_monitor = NodeMonitor(client)
        # logger.debug("Start node monitoring")
        # self._node_monitor.start()

        @client.tree.command(name="wai_chat", description="Start a chat to interact with WOMBO nodes")
        async def chat(interaction: Interaction):
            seed = await client.check_user_seed(interaction)
            if not seed:
                return

            wallet = client.generic_pft_utilities.spawn_wallet_from_seed(seed=seed)


            if interaction.user.id not in self._active_chats:
                self._active_chats[interaction.user.id] = ChatState()
            else:
                await interaction.response.send_message(
                    "You already have an active chat session!"
                )
                return

            chat_state = self._active_chats[interaction.user.id]

            await interaction.response.send_message(
                "Hi! What would you like to do? (generate image, mint NFT, or accept NFT)"
            )

            def check(message: Message) -> bool:
                return (
                    message.author.id == interaction.user.id
                    and message.channel.id == interaction.channel_id
                )

            try:
                while True:
                    message = await client.wait_for("message", timeout=60.0, check=check)

                    if message.content.lower() == "exit":
                        self._active_chats.pop(interaction.user.id)
                        await interaction.followup.send("Chat session ended!")
                        break

                    async with message.channel.typing():
                        chat_state.store_user_message(message.content)
                        handler = await self._intent_classifier.classify(chat_state._message_history)
                        await handler.handle(interaction, chat_state, wallet)

            except asyncio.TimeoutError:
                self._active_chats.pop(interaction.user.id)
                await interaction.followup.send("Chat session timed out due to inactivity!")
            except Exception as e:
                logger.error(f"Error occured during chat: {e}")
                self._active_chats.pop(interaction.user.id)
                await interaction.followup.send("Encountered an unknown error please begin a new chat!")




    async def close(self):
        # await self.node_monitor.stop()
        pass

