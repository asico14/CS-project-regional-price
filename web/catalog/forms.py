from django import forms
from django.utils import timezone

from locations.models import Store

from .models import Product


class ProductForm(forms.ModelForm):
    class Meta:
        model = Product
        fields = ["name", "brand", "category", "unit", "unit_size", "is_active"]
        help_texts = {
            "unit_size": "How much one item contains, e.g. 0.9 for a 0.9 l bottle.",
        }

    def clean_unit_size(self):
        size = self.cleaned_data["unit_size"]
        if size is not None and size <= 0:
            raise forms.ValidationError("The size must be above zero.")
        return size

    def clean_name(self):
        return " ".join(self.cleaned_data["name"].split())

    def clean_brand(self):
        return " ".join(self.cleaned_data["brand"].split())


class PriceEntryStartForm(forms.Form):
    """Step 1 of the daily price entry: which store and which day."""

    store = forms.ModelChoiceField(
        queryset=Store.objects.filter(is_active=True).select_related("city")
    )
    observed_on = forms.DateField(
        label="Date",
        initial=timezone.localdate,
        widget=forms.DateInput(attrs={"type": "date"}),
    )

    def clean_observed_on(self):
        day = self.cleaned_data["observed_on"]
        if day > timezone.localdate():
            raise forms.ValidationError("Prices cannot be entered for future days.")
        return day


class PriceEntryForm(forms.Form):
    """Step 2: one row of inputs per product; empty rows are skipped.

    Fields are named ``price_<id>``, ``regular_<id>`` and ``until_<id>`` so
    the whole shop can be entered on one page with the keyboard only.
    """

    def __init__(self, *args, products, last_prices=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.products = list(products)
        last_prices = last_prices or {}
        self.rows = []
        for product in self.products:
            pid = product.pk
            self.fields[f"price_{pid}"] = forms.IntegerField(
                required=False, min_value=1, label=str(product),
                widget=forms.NumberInput(attrs={
                    "inputmode": "numeric", "class": "price-input",
                    "placeholder": last_prices.get(pid, ""),
                }),
            )
            self.fields[f"regular_{pid}"] = forms.IntegerField(
                required=False, min_value=1, label="Regular price",
                widget=forms.NumberInput(attrs={"inputmode": "numeric"}),
            )
            self.fields[f"until_{pid}"] = forms.DateField(
                required=False, label="Promo until",
                widget=forms.DateInput(attrs={"type": "date"}),
            )
            self.rows.append({
                "product": product,
                "last_price": last_prices.get(pid),
                "price": self[f"price_{pid}"],
                "regular": self[f"regular_{pid}"],
                "until": self[f"until_{pid}"],
            })

    def clean(self):
        cleaned = super().clean()
        for product in self.products:
            pid = product.pk
            price = cleaned.get(f"price_{pid}")
            regular = cleaned.get(f"regular_{pid}")
            until = cleaned.get(f"until_{pid}")
            if price is None:
                if regular or until:
                    self.add_error(f"price_{pid}", "Enter the price too.")
                continue
            if regular is not None and regular <= price:
                self.add_error(
                    f"regular_{pid}", "Must be above the promotion price."
                )
            if until and regular is None:
                self.add_error(f"until_{pid}", "Only promotions have an end date.")
        return cleaned

    def entered_prices(self):
        """(product, price, regular_price, promo_until) for every filled row."""
        for product in self.products:
            pid = product.pk
            price = self.cleaned_data.get(f"price_{pid}")
            if price is not None:
                yield (
                    product,
                    price,
                    self.cleaned_data.get(f"regular_{pid}"),
                    self.cleaned_data.get(f"until_{pid}"),
                )
