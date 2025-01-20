from typing import Dict, List
from loguru import logger
from nodetools.protocols.generic_pft_utilities import GenericPFTUtilities
from nodetools.protocols.openrouter import OpenRouterTool

from wai.discord.chat.state import ChatMessage
from wai.discord.chat.utils import format_message_history
from wai.discord.intents import IntentHandler, IntentType
from wai.discord.intents.accept_nft import AcceptNFTIntent
from wai.discord.intents.generate_image import GenerateImageIntent
from wai.discord.intents.mint_nft import MintNFTIntent
from wai.discord.intents.unknown import UnknownIntent


classification_prompt = f"""You are an intent classifier. 
 Classify the user's message into one of these intents: 
 - {IntentType.GENERATE_IMAGE.name}
 - {IntentType.MINT_NFT.name}
 - {IntentType.ACCEPT_NFT.name}
 - {IntentType.UNKNOWN.name}

 Respond with ONLY the intent name, nothing else."""


class IntentClassifier:
    def __init__(
            self,
            openrouter: OpenRouterTool,
            generic_pft_utilities: GenericPFTUtilities,
            model: str = "anthropic/claude-3.5-sonnet:beta"
    ):
        self._handlers: Dict[IntentType, IntentHandler] = {
            IntentType.GENERATE_IMAGE: GenerateImageIntent(openrouter, generic_pft_utilities),
            IntentType.MINT_NFT: MintNFTIntent(openrouter, generic_pft_utilities),
            IntentType.ACCEPT_NFT: AcceptNFTIntent(),
            IntentType.UNKNOWN: UnknownIntent(),
        }
        self._default_handler = UnknownIntent()
        self._openrouter = openrouter 
        self._model = model 

    async def classify(self, message_history: List[ChatMessage]) -> IntentHandler:
        formatted_history = format_message_history(message_history)

        try:
            content = await self._openrouter.generate_simple_text_output_async(
                model=self._model,
                messages=[
                    {"role": "system", "content": classification_prompt},
                    {
                        "role": "user",
                        "content": formatted_history,
                    },
                ],
                temperature=0,
                max_tokens=100,
            )

            intent = content.strip().upper()
            logger.debug(f"Intent generated: {intent}")
            intent_type: IntentType | None = None

            try:
                intent_type = IntentType[intent]
            except Exception as e:
                logger.error(
                    f"Failed to determine a valid intent type, got {intent}. Defaulting to unknown intent. Error: {e}"
                )

            if intent_type is None:
                return self._default_handler

            return self._handlers[intent_type]

        except Exception as e:
            print(f"Classification error: {e}")
            return self._default_handler
