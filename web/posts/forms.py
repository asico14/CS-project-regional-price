from django import forms
from django.db.models import Q
from django.utils import timezone

from baskets.models import Basket
from catalog.models import Price, Product
from locations.models import City, Store

from . import generators
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


class GeneratorForm(forms.Form):
    """Base for the "generate a post" forms: every generator needs a language."""

    kind = None  # set by subclasses; also the form prefix
    title = ""
    help = ""

    language = forms.ChoiceField(choices=Post.Language.choices, initial="uz")

    def __init__(self, *args, **kwargs):
        kwargs.setdefault("prefix", self.kind)
        super().__init__(*args, **kwargs)

    def generate(self):
        raise NotImplementedError


class PromotionGeneratorForm(GeneratorForm):
    kind = "promotion"
    title = "Promotion post"
    help = "One running promotion: new price, old price, discount and end date."

    price = forms.ModelChoiceField(queryset=Price.objects.none(), label="Promotion")

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        today = timezone.localdate()
        self.fields["price"].queryset = (
            Price.objects.current()
            .filter(regular_price__isnull=False, store__is_active=True)
            .filter(Q(promo_until__isnull=True) | Q(promo_until__gte=today))
            .select_related("product", "store__city")
            .order_by("product__name", "store__name")
        )
        self.fields["price"].label_from_instance = lambda p: (
            f"{p.product} — {p.store} — {p.price} so'm (−{p.discount_percent}%)"
        )

    def generate(self):
        data = self.cleaned_data
        return generators.promotion_post(data["price"], data["language"])


class PriceGeneratorForm(GeneratorForm):
    kind = "price"
    title = "Price post"
    help = "Current prices of one product, cheapest store first."

    product = forms.ModelChoiceField(
        queryset=Product.objects.filter(is_active=True).select_related("category")
    )
    city = forms.ModelChoiceField(
        queryset=City.objects.all(), required=False, empty_label="All cities"
    )

    def clean(self):
        cleaned = super().clean()
        if self.errors:
            return cleaned
        try:
            self.post = generators.price_post(
                cleaned["product"], cleaned["language"], cleaned.get("city")
            )
        except ValueError as error:
            raise forms.ValidationError(str(error))
        return cleaned

    def generate(self):
        return self.post


class ComparisonGeneratorForm(GeneratorForm):
    kind = "comparison"
    title = "Basket comparison post"
    help = "Ranks the stores by the price of a whole basket."

    basket = forms.ModelChoiceField(queryset=Basket.objects.filter(is_active=True))
    city = forms.ModelChoiceField(
        queryset=City.objects.all(), required=False, empty_label="All cities"
    )

    def clean(self):
        cleaned = super().clean()
        if self.errors:
            return cleaned
        try:
            self.post = generators.comparison_post(
                cleaned["basket"], cleaned["language"], cleaned.get("city")
            )
        except ValueError as error:
            raise forms.ValidationError(str(error))
        return cleaned

    def generate(self):
        return self.post


class NewStoreGeneratorForm(GeneratorForm):
    kind = "new_store"
    title = "New store post"
    help = "Announces a store whose prices the channel now tracks."

    store = forms.ModelChoiceField(
        queryset=Store.objects.filter(is_active=True)
        .select_related("city")
        .order_by("-created_at")
    )

    def generate(self):
        data = self.cleaned_data
        return generators.new_store_post(data["store"], data["language"])


GENERATOR_FORMS = [
    PromotionGeneratorForm,
    PriceGeneratorForm,
    ComparisonGeneratorForm,
    NewStoreGeneratorForm,
]
