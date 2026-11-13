from django import forms

from .models import Product


class ProductForm(forms.ModelForm):
    class Meta:
        model = Product
        fields = ["name", "brand", "category", "unit", "unit_size", "is_active"]
        labels = {"unit_size": "Size", "is_active": "Active (shown in price entry)"}
        help_texts = {
            "unit_size": "How much one item contains, e.g. 0.9 for a 0.9 litre bottle.",
        }

    def clean_name(self):
        return self.cleaned_data["name"].strip()

    def clean_brand(self):
        return self.cleaned_data["brand"].strip()

    def clean_unit_size(self):
        unit_size = self.cleaned_data["unit_size"]
        if unit_size <= 0:
            raise forms.ValidationError("Size must be greater than zero.")
        return unit_size
