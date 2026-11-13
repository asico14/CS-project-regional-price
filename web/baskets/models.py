from django.db import models


class Basket(models.Model):
    """A fixed shopping list, e.g. "Haftalik savat" (weekly basket),
    used to compare what the same purchase costs in different stores."""

    name = models.CharField(max_length=150, unique=True)
    description = models.CharField(max_length=255, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return self.name


class BasketItem(models.Model):
    """One product in a basket with the quantity to buy."""

    basket = models.ForeignKey(Basket, on_delete=models.CASCADE, related_name="items")
    product = models.ForeignKey(
        "catalog.Product", on_delete=models.PROTECT, related_name="basket_items"
    )
    quantity = models.DecimalField(max_digits=8, decimal_places=3, default=1)

    class Meta:
        ordering = ["product__name"]
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
