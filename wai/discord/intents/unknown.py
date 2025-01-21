import discord
from xrpl.wallet import Wallet
from wai.discord.chat.state import ChatState
from wai.discord.embed import INFO_EMBED_FIELDS
from wai.discord.intents import IntentHandler


class UnknownIntent(IntentHandler):
    async def handle(self, interaction: discord.Interaction, chat: ChatState, wallet: Wallet) -> None:
        embed = discord.Embed(
            title="Reminder", 
            description="When chatting with the bot you have 3 options", 
            color=discord.Color.green()
        )
        for field in INFO_EMBED_FIELDS:
            embed.add_field(**field)

        await interaction.followup.send(embed=embed)
