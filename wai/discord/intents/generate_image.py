from decimal import Decimal
import traceback
import discord
from loguru import logger
from nodetools.configuration.configuration import json
from nodetools.models.memo_processor import generate_custom_id
from nodetools.protocols.openrouter import OpenRouterTool
from xrpl.wallet import Wallet
from wai.config import IMAGE_GEN_COST, ImageGenType, get_image_node_address
from wai.discord.chat.state import ChatState
from wai.discord.chat.utils import format_message_history
from wai.discord.intents import IntentHandler
from nodetools.protocols.generic_pft_utilities import GenericPFTUtilities, Response

system_prompt = f"""You are an AI assistant analyzing Discord conversations to handle image generation requests. Your role is to track multiple image requests and their states throughout the conversation.

For each new image request, you must:
1. Identify if there's a clear subject or concept to generate (even simple ones like 'a dog' or 'sunset')
2. Track if the user has explicitly confirmed they want to generate the image after seeing the cost
3. Only consider the most recent image request unless the user explicitly references the use of a previous one
4. Create an appropriate image generation prompt once all requirements are met

Important rules:
- Each new image request requires its own separate confirmation
- After an image generation is executed, that context is closed and shouldn't affect future requests
- Previous confirmations don't carry over to new requests
- The confirmation must be in response to seeing the {IMAGE_GEN_COST} PFT cost
- If a user makes a new request, any previous unconfirmed requests are abandoned
- If user has enough info, image prompt must be filled in

For chat logs in the format:
<user>message</user>
<bot>message</bot>

Respond in JSON format with no additional data:
{{
    "has_confirmation": boolean,  // true only if user has explicitly confirmed the CURRENT request after seeing the cost
    "has_enough_info": boolean,  // true if there's at least a basic subject/concept for the most recent request
    "missing_details": [         // empty if has_enough_info is true
        "string"                 // e.g. "need basic description of what to generate"
    ],
    "image_prompt": string,      // prompt for generation if has_enough_info is true
    "is_new_request": boolean    // true if this appears to be a new image request rather than a response to a previous one
}}"""


class GenerateImageIntent(IntentHandler):
    def __init__(self, openrouter: OpenRouterTool, generic_pft_utilities: GenericPFTUtilities):
        self._openrouter = openrouter
        self._generic_pft_utilities = generic_pft_utilities
        self._model = "anthropic/claude-3.5-sonnet:beta"

    async def transact_image_gen(self, prompt: str, wallet: Wallet, interaction: discord.Interaction):
        try:
            request_id = generate_custom_id()
            response = await self._generic_pft_utilities.send_memo(
                wallet_seed_or_wallet=wallet,
                destination=get_image_node_address(),
                memo_data=prompt,
                memo_type=request_id + "__" + ImageGenType.IMAGE_GEN.value,
                pft_amount=Decimal(IMAGE_GEN_COST),
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
                f"Transaction result: {tx_info}", ephemeral=True
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

            if analysis["has_enough_info"]:
                if analysis["has_confirmation"]:
                    # We have enough info to generate an image
                    await chat.send_followup_message(
                        "I'll generate an image based on what you've described!",
                        interaction,
                    )
                    await self.transact_image_gen(analysis["image_prompt"], wallet, interaction)
                else:
                    await chat.send_followup_message(
                        f"Are you sure that you wish to transact {IMAGE_GEN_COST} PFT for this image generation? "
                        "Here's what I understood you want:\n"
                        f"```{analysis['image_prompt']}```",
                        interaction,
                    )
            else:
                # We need more information
                missing_details = "\n".join(
                    f"• {detail}" for detail in analysis["missing_details"]
                )
                await chat.send_followup_message(
                    "I need a bit more information before I can generate your image. "
                    f"Could you please provide these details:\n{missing_details}",
                    interaction,
                )
        except Exception as e:
            logger.error(
                f"Error occured while handling image generation intent for user {interaction.user.id}: {e}"
            )
            await interaction.followup.send(
                f"Failed to handle image generation request {str(e)}. Please try again.", 
                ephemeral=True
            )
