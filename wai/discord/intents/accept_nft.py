import discord
from xrpl.wallet import Wallet
from wai.discord.chat.state import ChatState
from wai.discord.intents import IntentHandler


class AcceptNFTIntent(IntentHandler):
    async def handle(self, interaction: discord.Interaction, chat: ChatState, wallet: Wallet) -> None:
        await interaction.followup.send(
            "I'll help you accept the NFT! (Implementation placeholder)"
        )
