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

    Prices are not stored here: they live in the Price model
    (one row per observation) so that the history is kept.
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
    """Blocks bulk changes so the history stays append-only."""

    def current(self):
        """Only the newest price of every product in every store."""
        newest = (
            Price.objects.filter(
                product=models.OuterRef("product"), store=models.OuterRef("store")
            )
            .order_by("-recorded_at", "-id")
            .values("pk")[:1]
        )
        return self.filter(pk=models.Subquery(newest))

    def update(self, **kwargs):
        raise ValidationError("Prices are append-only: add a new price instead.")

    def delete(self):
        raise ValidationError("Prices are append-only and cannot be deleted.")


class Price(models.Model):
    """One observed price of a product in a store at a moment in time.

    The table is append-only: a price change is a NEW row, old rows are
    never edited or removed. This is what makes price history and
    charts possible later.
    """

    product = models.ForeignKey(
        Product, on_delete=models.PROTECT, related_name="prices"
    )
    store = models.ForeignKey(
        "locations.Store", on_delete=models.PROTECT, related_name="prices"
    )
    # Price in so'm for one item of the product.
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    recorded_at = models.DateTimeField(default=timezone.now)
    # A promotion is a price row marked as promo, optionally with the
    # last day on which the promo price is valid.
    is_promo = models.BooleanField(default=False)
    promo_ends = models.DateField(null=True, blank=True)

    objects = PriceQuerySet.as_manager()

    class Meta:
        ordering = ["-recorded_at", "-id"]
        get_latest_by = ["recorded_at", "id"]
        indexes = [
            models.Index(
                fields=["product", "store", "-recorded_at"],
                name="price_history_idx",
            ),
        ]
        constraints = [
            models.CheckConstraint(
                condition=models.Q(amount__gt=0), name="price_amount_positive"
            ),
        ]

    def __str__(self):
        return f"{self.product} @ {self.store}: {self.amount} so'm"

    @property
    def is_active_promo(self):
        """True while the promotion is still running."""
        if not self.is_promo:
            return False
        return self.promo_ends is None or self.promo_ends >= timezone.localdate()

    def clean(self):
        if self.promo_ends and not self.is_promo:
            raise ValidationError(
                {"promo_ends": "Only a promo price can have an end date."}
            )

    def save(self, *args, **kwargs):
        if not self._state.adding:
            raise ValidationError("Prices are append-only: add a new price instead.")
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise ValidationError("Prices are append-only and cannot be deleted.")
