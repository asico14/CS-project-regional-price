from django import forms
from django.utils import timezone

from .hashtags import build_hashtags
from .models import Post
from .telegram import compose_plain, length_limit, telegram_length


class PostForm(forms.ModelForm):
    """Create/edit a post. The submit button decides draft vs scheduled."""

    ACTION_DRAFT = "draft"
    ACTION_SCHEDULE = "schedule"

    class Meta:
        model = Post
        fields = ["rubric", "language", "city", "title", "body", "extra_tags",
                  "image", "scheduled_at"]
        widgets = {
            "body": forms.Textarea(attrs={"rows": 12}),
            "scheduled_at": forms.DateTimeInput(
                attrs={"type": "datetime-local"}, format="%Y-%m-%dT%H:%M"
            ),
        }
        help_texts = {
            "scheduled_at": "Leave empty to publish as soon as possible.",
        }

    def __init__(self, *args, action=ACTION_DRAFT, **kwargs):
        super().__init__(*args, **kwargs)
        self.action = action

    def clean_body(self):
        body = self.cleaned_data["body"].strip()
        if not body:
            raise forms.ValidationError("The post needs some text.")
        return body

    def has_image(self):
        image = self.cleaned_data.get("image")
        # ``False`` means the "clear" checkbox was ticked.
        return bool(image) if image is not False else False

    def clean(self):
        cleaned = super().clean()
        if self.errors:
            return cleaned
        hashtags = " ".join(build_hashtags(
            cleaned.get("rubric"),
            cleaned.get("language"),
            cleaned["city"].name if cleaned.get("city") else "",
            cleaned.get("extra_tags", ""),
        ))
        text = compose_plain(cleaned.get("title", ""), cleaned["body"], hashtags)
        length = telegram_length(text)
        limit = length_limit(self.has_image())
        if length > limit:
            where = "a photo caption" if self.has_image() else "a message"
            raise forms.ValidationError(
                f"The post is {length} characters long (with title and "
                f"hashtags); Telegram allows {limit} for {where}. "
                f"Shorten it by {length - limit} characters."
            )
        if self.action == self.ACTION_SCHEDULE and not cleaned.get("scheduled_at"):
            cleaned["scheduled_at"] = timezone.now()
        return cleaned

    def save(self, commit=True):
        post = super().save(commit=False)
        if self.action == self.ACTION_SCHEDULE:
            post.status = Post.Status.SCHEDULED
            post.last_error = ""
        else:
            post.status = Post.Status.DRAFT
        if commit:
            post.save()
        return post
