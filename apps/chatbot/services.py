import logging
from django.conf import settings

from .models import ChatConversation
from .providers.fake import FakeAIProvider
from .providers.groq import GroqProvider

logger = logging.getLogger(__name__)


def get_ai_provider():
    provider_name = (getattr(settings, "CHATBOT_AI_PROVIDER", "fake") or "fake").lower().strip()

    if provider_name == "groq":
        api_key = (getattr(settings, "GROQ_API_KEY", "") or "").strip()
        if not api_key:
            logger.warning(
                "CHATBOT_AI_PROVIDER is set to 'groq', but GROQ_API_KEY is missing/empty in settings. "
                "Falling back to FakeAIProvider."
            )
            return FakeAIProvider()
        try:
            return GroqProvider()
        except Exception as exc:
            logger.error(f"Failed to initialize GroqProvider ({exc}). Falling back to FakeAIProvider.")
            return FakeAIProvider()

    return FakeAIProvider()


def generate_chat_response(
    conversation: ChatConversation,
) -> dict:
    """
    Returns a dict with:
      - "response": str  (the AI text)
      - "properties": list[dict]  (structured property data for rich cards, may be empty)
    """
    provider = get_ai_provider()

    messages = conversation.messages.all()

    result = provider.generate_response(messages)

    # Provider may return a plain string (FakeAIProvider) or a dict (GroqProvider).
    if isinstance(result, str):
        return {"response": result, "properties": []}
    return result