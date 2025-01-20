from typing import Sequence
from wai.discord.chat.state import ChatMessage


def format_message_history(message_history: Sequence[ChatMessage]) -> str:
    """
    Formats a list of ChatMessages into a standardized string format for LLM consumption.
    Each message is clearly labeled with its sender and content is properly separated.

    Args:
        message_history: List of ChatMessage objects to format

    Returns:
        A formatted string containing the entire conversation history
    """
    formatted_messages = []

    for message in message_history:
        # Create a consistent format with clear role labels and message boundaries
        formatted_message = (
            f"<{message.sender}>\n{message.content.strip()}\n</{message.sender}>"
        )
        formatted_messages.append(formatted_message)

    # Join all messages with a newline separator for clear message boundaries
    return "\n\n".join(formatted_messages)
