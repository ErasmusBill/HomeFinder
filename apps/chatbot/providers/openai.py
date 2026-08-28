from django.conf import settings
from openai import OpenAI

from .base import AIProvider


class OpenAIProvider(AIProvider):

    def __init__(self):
        self.client = OpenAI(
            api_key=settings.OPENAI_API_KEY,
        )

    def generate_response(self, messages) -> str:

        input_messages = []

        for message in messages:
            input_messages.append(
                {
                    "role": message.role,
                    "content": message.content,
                }
            )

        response = self.client.responses.create(
            model="gpt-5.5",
            input=input_messages,
        )

        return response.output_text