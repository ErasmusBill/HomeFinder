from django.urls import path

from . import views

app_name = "chatbot"

urlpatterns = [
    path("", views.chatbot_page, name="page"),
    path("chat/", views.chat_view, name="chat"),
    path("history/", views.history_view, name="history"),
    path("clear/", views.clear_history_view, name="clear"),
]