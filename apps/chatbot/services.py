from .models import ChatConversation
from .providers.fake import FakeAIProvider
from .providers.openai import OpenAIProvider


def get_ai_provider():
    provider = getattr(
        __import__("django.conf").conf.settings,
        "CHATBOT_AI_PROVIDER",
        "fake",
    )

    if provider == "openai":
        return OpenAIProvider()

    return FakeAIProvider()


def generate_chat_response(conversation: ChatConversation,) -> str:
    
    provider = get_ai_provider()

    messages = conversation.messages.all()

    return provider.generate_response(messages)