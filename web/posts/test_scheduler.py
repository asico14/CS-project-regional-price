from datetime import timedelta

from django.test import TestCase
from django.utils import timezone

from .models import Post
from .publishing import PublishError, RetryLater
from .scheduler import (
    STUCK_AFTER,
    claim_post,
    due_posts,
    fail_stuck_posts,
    run_once,
)


class SchedulerTestCase(TestCase):
    def setUp(self):
        self.now = timezone.now()

    def post(self, title, minutes=-1, status="scheduled", **extra):
        when = self.now + timedelta(minutes=minutes) if minutes is not None else None
        return Post.objects.create(
            rubric="price", title=title, text="Matn", status=status, scheduled_at=when, **extra
        )

    def statuses(self):
        return dict(Post.objects.values_list("title", "status"))


class FakeChannel:
    """Stands in for Telegram: remembers what was sent."""

    def __init__(self, fail_on=()):
        self.sent = []
        self.fail_on = fail_on

    def send(self, post):
        if post.title in self.fail_on:
            raise RuntimeError(f"Telegram refused {post.title}")
        self.sent.append(post.title)
        return 1000 + len(self.sent)


class DuePostsTests(SchedulerTestCase):
    def test_only_scheduled_posts_whose_time_has_come(self):
        self.post("due")
        self.post("exactly now", minutes=0)
        self.post("future", minutes=5)
        self.post("draft", status="draft")
        self.post("published", status="published")
        self.post("failed", status="failed")
        self.post("publishing", status="publishing")
        self.post("draft without time", minutes=None, status="draft")
        titles = [post.title for post in due_posts(self.now)]
        self.assertEqual(titles, ["due", "exactly now"])

    def test_oldest_first_and_limited(self):
        for minutes in [-5, -30, -1, -10]:
            self.post(f"{minutes}", minutes=minutes)
        self.assertEqual(
            [post.title for post in due_posts(self.now)], ["-30", "-10", "-5", "-1"]
        )
        self.assertEqual([post.title for post in due_posts(self.now, limit=2)], ["-30", "-10"])


class ClaimTests(SchedulerTestCase):
    def test_a_post_can_be_claimed_only_once(self):
        post = self.post("a")
        self.assertTrue(claim_post(post.pk, self.now))
        self.assertFalse(claim_post(post.pk, self.now))
        post.refresh_from_db()
        self.assertEqual((post.status, post.claimed_at), ("publishing", self.now))

    def test_cannot_claim_what_is_not_due(self):
        future = self.post("future", minutes=5)
        draft = self.post("draft", status="draft")
        for post in (future, draft):
            self.assertFalse(claim_post(post.pk, self.now))
        self.assertFalse(claim_post(99999, self.now))
        self.assertEqual(self.statuses(), {"future": "scheduled", "draft": "draft"})


