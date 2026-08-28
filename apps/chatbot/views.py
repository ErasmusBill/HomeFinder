from django.http import JsonResponse
from django.shortcuts import get_object_or_404, render
from django.views.decorators.http import require_POST

from .models import ChatConversation, ChatMessage
from .services import generate_chat_response


def chatbot_page(request):
    return render(
        request,
        "chatbot/chat.html",
    )


@require_POST
def chat_view(request):
    message = request.POST.get("message", "").strip()
    conversation_id = request.POST.get("conversation_id")

    if not message:
        return JsonResponse(
            {
                "error": "Message is required."
            },
            status=400,
        )

    if conversation_id:
        conversation = get_object_or_404(
            ChatConversation,
            id=conversation_id,
            status=ChatConversation.Status.ACTIVE,
        )
    else:
        conversation = ChatConversation.objects.create(
            user=(
                request.user
                if request.user.is_authenticated
                else None
            ),
        )

    ChatMessage.objects.create(
        conversation=conversation,
        role=ChatMessage.Role.USER,
        content=message,
    )

    response = generate_chat_response(conversation)

    ChatMessage.objects.create(
        conversation=conversation,
        role=ChatMessage.Role.ASSISTANT,
        content=response,
    )

    conversation.save(
        update_fields=["updated_at"]
    )

    return JsonResponse(
        {
            "conversation_id": str(conversation.id),
            "response": response,
        }
    )