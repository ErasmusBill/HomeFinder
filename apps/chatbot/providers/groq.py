import json
import logging

from django.conf import settings
from openai import OpenAI, OpenAIError

from .base import AIProvider
from apps.chatbot.tools import search_properties

logger = logging.getLogger(__name__)


PROPERTY_SEARCH_TOOL = {
    "type": "function",
    "function": {
        "name": "search_properties",
        "description": (
            "Search VacantHommie for real rental properties. "
            "Use this tool whenever a user wants to find, search, "
            "browse, or get recommendations for rental properties."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "location": {
                    "type": "string",
                    "description": (
                        "The requested region, district, town, or area. "
                        "Examples: East Legon, Accra, Madina."
                    ),
                },
                "room_type": {
                    "type": "string",
                    "enum": [
                        "apartment",
                        "self_contained",
                        "chamber_and_hall",
                        "guest_house",
                    ],
                    "description": "The type of property requested.",
                },
                "min_price": {
                    "type": "number",
                    "description": "Minimum rental price in Ghana cedis.",
                },
                "max_price": {
                    "type": "number",
                    "description": "Maximum rental price in Ghana cedis.",
                },
                "bedrooms": {
                    "type": "integer",
                    "minimum": 1,
                    "description": "Number of bedrooms requested.",
                },
                "bathrooms": {
                    "type": "integer",
                    "minimum": 1,
                    "description": "Number of bathrooms requested.",
                },
                "is_furnished": {
                    "type": "boolean",
                    "description": "Whether the property must be furnished.",
                },
                "payment_period": {
                    "type": "string",
                    "enum": [
                        "daily",
                        "monthly",
                        "yearly",
                    ],
                    "description": "Rental payment period.",
                },
            },
            "additionalProperties": False,
        },
    },
}


class GroqProvider(AIProvider):

    def __init__(self):
        api_key = (getattr(settings, "GROQ_API_KEY", "") or "").strip()
        if not api_key:
            raise OpenAIError("GROQ_API_KEY is missing or empty in settings.")

        self.client = OpenAI(
            api_key=api_key,
            base_url="https://api.groq.com/openai/v1",
        )

    def generate_response(self, messages) -> dict:
        """
        Returns a dict: {"response": str, "properties": list[dict]}
        """
        collected_properties = []

        try:
            input_messages = [
                {
                    "role": "system",
                    "content": (
                        "You are the VacantHommie AI assistant. "
                        "VacantHommie is a property rental platform. "
                        "Help users find suitable rental properties. "
                        "Use the search_properties tool whenever actual "
                        "property listings are required. "
                        "Never invent property listings, prices, locations, "
                        "availability, or amenities. "
                        "Only recommend properties returned by the tool. "
                        "If the tool returns no properties, clearly tell the "
                        "user that no matching properties were found."
                    ),
                }
            ]

            # Add previous conversation messages.
            for message in messages:
                input_messages.append(
                    {
                        "role": message.role,
                        "content": message.content,
                    }
                )

            model_name = getattr(settings, "GROQ_CHAT_MODEL", "llama-3.3-70b-versatile")

            # First request: Let Groq decide whether it needs a tool.
            response = self.client.chat.completions.create(
                model=model_name,
                messages=input_messages,
                tools=[PROPERTY_SEARCH_TOOL],
                tool_choice="auto",
            )

            assistant_message = response.choices[0].message

            # No tool call required
            if not assistant_message.tool_calls:
                return {
                    "response": assistant_message.content or "",
                    "properties": [],
                }

            # Add Groq's tool-call message to the conversation.
            input_messages.append(
                assistant_message.model_dump(
                    exclude_none=True
                )
            )

            # Execute requested tools
            for tool_call in assistant_message.tool_calls:
                tool_name = tool_call.function.name

                if tool_name != "search_properties":
                    continue

                try:
                    arguments = json.loads(
                        tool_call.function.arguments
                    )
                except json.JSONDecodeError:
                    arguments = {}

                logger.debug(f"AI TOOL CALL: {tool_name} {arguments}")

                results = search_properties(**arguments)

                logger.debug(f"TOOL RESULT: {results}")

                # Collect structured property data for the frontend
                collected_properties.extend(results)

                input_messages.append(
                    {
                        "role": "tool",
                        "tool_call_id": tool_call.id,
                        "content": json.dumps(results),
                    }
                )

            # Second request: Groq receives tool results and creates final response.
            final_response = self.client.chat.completions.create(
                model=model_name,
                messages=input_messages,
                tools=[PROPERTY_SEARCH_TOOL],
                tool_choice="auto",
            )

            final_message = final_response.choices[0].message

            return {
                "response": final_message.content or "",
                "properties": collected_properties,
            }
        except Exception as exc:
            logger.error(f"Groq API error during chat response generation: {exc}", exc_info=True)
            return {
                "response": (
                    "I apologize, but I am currently experiencing technical difficulties "
                    "connecting to the AI service. Please try again shortly."
                ),
                "properties": [],
            }