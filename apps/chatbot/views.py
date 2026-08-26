from django.shortcuts import render

# Create your views here.
from django.http import JsonResponse
from django.views.decorators.http import require_POST

from .services import generate_chat_response


@require_POST
def chat_view(request):
    message = request.POST.get("message", "").strip()

    if not message:
        return JsonResponse(
            {"error": "Message is required."},
            status=400,
        )

    response = generate_chat_response(message)

    return JsonResponse({
        "response": response,
    })