class RunOnceTests(SchedulerTestCase):
    def test_publishes_due_posts_in_order(self):
        self.post("second", minutes=-1)
        self.post("first", minutes=-9)
        self.post("later", minutes=30)
        channel = FakeChannel()
        self.assertEqual(run_once(channel.send, self.now), 2)
        self.assertEqual(channel.sent, ["first", "second"])
        self.assertEqual(
            self.statuses(),
            {"first": "published", "second": "published", "later": "scheduled"},
        )
        first = Post.objects.get(title="first")
        self.assertEqual(first.telegram_message_id, 1001)
        self.assertIsNotNone(first.published_at)

    def test_second_pass_sends_nothing_again(self):
        self.post("a")
        channel = FakeChannel()
        run_once(channel.send, self.now)
        self.assertEqual(run_once(channel.send, self.now), 0)
        self.assertEqual(run_once(channel.send, self.now + timedelta(hours=1)), 0)
        self.assertEqual(channel.sent, ["a"])

    def test_two_workers_at_the_same_moment_send_each_post_once(self):
        """Worker B runs a full pass while worker A is in the middle of
        sending: B must not send what A has already claimed."""
        for title in ["a", "b", "c"]:
            self.post(title)
        worker_b = FakeChannel()
        sent_by_a = []

        def worker_a_send(post):
            run_once(worker_b.send, self.now)  # B wakes up right now
            sent_by_a.append(post.title)
            return 1

        run_once(worker_a_send, self.now)
        everything = sorted(sent_by_a + worker_b.sent)
        self.assertEqual(everything, ["a", "b", "c"])
        self.assertEqual(set(self.statuses().values()), {"published"})

    def test_post_unscheduled_after_selection_is_not_sent(self):
        self.post("a", minutes=-5)
        b = self.post("b", minutes=-1)
        sent = []

        def send(post):
            # While "a" is being sent, staff turn "b" back into a draft.
            Post.objects.filter(pk=b.pk).update(status="draft")
            sent.append(post.title)
            return 1

        run_once(send, self.now)
        self.assertEqual(sent, ["a"])
        self.assertEqual(self.statuses()["b"], "draft")

    def test_failure_is_recorded_and_does_not_stop_other_posts(self):
        self.post("bad", minutes=-9)
        self.post("good", minutes=-1)
        channel = FakeChannel(fail_on=["bad"])
        with self.assertLogs("posts.scheduler", level="ERROR"):
            self.assertEqual(run_once(channel.send, self.now), 1)
        bad = Post.objects.get(title="bad")
        self.assertEqual((bad.status, bad.error_message), ("failed", "RuntimeError: Telegram refused bad"))
        self.assertIsNone(bad.published_at)
        self.assertEqual(self.statuses()["good"], "published")
        # A failed post is not retried by itself.
        self.assertEqual(run_once(channel.send, self.now), 0)

    def test_publishing_clears_an_old_error(self):
        post = self.post("retry", error_message="old problem")
        run_once(FakeChannel().send, self.now)
        post.refresh_from_db()
        self.assertEqual((post.status, post.error_message), ("published", ""))


class StuckPostTests(SchedulerTestCase):
    def test_old_publishing_posts_fail_and_are_not_resent(self):
        old = self.now - STUCK_AFTER - timedelta(seconds=1)
        self.post("stuck", status="publishing", claimed_at=old)
        self.post("in progress", status="publishing", claimed_at=self.now)
        channel = FakeChannel()
        with self.assertLogs("posts.scheduler", level="WARNING"):
            run_once(channel.send, self.now)
        self.assertEqual(channel.sent, [])
        stuck = Post.objects.get(title="stuck")
        self.assertEqual(stuck.status, "failed")
        self.assertIn("Check the channel", stuck.error_message)
        self.assertEqual(self.statuses()["in progress"], "publishing")
        self.assertEqual(fail_stuck_posts(self.now), 0)


class TransitionTests(SchedulerTestCase):
    def test_retry_later_puts_the_post_back_and_stops_the_pass(self):
        self.post("first", minutes=-9)
        self.post("second", minutes=-1)
        calls = []

        def limited(post):
            calls.append(post.title)
            raise RetryLater("Flood control: retry in 30 s")

        with self.assertLogs("posts.scheduler", level="WARNING"):
            self.assertEqual(run_once(limited, self.now), 0)
        self.assertEqual(calls, ["first"])
        first = Post.objects.get(title="first")
        self.assertEqual((first.status, first.claimed_at, first.error_message), ("scheduled", None, ""))
        # Next pass, Telegram accepts again: both go out, in order.
        channel = FakeChannel()
        self.assertEqual(run_once(channel.send, self.now), 2)
        self.assertEqual(channel.sent, ["first", "second"])

    def test_publish_error_message_is_kept_for_staff(self):
        self.post("too long")

        def refuse(post):
            raise PublishError("Shorten the text.")

        with self.assertLogs("posts.scheduler", level="WARNING"):
            run_once(refuse, self.now)
        post = Post.objects.get()
        self.assertEqual((post.status, post.error_message), ("failed", "Shorten the text."))

    def test_finished_posts_are_not_changed_by_late_calls(self):
        from .scheduler import mark_failed, mark_published, release_post

        published = self.post("published", status="published", telegram_message_id=7)
        draft = self.post("draft", status="draft")
        for post in (published, draft):
            mark_failed(post, "late error")
            mark_published(post, 99)
            release_post(post)
        published.refresh_from_db()
        self.assertEqual(
            (published.status, published.telegram_message_id, published.error_message),
            ("published", 7, ""),
        )
        self.assertEqual(self.statuses()["draft"], "draft")
