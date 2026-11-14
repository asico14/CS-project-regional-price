from django import forms
from django.utils import timezone

from catalog.models import Product
from locations.models import City

from .formatting import compose_text, limit_for, telegram_length
from .hashtags import build_hashtags
from .models import Post

DATETIME_FORMAT = "%Y-%m-%dT%H:%M"


class PostForm(forms.ModelForm):
    # Staff choose only between these two; the worker sets the rest.
    status = forms.ChoiceField(
        choices=[
            (Post.Status.DRAFT, "Save as draft"),
            (Post.Status.SCHEDULED, "Schedule for publishing"),
        ],
        widget=forms.RadioSelect,
        initial=Post.Status.DRAFT,
    )
    scheduled_at = forms.DateTimeField(
        required=False,
        label="Publish at",
        input_formats=[DATETIME_FORMAT],
        widget=forms.DateTimeInput(
            attrs={"type": "datetime-local"}, format=DATETIME_FORMAT
        ),
        help_text="Tashkent time. Needed only for a scheduled post.",
    )

    class Meta:
        model = Post
        fields = [
            "rubric",
            "language",
            "city",
            "title",
            "text",
            "photo",
            "status",
            "scheduled_at",
        ]
        widgets = {"text": forms.Textarea(attrs={"rows": 10})}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # A failed post is shown as a draft until it is scheduled again.
        if self.instance.pk and self.instance.status == Post.Status.FAILED:
            self.initial["status"] = Post.Status.DRAFT

    def clean_title(self):
        return self.cleaned_data["title"].strip()

    def clean_text(self):
        # Browsers send line breaks as \r\n; Telegram would count both.
        return self.cleaned_data["text"].replace("\r\n", "\n").strip()

    def clean(self):
        cleaned = super().clean()
        self.check_length(cleaned)
        self.check_schedule(cleaned)
        return cleaned

    def check_length(self, cleaned):
        if "title" not in cleaned or "text" not in cleaned:
            return
        hashtags = build_hashtags(
            cleaned.get("rubric"), cleaned.get("language"), cleaned.get("city")
        )
        message = compose_text(cleaned["title"], cleaned["text"], hashtags)
        has_photo = bool(cleaned.get("photo"))
        length, limit = telegram_length(message), limit_for(has_photo)
        if length > limit:
            kind = "a post with a photo" if has_photo else "a text post"
            self.add_error(
                "text",
                f"The post is {length} characters long with title and hashtags; "
                f"Telegram allows {limit} for {kind}. "
                f"Shorten it by {length - limit}.",
            )

    def check_schedule(self, cleaned):
        if cleaned.get("status") != Post.Status.SCHEDULED:
            return
        scheduled_at = cleaned.get("scheduled_at")
        if scheduled_at is None:
            if "scheduled_at" not in self.errors:
                self.add_error(
                    "scheduled_at", "A scheduled post needs a date and time."
                )
        elif scheduled_at <= timezone.now():
            self.add_error("scheduled_at", "The publishing time must be in the future.")

    def _post_clean(self):
        # Django now runs Post.clean(), which has its own "needs a date
        # and time" rule. Keep one message per problem, not two.
        super()._post_clean()
        if len(self.errors.get("scheduled_at", [])) > 1:
            del self.errors["scheduled_at"][1:]

    def save(self, commit=True):
        post = super().save(commit=False)
        # Scheduling again clears the result of the previous attempt.
        post.error_message = ""
        if commit:
            post.save()
        return post


class GeneratorForm(forms.Form):
    """Fields shared by all "generate a post" forms."""

    city = forms.ModelChoiceField(
        queryset=City.objects.all(), required=False, empty_label="Whole valley"
    )
    language = forms.ChoiceField(choices=Post.Language.choices, initial="uz")


class PromotionPostForm(GeneratorForm):
    pass


class PricePostForm(GeneratorForm):
    product = forms.ModelChoiceField(queryset=Product.objects.filter(is_active=True))
    field_order = ["product", "city", "language"]
