from django.conf import settings
from django.db import models


class Basket(models.Model):
    """A shopping list, e.g. "Weekly family basket", compared across stores."""

    name = models.CharField(max_length=150, unique=True)
    description = models.TextField(blank=True)
    is_active = models.BooleanField(default=True)
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
        ordering = ["name"]

    def __str__(self):
        return self.name


class BasketItem(models.Model):
    """A product and how much of it the basket contains."""

    basket = models.ForeignKey(Basket, on_delete=models.CASCADE, related_name="items")
    # PROTECT: removing a product must not silently change saved baskets.
    product = models.ForeignKey(
        "catalog.Product", on_delete=models.PROTECT, related_name="basket_items"
    )
    quantity = models.DecimalField(
        max_digits=8,
        decimal_places=3,
        default=1,
        help_text="Number of items (packs, bottles, kg as sold).",
    )

    class Meta:
        ordering = ["product__category__name", "product__name"]
        constraints = [
            models.UniqueConstraint(
                fields=["basket", "product"], name="unique_product_per_basket"
            ),
            models.CheckConstraint(
                condition=models.Q(quantity__gt=0), name="basket_quantity_positive"
            ),
        ]

    def __str__(self):
        return f"{self.quantity.normalize():f} × {self.product}"
