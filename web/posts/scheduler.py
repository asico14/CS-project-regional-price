"""Scheduler logic used by the worker service.

The worker calls run_once() every few seconds. The important rule is
that a post is never sent to the channel twice, even if two workers
run at the same time or a worker is restarted in the middle.

How that is guaranteed: before sending, a worker must *claim* the post
with one UPDATE statement that only matches a post that is still
"scheduled":

    UPDATE post SET status = 'publishing' WHERE id = ? AND status = 'scheduled'

The database runs this statement atomically, so when two workers try,
exactly one of them changes a row. The other sees "0 rows changed" and
leaves the post alone.
"""

import logging
from datetime import timedelta

from django.utils import timezone

from .models import Post

logger = logging.getLogger(__name__)

BATCH_SIZE = 10
# A post still "publishing" after this long belongs to a worker that died.
STUCK_AFTER = timedelta(minutes=10)
STUCK_MESSAGE = (
    "The worker stopped while publishing this post, so it is unknown whether "
    "it reached the channel. Check the channel before scheduling it again."
)


def due_posts(now=None, limit=BATCH_SIZE):
    """Scheduled posts whose time has come, oldest first."""
    now = now or timezone.now()
    return Post.objects.filter(
        status=Post.Status.SCHEDULED, scheduled_at__lte=now
    ).order_by("scheduled_at", "pk")[:limit]


def claim_post(post_id, now=None):
    """Take a due post for publishing. Returns True for one caller only."""
    now = now or timezone.now()
    changed = Post.objects.filter(
        pk=post_id, status=Post.Status.SCHEDULED, scheduled_at__lte=now
    ).update(status=Post.Status.PUBLISHING, claimed_at=now)
    return changed == 1


def mark_published(post, message_id, now=None):
    Post.objects.filter(pk=post.pk, status=Post.Status.PUBLISHING).update(
        status=Post.Status.PUBLISHED,
        published_at=now or timezone.now(),
        telegram_message_id=message_id,
        error_message="",
    )


def mark_failed(post, error):
    Post.objects.filter(pk=post.pk, status=Post.Status.PUBLISHING).update(
        status=Post.Status.FAILED, error_message=str(error)[:2000]
    )


def fail_stuck_posts(now=None):
    """Posts left in "publishing" by a worker that died become "failed".

    They are NOT sent again automatically: the message may already be
    in the channel, and a person has to look before it is rescheduled.
    """
    now = now or timezone.now()
    return Post.objects.filter(
        status=Post.Status.PUBLISHING, claimed_at__lt=now - STUCK_AFTER
    ).update(status=Post.Status.FAILED, error_message=STUCK_MESSAGE)


def run_once(send, now=None):
    """One pass of the worker: publish every post that is due.

    `send(post)` must send the post to the channel and return the
    Telegram message id, or raise an exception. Returns the number of
    posts published in this pass.
    """
    now = now or timezone.now()
    stuck = fail_stuck_posts(now)
    if stuck:
        logger.warning("Marked %s stuck post(s) as failed", stuck)

    published = 0
    for post in due_posts(now):
        if not claim_post(post.pk, now):
            # Another worker took it, or staff unscheduled it meanwhile.
            continue
        try:
            message_id = send(post)
        except Exception as error:  # one bad post must not stop the others
            logger.exception("Post %s failed", post.pk)
            mark_failed(post, error)
        else:
            mark_published(post, message_id)
            published += 1
            logger.info("Post %s published as message %s", post.pk, message_id)
    return published
