from django.test import TestCase, override_settings
from apps.chatbot.models import ChatConversation, ChatMessage
from apps.chatbot.providers.fake import FakeAIProvider
from apps.chatbot.services import get_ai_provider, generate_chat_response


class ChatbotProviderTestCase(TestCase):
    @override_settings(CHATBOT_AI_PROVIDER="fake", GROQ_API_KEY="")
    def test_get_ai_provider_fake_fallback(self):
        provider = get_ai_provider()
        self.assertIsInstance(provider, FakeAIProvider)

    @override_settings(CHATBOT_AI_PROVIDER="groq", GROQ_API_KEY="")
    def test_get_ai_provider_groq_without_key_falls_back_to_fake(self):
        provider = get_ai_provider()
        self.assertIsInstance(provider, FakeAIProvider)

    @override_settings(CHATBOT_AI_PROVIDER="fake")
    def test_generate_chat_response_with_fake_provider(self):
        conversation = ChatConversation.objects.create()
        ChatMessage.objects.create(
            conversation=conversation,
            role=ChatMessage.Role.USER,
            content="Hello assistant",
        )
        response = generate_chat_response(conversation)
        self.assertIsInstance(response, dict)
        self.assertIn("response", response)
        self.assertIn("properties", response)
        self.assertIn("VacantHommie assistant", response["response"])
        self.assertIn("Hello assistant", response["response"])
        self.assertEqual(response["properties"], [])
