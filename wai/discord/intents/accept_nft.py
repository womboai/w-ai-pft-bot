import json
import discord
from loguru import logger
from nodetools.protocols.openrouter import OpenRouterTool
from xrpl.asyncio.clients import AsyncJsonRpcClient
from xrpl.asyncio.transaction import submit_and_wait
from xrpl.models import NFTokenAcceptOffer
from xrpl.wallet import Wallet
from wai.config import get_https_url
from wai.discord.chat.state import ChatState
from wai.discord.chat.utils import format_message_history
from wai.discord.intents import IntentHandler
from nodetools.protocols.generic_pft_utilities import GenericPFTUtilities 

system_prompt = """You are an AI assistant analyzing Discord conversations to detect NFT offer IDs in user requests.

Your role is to track the current request and determine if it contains an NFT offer ID provided by the user.

For each new request, you must:
1. Check if there's an NFT offer ID provided by the user
2. Track if the user has explicitly confirmed they want to proceed after providing the offer ID
3. Only consider the most recent request

Important rules:
- Each new request requires its own separate confirmation
- After a request is executed, that context is closed and shouldn't affect future requests
- Previous confirmations don't carry over to new requests
- The confirmation must be in response to providing a NFT offer id 
- If a user makes a new request, any previous unconfirmed requests are abandoned
- If has_confirmation is True, there must be an offer_id

For chat logs in the format:
<user>message</user>
<bot>message</bot>

Respond in JSON format with no additional data:
{
   "is_new_request": boolean,   // true if this appears to be a new request rather than a response to a previous one
   "has_confirmation": boolean, // true only if user has explicitly confirmed the CURRENT request and has given an offer_id for the CURRENT request
   "offer_id": string | null    // NFT offer ID if provided in current request, null otherwise
}"""

class AcceptNFTIntent(IntentHandler):
    def __init__(
            self, 
            openrouter: OpenRouterTool, 
            generic_pft_utilities: GenericPFTUtilities, 
    ):
        self._openrouter = openrouter
        self._generic_pft_utilities = generic_pft_utilities
        self._model = "anthropic/claude-3.5-sonnet:beta"
        self._client = AsyncJsonRpcClient(get_https_url())

    async def accept_nft_offer(self, offer_id: str, interaction: discord.Interaction, wallet: Wallet):
        try:
            # Accept offer transaction
            accept_tx = NFTokenAcceptOffer(
                account=wallet.classic_address,
                nftoken_sell_offer=offer_id,
            )

            response = await submit_and_wait(
                accept_tx, wallet=wallet, client=self._client
            )

            if response.result.get("meta", {}).get("TransactionResult") == "tesSUCCESS":
                url = self._generic_pft_utilities.extract_transaction_info(response)[
                    "xrpl_explorer_url"
                ]
                await interaction.followup.send(
                    f"Offer Acceptance successful, Explorer: {url}", 
                    ephemeral=True
                )
            else:
                logger.error(f"Offer acceptance failed with result: {response.result.get('meta', {}).get('TransactionResult')}")
                await interaction.followup.send(
                    f"Offer Acceptance failed: {response.result.get('meta', {}).get('TransactionResult')}", 
                    ephemeral=True
                )
        except Exception as e:
            logger.error(f"Error encountered while accepting NFT offer {e}")
            await interaction.followup.send(f"An error occured: {str(e)}", ephemeral=True)

    async def handle(self, interaction: discord.Interaction, chat: ChatState, wallet: Wallet) -> None:
        formatted_history = format_message_history(chat.get_message_history())

        try:
            content = await self._openrouter.generate_simple_text_output_async(
                model=self._model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": formatted_history},
                ],
            )

            analysis = json.loads(content)

            logger.debug(f"Analysis so far: {analysis}")

            if analysis["offer_id"] is not None:
                if analysis["has_confirmation"]:
                    await chat.send_followup_message(
                        "I'll accept the NFT using the offer ID you provided!",
                        interaction,
                    )
                    await self.accept_nft_offer(analysis['offer_id'], interaction, wallet)
                else:
                    await chat.send_followup_message(
                        f"Are you sure that you wish to accept this NFT? "
                        "Here's the offer ID I will use:\n"
                        f"```{analysis['offer_id']}```",
                        interaction,
                    )
            else:
                await chat.send_followup_message(
                    "Could you please provide an offer ID.",
                    interaction
                )
        except Exception as e:
            logger.error(f"Error occured while handling NFT acceptance intent: {e}")
            await interaction.followup.send(f"Failed to handle NFT acceptance {str(e)}. Please try again.", ephemeral=True)
