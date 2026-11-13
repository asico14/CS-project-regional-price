from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.utils import timezone


class Post(models.Model):
    """A post for the Telegram channel.

    Life cycle:  draft -> scheduled -> published
                                   \\-> failed (can be scheduled again)
    The worker service publishes scheduled posts when their time comes.
    """

    class Rubric(models.TextChoices):
        PROMOTION = "promotion", "Promotion"
        PRICE = "price", "Price tracking"
        COMPARISON = "comparison", "Price comparison"
        REVIEW = "review", "Product review"
        LIFEHACK = "lifehack", "Life hack"
        STORE_NEWS = "store_news", "Store news"

    class Status(models.TextChoices):
        DRAFT = "draft", "Draft"
        SCHEDULED = "scheduled", "Scheduled"
        PUBLISHED = "published", "Published"
        FAILED = "failed", "Failed"

    class Language(models.TextChoices):
        UZBEK = "uz", "O'zbekcha"
        RUSSIAN = "ru", "Русский"

    rubric = models.CharField(max_length=20, choices=Rubric.choices)
    language = models.CharField(
        max_length=2, choices=Language.choices, default=Language.UZBEK
    )
    title = models.CharField(max_length=200)
    text = models.TextField()
    photo = models.ImageField(upload_to="posts/%Y/%m/", blank=True)
    # Optional: the city the post is about (used later for hashtags).
    city = models.ForeignKey(
        "locations.City",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="posts",
    )

    status = models.CharField(
        max_length=10, choices=Status.choices, default=Status.DRAFT
    )
    # When the post should go out. Required for scheduled posts.
    scheduled_at = models.DateTimeField(null=True, blank=True)
    # Filled in by the worker.
    published_at = models.DateTimeField(null=True, blank=True, editable=False)
    telegram_message_id = models.BigIntegerField(null=True, blank=True, editable=False)
    error_message = models.TextField(blank=True, editable=False)

    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        editable=False,
        related_name="posts",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            # The worker looks up "scheduled posts whose time has come".
            models.Index(fields=["status", "scheduled_at"], name="post_due_idx"),
        ]
        constraints = [
            models.CheckConstraint(
                condition=~models.Q(status="scheduled")
                | models.Q(scheduled_at__isnull=False),
                name="scheduled_post_has_time",
            ),
        ]

    def __str__(self):
        return f"[{self.get_rubric_display()}] {self.title}"

    def clean(self):
        if self.status == self.Status.SCHEDULED and self.scheduled_at is None:
            raise ValidationError(
                {"scheduled_at": "A scheduled post needs a date and time."}
            )

    @property
    def is_due(self):
        """True when the worker should publish this post now."""
        return (
            self.status == self.Status.SCHEDULED
            and self.scheduled_at is not None
            and self.scheduled_at <= timezone.now()
        )
