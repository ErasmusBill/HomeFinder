from django.contrib.auth.tokens import PasswordResetTokenGenerator

class EmailVerificationTokenGenerator(PasswordResetTokenGenerator):
    def _make_hash_value(self, user, timestamp):
        # Invalidate token if the email becomes verified or user is inactive
        return f"{user.pk}{timestamp}{user.is_email_verified}"

email_verification_token = EmailVerificationTokenGenerator()