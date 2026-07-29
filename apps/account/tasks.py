from celery import shared_task
from django.contrib.auth.tokens import default_token_generator
from django.core.mail import send_mail
from django.conf import settings
from django.utils.http import urlsafe_base64_encode
from django.utils.encoding import force_bytes
from django.contrib.auth import get_user_model
from .tokens import email_verification_token

User = get_user_model()


@shared_task(bind=True, max_retries=3)
def send_activation_email_task(self, user_id):
    try:
        user = User.objects.get(pk=user_id)

        # Generate UID and secure token
        uid = urlsafe_base64_encode(force_bytes(user.pk))
        token = email_verification_token.make_token(user)

        # Construct link (adjust domain/frontend URL as needed)
        verification_url = f"{settings.FRONTEND_URL}/verify-email/?uid={uid}&token={token}"

        subject = "Activate your account"
        message = f"Hi {user.full_name},\n\nPlease click the link below to verify your email address:\n{verification_url}\n\nThank you!"

        send_mail(
            subject,
            message,
            settings.DEFAULT_FROM_EMAIL,
            [user.email],
            fail_silently=False,
        )
    except User.DoesNotExist:
        # User was somehow deleted before the task ran
        pass
    except Exception as exc:
        # Retry the task up to 3 times if email server fails temporarily
        raise self.retry(exc=exc, countdown=60)


@shared_task(bind=True, max_retries=3)
def send_password_reset_email_task(self, user_id):
    try:
        user = User.objects.get(pk=user_id)

        # Generate UID and token
        uid = urlsafe_base64_encode(force_bytes(user.pk))
        token = default_token_generator.make_token(user)

        # Construct reset URL
        reset_url = f"{settings.FRONTEND_URL}/reset-password/?uid={uid}&token={token}"

        subject = "Reset Your Password"
        message = f"Hi {user.full_name},\n\nWe received a request to reset your password. Click the link below to set a new password:\n{reset_url}\n\nIf you didn't request this, please ignore this email."

        send_mail(
            subject,
            message,
            settings.DEFAULT_FROM_EMAIL,
            [user.email],
            fail_silently=False,
        )
    except User.DoesNotExist:
        pass
    except Exception as exc:
        raise self.retry(exc=exc, countdown=60)