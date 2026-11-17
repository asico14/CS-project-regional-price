from django.urls import reverse_lazy
from django.views.generic import CreateView, ListView, UpdateView

from core.permissions import StaffRequiredMixin
from core.views_mixins import FormPageMixin

from .forms import StoreForm
from .models import City, Store


class StoreListView(StaffRequiredMixin, ListView):
    """Stores, optionally filtered by city."""

    model = Store
    paginate_by = 50
    template_name = "locations/store_list.html"

    def get_queryset(self):
        self.city = self.request.GET.get("city", "")
        stores = Store.objects.select_related("city", "district")
        if self.city:
            stores = stores.filter(city__slug=self.city)
        return stores

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context.update(
            cities=City.objects.all(),
            selected_city=self.city,
            filter_params=f"city={self.city}" if self.city else "",
        )
        return context


class StoreFormMixin(StaffRequiredMixin, FormPageMixin):
    model = Store
    form_class = StoreForm
    noun = "store"
    cancel_url_name = "locations:store_list"
    success_url = reverse_lazy("locations:store_list")


class StoreCreateView(StoreFormMixin, CreateView):
    pass


class StoreUpdateView(StoreFormMixin, UpdateView):
    pass
