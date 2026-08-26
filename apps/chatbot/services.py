from openai import OpenAI
from django.conf import settings

client = OpenAI(
    api_key=settings.OPENAI_API_KEY,
)

def generate_chat_response(message:str):
    response = client.responses.create(
        model="gpt-5.6",
        input=message,
    )
    return response.output_text


