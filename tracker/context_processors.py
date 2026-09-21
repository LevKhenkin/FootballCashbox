from django.conf import settings


def auth_features(request):
    """
    Feature flags for templates.

    Password reset via email is only usable when SMTP is configured.
    """

    return {"password_reset_enabled": bool(getattr(settings, "EMAIL_HOST", ""))}

