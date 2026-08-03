"""Email side of the dual-channel admin messaging (PRD 6.3.3 / 6.6.1):
full email to the registered address; the in-app brief is created by the views.
Follows the same Resend + Celery pattern as Authentication.utils."""

import logging

import resend
from celery import shared_task
from django.conf import settings

resend.api_key = settings.RESEND_API_KEY

CHUNK_LOG_EVERY = 50


def queue_email(task, *args):
    """Queue a Celery email task, tolerating a down/unreachable broker.

    The in-app half of dual-channel messaging must not be lost because the
    email broker is offline (e.g. local dev without Redis) — callers create
    notifications regardless and use the return value to report email status.
    """
    try:
        task.delay(*args)
        return True
    except Exception as e:
        logging.error(f"Email queue unavailable, email not sent: {e}")
        return False


@shared_task(bind=True, max_retries=3, default_retry_delay=60)
def send_admin_email(self, email, subject, body):
    """Single-recipient email from the admin dashboard."""
    try:
        params: resend.Emails.SendParams = {
            "from": settings.DEFAULT_FROM_EMAIL,
            "to": [email],
            "subject": subject,
            "html": f"<p>{body}</p>",
        }
        resend.Emails.send(params)
        logging.info(f"Admin message sent to {email}")
        return True
    except Exception as e:
        logging.error(f"Failed to send admin message to {email}: {e}")
        raise self.retry(exc=e)


@shared_task(bind=True, max_retries=1, default_retry_delay=120)
def send_bulk_admin_email(self, emails, subject, body):
    """Broadcast/segment fan-out in one task; failures on individual
    addresses are logged and skipped so one bad address can't stall a batch."""
    sent = 0
    for i, email in enumerate(emails):
        try:
            params: resend.Emails.SendParams = {
                "from": settings.DEFAULT_FROM_EMAIL,
                "to": [email],
                "subject": subject,
                "html": f"<p>{body}</p>",
            }
            resend.Emails.send(params)
            sent += 1
        except Exception as e:
            logging.error(f"Broadcast: failed to send to {email}: {e}")
        if (i + 1) % CHUNK_LOG_EVERY == 0:
            logging.info(f"Broadcast progress: {i + 1}/{len(emails)}")
    logging.info(f"Broadcast complete: {sent}/{len(emails)} delivered")
    return sent
