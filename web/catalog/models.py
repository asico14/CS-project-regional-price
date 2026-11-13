from django.db import models


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
