from django import forms

from .models import District, Store


class StoreForm(forms.ModelForm):
    class Meta:
        model = Store
        fields = ["name", "city", "district", "address", "is_active"]
        labels = {"is_active": "Active (shown in price entry)"}
        help_texts = {"district": "Optional. Must be a district of the chosen city."}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["district"].queryset = District.objects.select_related("city")

    def clean_name(self):
        return self.cleaned_data["name"].strip()

    # The "district belongs to the city" rule lives in Store.clean(),
    # which ModelForm runs automatically, so the admin uses it too.
