from django import forms

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
