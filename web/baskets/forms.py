from django import forms
from django.forms import inlineformset_factory

from catalog.models import Product

from .models import Basket, BasketItem


class BasketForm(forms.ModelForm):
    class Meta:
        model = Basket
        fields = ["name", "description", "is_active"]
        widgets = {"description": forms.Textarea(attrs={"rows": 3})}


class BasketItemForm(forms.ModelForm):
    class Meta:
        model = BasketItem
        fields = ["product", "quantity"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["product"].queryset = Product.objects.filter(
            is_active=True
        ).select_related("category")

    def clean_quantity(self):
        quantity = self.cleaned_data["quantity"]
        if quantity is not None and quantity <= 0:
            raise forms.ValidationError("Must be above zero.")
        return quantity


BasketItemFormSet = inlineformset_factory(
    Basket,
    BasketItem,
    form=BasketItemForm,
    extra=3,
    can_delete=True,
)
