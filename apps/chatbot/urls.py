from django.urls import path

from . import views


app_name = "chatbot"


urlpatterns = [
    path(
        "",
        views.chatbot_page,
        name="page",
    ),
    path(
        "chat/",
        views.chat_view,
        name="chat",
    ),
]