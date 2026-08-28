from .base import AIProvider


class FakeAIProvider(AIProvider):

    def generate_response(self, messages) -> str:
        last_message = messages.last()

        return (
            "I'm the VacantHommie assistant. "
            f"I received your message: "
            f"'{last_message.content}'"
        )