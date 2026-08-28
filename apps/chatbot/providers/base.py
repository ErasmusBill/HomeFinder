from abc import ABC, abstractmethod


class AIProvider(ABC):
    """
    Base interface for AI providers.

    Every AI provider used by the chatbot should implement
    generate_response().
    """

    @abstractmethod
    def generate_response(self, message) -> str:
        raise NotImplementedError