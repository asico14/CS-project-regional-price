from django.contrib.messages.views import SuccessMessageMixin
from django.urls import reverse_lazy
from django.views.generic import CreateView, ListView, UpdateView

from core.access import StaffRequiredMixin

from .forms import StoreForm
from .models import City, Store


class StoreListView(StaffRequiredMixin, ListView):
    """Store list, optionally filtered by city."""

    model = Store
    template_name = "locations/store_list.html"
    context_object_name = "stores"
    paginate_by = 25

    def get_queryset(self):
        stores = Store.objects.select_related("city", "district")
        self.city_id = self.request.GET.get("city", "")
        if self.city_id.isdigit():
            stores = stores.filter(city_id=self.city_id)
        return stores

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["city_id"] = self.city_id
        context["cities"] = City.objects.all()
        params = self.request.GET.copy()
        params.pop("page", None)
        context["filter_query"] = params.urlencode()
        return context


class StoreCreateView(StaffRequiredMixin, SuccessMessageMixin, CreateView):
    model = Store
    form_class = StoreForm
    template_name = "locations/store_form.html"
    success_url = reverse_lazy("store_list")
    success_message = "Store “%(name)s” was added."


class StoreUpdateView(StaffRequiredMixin, SuccessMessageMixin, UpdateView):
    model = Store
    form_class = StoreForm
    template_name = "locations/store_form.html"
    success_url = reverse_lazy("store_list")
    success_message = "Store “%(name)s” was saved."
