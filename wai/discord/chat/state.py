from dataclasses import dataclass
from typing import List, Literal, Sequence

from discord import Client, Interaction
from nodetools.configuration.configuration import global_constants


@dataclass
class ChatMessage:
    sender: Literal["user", "bot"]
    content: str


class ChatState:
    def __init__(self):
        self._message_history: List[ChatMessage] = []

    async def send_response_message(
        self, content: str, interaction: Interaction[Client]
    ):
        await interaction.response.send_message(content)
        self._message_history.append(ChatMessage(sender="bot", content=content))
        self.clean_history()

    async def send_followup_message(
        self, content: str, interaction: Interaction[Client]
    ):
        await interaction.followup.send(content)
        self._message_history.append(ChatMessage(sender="bot", content=content))
        self.clean_history()

    def store_user_message(self, content: str):
        self._message_history.append(ChatMessage(sender="user", content=content))
        self.clean_history()

    def get_message_history(self) -> Sequence[ChatMessage]:
        return self._message_history

    def clean_history(self):
        if len(self._message_history) > global_constants.MAX_HISTORY:
            del self._message_history[0]

