"""Apply the security log retention period (SEC-32) and drop old rate-limit counters.

Run daily from cron: ``python manage.py purge_security_events``.
"""

from datetime import timedelta

from django.conf import settings
from django.core.management.base import BaseCommand
from django.utils import timezone

from security import ratelimit
from security.models import SecurityEvent


class Command(BaseCommand):
    help = "Delete security events older than SECURITY_LOG_RETENTION_DAYS and expired rate-limit buckets."

    def handle(self, *args, **options):
        days = settings.SECURITY_LOG_RETENTION_DAYS
        cutoff = timezone.now() - timedelta(days=days)
        # QuerySet.delete bypasses the per-instance guard; the DB trigger still refuses young rows.
        deleted, _ = SecurityEvent.objects.filter(created_at__lt=cutoff).delete()
        buckets = ratelimit.purge_expired()
        self.stdout.write(f"Deleted {deleted} security events older than {days} days and {buckets} rate-limit buckets.")
