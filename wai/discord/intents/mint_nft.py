from decimal import Decimal
import json
import traceback
import discord
from loguru import logger
from nodetools.models.memo_processor import generate_custom_id
from nodetools.protocols.generic_pft_utilities import GenericPFTUtilities
from nodetools.protocols.openrouter import OpenRouterTool
from xrpl.models import Response
from xrpl.wallet import Wallet
from wai.config import NFT_MINT_COST, NFTMintType, get_nft_node_address
from wai.discord.chat.state import ChatState
from wai.discord.chat.utils import format_message_history
from wai.discord.intents import IntentHandler

system_prompt = f"""You are an AI assistant analyzing Discord conversations to handle NFT minting requests. Your role is to track multiple minting requests and their states throughout the conversation.

For each new NFT mint request, you must:
1. Identify if there's a data URI that was given.
2. Track if the user has explicitly confirmed they want to mint the NFT after seeing the cost
3. Only consider the most recent NFT mint request unless the user explicitly references the use of a previous one

Important rules:
- Each new NFT mint request requires its own separate confirmation
- After an NFT mint is executed, that context is closed and shouldn't affect future requests
- Previous confirmations don't carry over to new requests
- The user's confirmation must be in response to seeing the {NFT_MINT_COST} PFT cost provided explicitly by the BOT
- If a user makes a new request, any previous unconfirmed requests are abandoned
- If user has given a data URI for the CURRENT request ensure to retain that for the lifetime of that request
- Accept any data URI meeting the URI spec

For chat logs in the format:
<user>message</user>
<bot>message</bot>

Respond in JSON format with no additional data:
{{
    "has_confirmation": boolean,  // true only if user has explicitly confirmed the CURRENT request after seeing the cost
    "has_enough_info": boolean,  // true if a data URI was given for the CURRENT request
    "data_uri": string,      // data URI used for NFT minting for generation
    "deformed_uri": boolean, // whether the URI is deformed or not matching any URI standard, False if there is no data_uri for the CURRENT request
    "is_new_request": boolean    // true if this appears to be a new NFT mint request rather than a response to a previous one
}}"""


class MintNFTIntent(IntentHandler):
    def __init__(self, openrouter: OpenRouterTool, generic_pft_utilities: GenericPFTUtilities):
        self._openrouter = openrouter
        self._generic_pft_utilities = generic_pft_utilities
        self._model = "anthropic/claude-3.5-sonnet:beta"


    async def transact_nft_mint(self, data_uri: str, interaction: discord.Interaction, wallet: Wallet):
        try:
            request_id = generate_custom_id()
            response = await self._generic_pft_utilities.send_memo(
                wallet_seed_or_wallet=wallet,
                destination=get_nft_node_address(),
                memo_data=data_uri,
                memo_type=request_id + "__" + NFTMintType.NFT_MINT.value,
                pft_amount=Decimal(NFT_MINT_COST),
            )

            if not self._generic_pft_utilities.verify_transaction_response(response):
                if isinstance(response, Response):
                    raise Exception(
                        f"Failed to send PFT transaction: {response.result}"
                    )

                raise Exception(f"Failed to send PFT transaction: {response}")

            # extract response from last memo
            tx_info = self._generic_pft_utilities.extract_transaction_info(response)[
                "clean_string"
            ]
            await interaction.followup.send(
                f"Transaction result: {tx_info}\n**NFT offer incoming...**", ephemeral=True
            )
        except Exception as e:
            logger.error(f"PFTTransactionModal.on_submit: Error sending memo: {e}")
            logger.error(traceback.format_exc())
            await interaction.followup.send(
                f"An error occurred: {str(e)}", ephemeral=True
            )

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

            if analysis["deformed_uri"]:
                await chat.send_followup_message(
                        "The URI you provided is invalid. Please enter a valid URI.",
                    )
                return


            if analysis["has_enough_info"]:
                if analysis["has_confirmation"]:
                    await chat.send_followup_message(
                        "I'll mint an NFT using the URI you provided! Please wait a moment...",
                    )
                    await self.transact_nft_mint(analysis['data_uri'], interaction, wallet)
                else:
                    await chat.send_followup_message(
                        f"Are you sure that you wish to transact {NFT_MINT_COST} PFT for this NFT? "
                        "Here's the URI I will use:\n"
                        f"```{analysis['data_uri']}```",
                    )
            else:
                await chat.send_followup_message(
                    "Could you please provide a data URI that will contain the NFT data.", 
                )
        except Exception as e:
            logger.error(f"Error occured while handling NFT mint intent: {e}")
            await interaction.followup.send(f"Failed to handle NFT request {str(e)}. Please try again.", ephemeral=True)
