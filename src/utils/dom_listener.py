import logging
import json
from queue import Empty
from time import monotonic, sleep
from threading import current_thread


LOG = logging.getLogger(__name__)


class DepthLogLimiter:
    """Allow one top-of-book DEBUG record per interval and only on change."""

    def __init__(self, interval_seconds=1.0, clock=monotonic, only_on_change=True):
        self.interval_seconds = float(interval_seconds)
        self.clock = clock
        self.only_on_change = only_on_change
        self.last_logged_at = None
        self.last_top = None

    def allow(self, top_of_book):
        best_bid, best_ask, _ = top_of_book
        if best_bid is None or best_ask is None:
            return False
        now = self.clock()
        if self.last_logged_at is not None and now - self.last_logged_at < self.interval_seconds:
            return False
        top = (best_bid, best_ask)
        if self.only_on_change and top == self.last_top:
            return False
        self.last_logged_at = now
        self.last_top = top
        return True

    def is_due(self):
        """Return whether the next status check can emit a record."""
        return (
            self.last_logged_at is None
            or self.clock() - self.last_logged_at >= self.interval_seconds
        )


def _depth_signature(new_quotes, deleted_quotes):
    """Build a stable signature for suppressing immediate duplicate packets."""
    return json.dumps(
        {"newQuotes": new_quotes, "deletedQuotes": deleted_quotes},
        sort_keys=True,
        separators=(",", ":"),
    )


def dom_stream_worker(
    client,
    book,
    symbol_id=None,
    log_interval_seconds=1.0,
    status_interval_seconds=10.0,
):
    """
       Listens to the 2155 stream and updates the book.
    """
    LOG.info("DOM listener started for symbol %s", symbol_id)
    change_limiter = DepthLogLimiter(log_interval_seconds)
    status_limiter = DepthLogLimiter(status_interval_seconds, only_on_change=False)
    last_signature = None
    last_signature_at = 0.0
    dedupe_window_seconds = 0.1
    total_updates = 0
    total_duplicates = 0
    try:
        while client.is_connected() and getattr(client, "is_listening_dom", False):
            # One socket reader pumps packets. This worker only consumes its queue.
            client.dispatch_messages()

            processed_count = 0
            deduplicated_count = 0
            while True:
                try:
                    event = client.depth_queue.get_nowait()
                except Empty:
                    break

                try:
                    payload = event.get("payload", {})
                    new_quotes = payload.get("newQuotes", [])
                    deleted_quotes = payload.get("deletedQuotes", [])
                    signature = _depth_signature(new_quotes, deleted_quotes)
                    now = monotonic()
                    if signature == last_signature and now - last_signature_at <= dedupe_window_seconds:
                        deduplicated_count += 1
                        continue
                    last_signature = signature
                    last_signature_at = now
                    book.apply_update(new_quotes, deleted_quotes)
                    processed_count += 1
                except Exception:
                    LOG.exception("Malformed depth event ignored")

            total_updates += processed_count
            total_duplicates += deduplicated_count
            if processed_count or deduplicated_count or status_limiter.is_due():
                top_of_book = book.get_top_of_book()
                log_status = status_limiter.allow(top_of_book)
                log_change = change_limiter.allow(top_of_book) if processed_count else False
                if log_status or log_change:
                    metrics = book.snapshot_metrics()
                    log_method = LOG.info if log_status else LOG.debug
                    log_method(
                        "[DEPTH] mode=%s symbol=%s top_bid=%s top_ask=%s spread=%s "
                        "depth_levels=%s updates_total=%s duplicates_suppressed_total=%s",
                        "status" if log_status else "change",
                        symbol_id,
                        metrics["best_bid"],
                        metrics["best_ask"],
                        metrics["spread"],
                        top_of_book[2],
                        total_updates,
                        total_duplicates,
                        extra={
                            "event_type": "depth_update",
                            "symbol_id": symbol_id,
                            "top_bid": metrics["best_bid"],
                            "top_ask": metrics["best_ask"],
                            "depth_levels": top_of_book[2],
                        },
                    )

            sleep(0.001)
    except Exception:
        LOG.exception("DOM listener stopped after an unexpected error")
    finally:
        client.is_listening_dom = False
        if getattr(client, "depth_worker_thread", None) is current_thread():
            client.depth_worker_thread = None
        LOG.info("DOM listener stopped for symbol %s", symbol_id)
