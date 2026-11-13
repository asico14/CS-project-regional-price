from django import forms
from django.forms import inlineformset_factory

from .models import Basket, BasketItem


class BasketForm(forms.ModelForm):
    class Meta:
        model = Basket
        fields = ["name", "description"]

    def clean_name(self):
        return self.cleaned_data["name"].strip()


class BasketItemForm(forms.ModelForm):
    class Meta:
        model = BasketItem
        fields = ["product", "quantity"]

    def clean_quantity(self):
        quantity = self.cleaned_data["quantity"]
        if quantity <= 0:
            raise forms.ValidationError("Quantity must be greater than zero.")
        return quantity


# Several product rows are edited together with the basket itself.
BasketItemFormSet = inlineformset_factory(
    Basket,
    BasketItem,
    form=BasketItemForm,
    extra=5,
    can_delete=True,
)
