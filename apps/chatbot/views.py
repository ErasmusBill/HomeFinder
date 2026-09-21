from django.http import JsonResponse
from django.shortcuts import get_object_or_404, render
from django.utils import timezone
from django.views.decorators.http import require_GET, require_POST

from .models import ChatConversation, ChatMessage
from .services import generate_chat_response


def chatbot_page(request):
    return render(request, "chatbot/chat.html")


@require_GET
def history_view(request):
    """
    Returns existing chat message history for session persistence across page loads.
    """
    conversation_id = request.GET.get("conversation_id")
    conversation = None

    if conversation_id:
        conversation = ChatConversation.objects.filter(
            id=conversation_id,
            status=ChatConversation.Status.ACTIVE,
        ).first()

    if not conversation and request.user.is_authenticated:
        conversation = ChatConversation.objects.filter(
            user=request.user,
            status=ChatConversation.Status.ACTIVE,
        ).first()

    if not conversation:
        return JsonResponse({"conversation_id": None, "messages": []})

    # Associate guest conversation to logged-in user
    if request.user.is_authenticated and not conversation.user:
        conversation.user = request.user
        conversation.save(update_fields=["user"])

    messages_qs = conversation.messages.all().order_by("created_at")
    messages = [
        {
            "id": str(msg.id),
            "role": msg.role,
            "content": msg.content,
            "created_at": msg.created_at.strftime("%I:%M %p"),
        }
        for msg in messages_qs
    ]

    return JsonResponse(
        {
            "conversation_id": str(conversation.id),
            "messages": messages,
        }
    )


@require_POST
def chat_view(request):
    message = request.POST.get("message", "").strip()
    conversation_id = request.POST.get("conversation_id")

    if not message:
        return JsonResponse(
            {"error": "Message is required."},
            status=400,
        )

    if conversation_id:
        conversation = ChatConversation.objects.filter(
            id=conversation_id,
            status=ChatConversation.Status.ACTIVE,
        ).first()
        if not conversation:
            conversation = ChatConversation.objects.create(
                user=request.user if request.user.is_authenticated else None,
            )
    else:
        conversation = ChatConversation.objects.create(
            user=request.user if request.user.is_authenticated else None,
        )

    if request.user.is_authenticated and not conversation.user:
        conversation.user = request.user

    user_msg = ChatMessage.objects.create(
        conversation=conversation,
        role=ChatMessage.Role.USER,
        content=message,
    )

    result = generate_chat_response(conversation)
    response_text = result["response"]
    properties = result.get("properties", [])

    assistant_msg = ChatMessage.objects.create(
        conversation=conversation,
        role=ChatMessage.Role.ASSISTANT,
        content=response_text,
    )

    conversation.save(update_fields=["updated_at"])

    return JsonResponse(
        {
            "conversation_id": str(conversation.id),
            "response": response_text,
            "properties": properties,
            "user_time": user_msg.created_at.strftime("%I:%M %p"),
            "assistant_time": assistant_msg.created_at.strftime("%I:%M %p"),
        }
    )


@require_POST
def clear_history_view(request):
    conversation_id = request.POST.get("conversation_id")
    if conversation_id:
        ChatConversation.objects.filter(id=conversation_id).update(status=ChatConversation.Status.ARCHIVED)
    return JsonResponse({"status": "cleared"})