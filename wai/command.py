from discord import Message, Interaction, Embed, Color
import asyncio
from typing import TYPE_CHECKING

from loguru import logger
from nodetools.protocols.generic_pft_utilities import GenericPFTUtilities
from nodetools.protocols.openrouter import OpenRouterTool
from tasknode.discord.wallet_seed_manager import WalletSeedManager
from wai.cache import TTLCache
from wai.config import IMAGE_GEN_COST, NFT_MINT_COST
from wai.discord.chat.state import ChatHandler, ChatState
from wai.discord.embed import INFO_EMBED_FIELDS
from wai.discord.intent_classifier import IntentClassifier

if TYPE_CHECKING:
    from tasknode.discord.pft_discord import TaskNodeDiscordBot


class WAICommand(ChatHandler):
    def __init__(self, openrouter: OpenRouterTool, wallet_seed_manager: WalletSeedManager, generic_pft_utilities: GenericPFTUtilities, active_users: TTLCache[int]):
        self._intent_classifier = IntentClassifier(openrouter, generic_pft_utilities)
        self._wallet_seed_manager = wallet_seed_manager
        self._active_users = active_users

    def setup(self, client: "TaskNodeDiscordBot"):
        @client.tree.command(name="wai_chat", description="Start a chat to interact with WOMBO nodes")
        async def chat(interaction: Interaction):
            seed = await client.check_user_seed(interaction)
            if not seed:
                return

            # clear cache of any expired keys
            self._active_users.evict()
            wallet = client.generic_pft_utilities.spawn_wallet_from_seed(seed=seed)

            if interaction.user.id not in self._active_chats:
                logger.debug(f"Creating new chat for {interaction.user.id}")
                self.add_chat(interaction.user.id, ChatState(interaction))
            else:
                await interaction.response.send_message(
                    "You already have an active chat session!"
                )
                return

            chat_state = self.get_chat(interaction.user.id) 
            if chat_state is None:
                logger.error(f"Chat state for user {interaction.user.id} was None when a session was active")
                await interaction.response.send_message(
                    "I couldn't find a chat for you. Try again."
                )
                return

            embed = Embed(title="A Chat has Begun", description="Start chatting with the bot. You have 3 options", color=Color.green())

            for field in INFO_EMBED_FIELDS:
                embed.add_field(**field)

            await interaction.response.send_message(embed=embed)
            
            def check(message: Message) -> bool:
                return (
                    message.author.id == interaction.user.id
                    and message.channel.id == interaction.channel_id
                )

            try:
                while True:
                    # update in cache as active user each time a message is received from them
                    self._active_users.set(wallet.classic_address, interaction.user.id)
                    message = await client.wait_for("message", timeout=120.0, check=check)

                    if message.content.lower() == "exit":
                        self.delete_chat(interaction.user.id)
                        await interaction.followup.send("Chat session ended!")
                        break

                    async with message.channel.typing():
                        chat_state.store_user_message(message.content)
                        handler = await self._intent_classifier.classify(chat_state._message_history)
                        await handler.handle(interaction, chat_state, wallet)
            except asyncio.TimeoutError:
                self.delete_chat(interaction.user.id)
                await interaction.followup.send("Chat session timed out due to inactivity!")
            except Exception as e:
                logger.error(f"Error occured during chat: {e}")
                self.delete_chat(interaction.user.id)
                await interaction.followup.send(f"Encountered an error {str(e)}. Please begin a new chat!")

