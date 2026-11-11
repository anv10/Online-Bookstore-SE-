"""Measure catalogue search latency under concurrent load (Test Plan FR-2_ST02).

This is the repeatable evidence for the 500-user / 2-second target in NFR-1. It
drives the real URL through the full Django request stack from many threads and
reports the p95 latency, so a regression in the search path shows up as a
failing command instead of a vague claim.
"""

import statistics
import time
from concurrent.futures import ThreadPoolExecutor

from django.core.management.base import BaseCommand, CommandError
from django.test import Client
from django.urls import reverse


class Command(BaseCommand):
    help = "Fire N concurrent search requests and check that p95 latency is under the threshold."

    def add_arguments(self, parser):
        parser.add_argument("--requests", type=int, default=500, help="Total search requests (default 500).")
        parser.add_argument("--workers", type=int, default=50, help="Concurrent workers (default 50).")
        parser.add_argument("--query", default="clean", help="Search term to use.")
        parser.add_argument("--threshold", type=float, default=2.0, help="p95 limit in seconds (NFR-1: 2).")

    def handle(self, *args, **options):
        total = options["requests"]
        workers = max(1, min(options["workers"], total))
        url = reverse("catalog")
        query = options["query"]

        def one(_):
            client = Client()
            started = time.perf_counter()
            response = client.get(url, {"q": query})
            return time.perf_counter() - started, response.status_code

        # Warm the URL and the template cache before timing, like a real steady-state run.
        one(0)

        wall_started = time.perf_counter()
        with ThreadPoolExecutor(max_workers=workers) as pool:
            results = list(pool.map(one, range(total)))
        wall = time.perf_counter() - wall_started

        latencies = sorted(elapsed for elapsed, _ in results)
        failures = [status for _, status in results if status != 200]
        p95 = latencies[max(0, int(round(len(latencies) * 0.95)) - 1)]
        slowest = latencies[-1]
        average = statistics.fmean(latencies)

        self.stdout.write(
            f"{total} searches, {workers} workers, {wall:.2f}s wall time; "
            f"average {average * 1000:.0f}ms, p95 {p95 * 1000:.0f}ms, max {slowest * 1000:.0f}ms"
        )
        if failures:
            raise CommandError(f"{len(failures)} requests returned a non-200 status: {sorted(set(failures))}")
        if p95 > options["threshold"]:
            raise CommandError(f"p95 {p95:.2f}s exceeds the {options['threshold']:.2f}s threshold")
        self.stdout.write(self.style.SUCCESS(f"p95 {p95:.2f}s is within the {options['threshold']:.2f}s threshold"))
