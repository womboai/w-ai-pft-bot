# Abstract Intent Handler
from abc import ABC, abstractmethod
from enum import Enum

import discord
from xrpl.wallet import Wallet

from wai.discord.chat.state import ChatState


class IntentType(Enum):
    GENERATE_IMAGE = "generate_image"
    MINT_NFT = "mint_nft"
    ACCEPT_NFT = "accept_nft"
    UNKNOWN = "unknown"


class IntentHandler(ABC):
    @abstractmethod
    async def handle(self, interaction: discord.Interaction, chat: ChatState, wallet: Wallet) -> None:
        """Handle the intent action"""
        pass
