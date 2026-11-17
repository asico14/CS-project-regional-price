from decimal import Decimal

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.utils import timezone


class Category(models.Model):
    """A product group, e.g. "Sut mahsulotlari" (dairy)."""

    name = models.CharField(max_length=100, unique=True)
    slug = models.SlugField(max_length=100, unique=True)

    class Meta:
        ordering = ["name"]
        verbose_name_plural = "categories"

    def __str__(self):
        return self.name


class Product(models.Model):
    """A product whose price is compared between stores.

    Prices are not stored here: they will live in their own model
    (one row per store and date) so that the history is kept.
    """

    class Unit(models.TextChoices):
        KILOGRAM = "kg", "kg"
        LITRE = "l", "litre"
        PIECE = "pc", "piece"
        PACK = "pack", "pack"

    name = models.CharField(max_length=150)
    brand = models.CharField(max_length=100, blank=True)
    # PROTECT: a category that still has products cannot be deleted.
    category = models.ForeignKey(
        Category, on_delete=models.PROTECT, related_name="products"
    )
    unit = models.CharField(max_length=10, choices=Unit.choices, default=Unit.PIECE)
    # How much of the unit one item contains, e.g. 0.9 for a 0.9 l bottle.
    unit_size = models.DecimalField(max_digits=8, decimal_places=3, default=1)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["name", "brand"]
        constraints = [
            models.UniqueConstraint(
                fields=["name", "brand", "unit", "unit_size"],
                name="unique_product_variant",
            ),
            models.CheckConstraint(
                condition=models.Q(unit_size__gt=0),
                name="product_unit_size_positive",
            ),
        ]

    def __str__(self):
        parts = [self.name]
        if self.brand:
            parts.append(self.brand)
        parts.append(f"{self.unit_size.normalize():f} {self.get_unit_display()}")
        return ", ".join(parts)


class PriceQuerySet(models.QuerySet):
    def latest_first(self):
        return self.order_by("-observed_on", "-created_at", "-id")

    def current(self):
        """The most recent price of every (product, store) pair.

        Prices are append-only, so the "current" price is simply the newest
        row for the pair. SQLite has no DISTINCT ON, so we find the newest id
        per pair with a subquery.
        """
        newest = (
            Price.objects.filter(
                product_id=models.OuterRef("product_id"),
                store_id=models.OuterRef("store_id"),
            )
            .latest_first()
            .values("id")[:1]
        )
        return self.filter(id=models.Subquery(newest))


class Price(models.Model):
    """One observed price of a product in a store on a day.

    The table is an append-only history: a row is never changed after it is
    saved. A correction is a new row, so the price chart keeps every value
    that was ever published.

    Prices are whole so'm (UZS has no coins in use). A promotion is a price
    with a higher ``regular_price``, optionally valid until ``promo_until``.
    """

    product = models.ForeignKey(
        Product, on_delete=models.CASCADE, related_name="prices"
    )
    # PROTECT: deleting a store must not silently wipe its price history.
    store = models.ForeignKey(
        "locations.Store", on_delete=models.PROTECT, related_name="prices"
    )
    price = models.PositiveIntegerField(help_text="Price in so'm.")
    regular_price = models.PositiveIntegerField(
        null=True,
        blank=True,
        help_text="Price before the discount. Fill in only for promotions.",
    )
    promo_until = models.DateField(
        null=True, blank=True, help_text="Last day of the promotion, if known."
    )
    observed_on = models.DateField(default=timezone.localdate)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    objects = PriceQuerySet.as_manager()

    class Meta:
        ordering = ["-observed_on", "-created_at", "-id"]
        indexes = [
            models.Index(
                fields=["product", "store", "observed_on"],
                name="price_product_store_day",
            ),
        ]
        constraints = [
            models.CheckConstraint(
                condition=models.Q(price__gt=0), name="price_positive"
            ),
            models.CheckConstraint(
                condition=models.Q(regular_price__isnull=True)
                | models.Q(regular_price__gt=models.F("price")),
                name="regular_price_above_price",
            ),
            models.CheckConstraint(
                condition=models.Q(promo_until__isnull=True)
                | models.Q(regular_price__isnull=False),
                name="promo_until_only_for_promotions",
            ),
        ]

    def __str__(self):
        return f"{self.product} @ {self.store}: {self.price} so'm ({self.observed_on})"

    @property
    def is_promotion(self):
        if self.regular_price is None:
            return False
        return self.promo_until is None or self.promo_until >= timezone.localdate()

    @property
    def discount_percent(self):
        if not self.regular_price:
            return 0
        return round(100 * (self.regular_price - self.price) / self.regular_price)

    @property
    def unit_price(self):
        """Price per kg / litre / piece, for comparing different pack sizes."""
        return round(Decimal(self.price) / self.product.unit_size)

    def clean(self):
        if self.regular_price is not None and self.regular_price <= self.price:
            raise ValidationError(
                {"regular_price": "The regular price must be above the promotion price."}
            )
        if self.promo_until and self.regular_price is None:
            raise ValidationError(
                {"promo_until": "Only promotions have an end date."}
            )

    def save(self, *args, **kwargs):
        if not self._state.adding:
            raise ValueError("Prices are append-only: add a new Price instead.")
        super().save(*args, **kwargs)
