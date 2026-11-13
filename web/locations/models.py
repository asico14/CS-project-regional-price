from django.core.exceptions import ValidationError
from django.db import models


class City(models.Model):
    """A city covered by the channel, e.g. Qo'qon or Farg'ona."""

    name = models.CharField(max_length=100, unique=True)
    slug = models.SlugField(max_length=100, unique=True)

    class Meta:
        ordering = ["name"]
        verbose_name_plural = "cities"

    def __str__(self):
        return self.name


class District(models.Model):
    """A district (tuman / mahalla area) inside a city."""

    city = models.ForeignKey(City, on_delete=models.CASCADE, related_name="districts")
    name = models.CharField(max_length=100)

    class Meta:
        ordering = ["city__name", "name"]
        constraints = [
            models.UniqueConstraint(
                fields=["city", "name"], name="unique_district_per_city"
            ),
        ]

    def __str__(self):
        return f"{self.name} ({self.city})"


class Store(models.Model):
    """A shop or market stall whose prices are tracked."""

    name = models.CharField(max_length=150)
    # PROTECT: a city with stores cannot be deleted by accident, because
    # the stores (and later their price history) would be lost with it.
    city = models.ForeignKey(City, on_delete=models.PROTECT, related_name="stores")
    district = models.ForeignKey(
        District,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="stores",
    )
    address = models.CharField(max_length=255, blank=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["city__name", "name"]
        constraints = [
            models.UniqueConstraint(
                fields=["city", "name", "address"], name="unique_store_per_city"
            ),
        ]

    def __str__(self):
        return f"{self.name} ({self.city})"

    def clean(self):
        if self.district_id and self.city_id and self.district.city_id != self.city_id:
            raise ValidationError(
                {"district": "This district belongs to a different city."}
            )
