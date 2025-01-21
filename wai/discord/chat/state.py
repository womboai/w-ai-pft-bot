from dataclasses import dataclass
from typing import Dict, List, Literal, Optional, Sequence

from discord import Client, Interaction
from nodetools.configuration.configuration import global_constants


@dataclass
class ChatMessage:
    sender: Literal["user", "bot"]
    content: str


class ChatState:
    def __init__(self, interaction: Interaction[Client]):
        self._message_history: List[ChatMessage] = []
        self.interaction = interaction 

    async def send_response_message(
        self, content: str
    ):
        await self.interaction.response.send_message(content)
        self._message_history.append(ChatMessage(sender="bot", content=content))
        self.clean_history()

    async def send_followup_message(
        self, content: str
    ):
        await self.interaction.followup.send(content)
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


class ChatHandler:
    _active_chats: Dict[int, ChatState] = {}

    def add_chat(self, id: int, chat_state: ChatState):
        self._active_chats[id] = chat_state

    def delete_chat(self, id: int):
        self._active_chats.pop(id)

    def get_chat(self, id: int) -> Optional[ChatState]:
        return self._active_chats.get(id)
    
