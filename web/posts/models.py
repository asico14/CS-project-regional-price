from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.utils import timezone


class Post(models.Model):
    """A message for the Telegram channel.

    Life cycle (``status``)::

        draft ──> scheduled ──> publishing ──> published
          ^           │              │
          └───────────┴──── failed <─┘

    Editors move posts between *draft* and *scheduled*. Only the worker
    moves a post to *publishing* (when it claims it), and then to
    *published* or *failed*. A failed post can be rescheduled.
    """

    class Rubric(models.TextChoices):
        PROMOTION = "promotion", "Promotion"
        PRICE = "price", "Price tracking"
        COMPARISON = "comparison", "Basket comparison"
        REVIEW = "review", "Product review"
        LIFEHACK = "lifehack", "Life hack"
        STORE_NEWS = "store_news", "Store news"

    class Status(models.TextChoices):
        DRAFT = "draft", "Draft"
        SCHEDULED = "scheduled", "Scheduled"
        PUBLISHING = "publishing", "Publishing"
        PUBLISHED = "published", "Published"
        FAILED = "failed", "Failed"

    class Language(models.TextChoices):
        UZBEK = "uz", "O'zbekcha"
        RUSSIAN = "ru", "Русский"

    # Which status changes an editor may make in the web UI.
    EDITOR_TRANSITIONS = {
        Status.DRAFT: {Status.SCHEDULED},
        Status.SCHEDULED: {Status.DRAFT},
        Status.FAILED: {Status.DRAFT, Status.SCHEDULED},
        Status.PUBLISHING: set(),
        Status.PUBLISHED: set(),
    }

    title = models.CharField(
        max_length=200, blank=True, help_text="Shown in bold above the text."
    )
    body = models.TextField("text")
    rubric = models.CharField(max_length=20, choices=Rubric.choices)
    language = models.CharField(
        max_length=2, choices=Language.choices, default=Language.UZBEK
    )
    image = models.ImageField(
        upload_to="posts/%Y/%m/",
        blank=True,
        help_text="Optional photo. With a photo the text limit is 1024 characters.",
    )
    city = models.ForeignKey(
        "locations.City",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="posts",
        help_text="Optional: the city the post is about (adds a hashtag).",
    )

    status = models.CharField(
        max_length=12, choices=Status.choices, default=Status.DRAFT, db_index=True
    )
    scheduled_at = models.DateTimeField(
        null=True, blank=True, help_text="When the worker should publish the post."
    )
    # Filled in by the worker.
    published_at = models.DateTimeField(null=True, blank=True)
    telegram_message_id = models.BigIntegerField(null=True, blank=True)
    attempts = models.PositiveSmallIntegerField(default=0)
    locked_at = models.DateTimeField(
        null=True, blank=True, help_text="When the worker claimed the post."
    )
    last_error = models.TextField(blank=True)

    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            # The worker's "due posts" query: status = scheduled, oldest first.
            models.Index(fields=["status", "scheduled_at"], name="post_due"),
        ]
        constraints = [
            models.CheckConstraint(
                condition=~models.Q(status="scheduled")
                | models.Q(scheduled_at__isnull=False),
                name="scheduled_post_has_time",
            ),
        ]

    def __str__(self):
        return self.title or self.body[:50] or f"Post {self.pk}"

    @property
    def is_editable(self):
        return self.status not in {self.Status.PUBLISHING, self.Status.PUBLISHED}

    def can_change_status(self, new_status):
        return new_status in self.EDITOR_TRANSITIONS.get(self.status, set())

    def clean(self):
        if self.status == self.Status.SCHEDULED and self.scheduled_at is None:
            raise ValidationError({"scheduled_at": "Choose when to publish the post."})

    def schedule(self, when=None):
        """Editor action: queue the post for the worker."""
        if not self.can_change_status(self.Status.SCHEDULED):
            raise ValidationError(f"A {self.status} post cannot be scheduled.")
        self.status = self.Status.SCHEDULED
        self.scheduled_at = when or self.scheduled_at or timezone.now()
        self.last_error = ""
        self.save()

    def unschedule(self):
        """Editor action: take the post back to draft."""
        if not self.can_change_status(self.Status.DRAFT):
            raise ValidationError(f"A {self.status} post cannot go back to draft.")
        self.status = self.Status.DRAFT
        self.save()
