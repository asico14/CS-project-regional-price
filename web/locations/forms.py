from django import forms

from .models import Store


class StoreForm(forms.ModelForm):
    class Meta:
        model = Store
        fields = ["name", "city", "district", "address", "is_active"]
        help_texts = {
            "district": "Optional. Must be a district of the chosen city.",
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["district"].queryset = self.fields[
            "district"
        ].queryset.select_related("city")

    def clean_name(self):
        return " ".join(self.cleaned_data["name"].split())
