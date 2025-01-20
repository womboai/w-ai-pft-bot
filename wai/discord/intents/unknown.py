import discord
from xrpl.wallet import Wallet
from wai.discord.chat.state import ChatState
from wai.discord.intents import IntentHandler


class UnknownIntent(IntentHandler):
    async def handle(self, interaction: discord.Interaction, chat: ChatState, wallet: Wallet) -> None:
        await interaction.followup.send(
            "I'm not sure what you want to do. Could you be more specific?"
        )
