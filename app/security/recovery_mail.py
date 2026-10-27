"""Fixed SMTP delivery; credentials are operator configuration, never request data."""
from __future__ import annotations

import smtplib
import ssl
from email.message import EmailMessage

from app.config import get_settings
from app.security.account_recovery import normalize_email


def configured():
    settings = get_settings().security
    if not settings.auth_enabled or not settings.email_recovery_enabled or not settings.smtp_host or not settings.smtp_from:
        return False
    try: normalize_email(settings.smtp_from)
    except ValueError: return False
    return bool(settings.smtp_username) == bool(settings.smtp_password.get_secret_value())


def send_challenge(challenge):
    settings = get_settings().security
    if not configured(): raise RuntimeError('email_service_unavailable')
    address = normalize_email(challenge['address'])
    token = challenge['token']
    if challenge['kind'] not in {'verify', 'reset'}: raise ValueError('email_challenge_kind_invalid')
    message = EmailMessage()
    message['From'] = normalize_email(settings.smtp_from)
    message['To'] = address
    message['Subject'] = 'DeepIntel account verification' if challenge['kind'] == 'verify' else 'DeepIntel password reset'
    message.set_content('Use this one-time code in DeepIntel. It expires in 30 minutes.\n\n' + token + '\n')
    context = ssl.create_default_context()
    timeout = settings.smtp_timeout_seconds
    if settings.smtp_mode == 'tls':
        client = smtplib.SMTP_SSL(settings.smtp_host,settings.smtp_port,timeout=timeout,context=context)
    else:
        client = smtplib.SMTP(settings.smtp_host,settings.smtp_port,timeout=timeout)
    with client:
        if settings.smtp_mode == 'starttls':
            client.ehlo();client.starttls(context=context);client.ehlo()
        if settings.smtp_username:
            client.login(settings.smtp_username,settings.smtp_password.get_secret_value())
        client.send_message(message)
