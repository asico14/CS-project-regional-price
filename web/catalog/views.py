from django.db.models import Q
from django.views.generic import ListView

from core.permissions import StaffRequiredMixin

from .models import Category, Product


class ProductListView(StaffRequiredMixin, ListView):
    """Products with a text search (name or brand) and a category filter."""

    model = Product
    paginate_by = 25
    template_name = "catalog/product_list.html"

    def get_queryset(self):
        products = Product.objects.select_related("category")
        self.query = self.request.GET.get("q", "").strip()
        self.category = self.request.GET.get("category", "")
        if self.query:
            products = products.filter(
                Q(name__icontains=self.query) | Q(brand__icontains=self.query)
            )
        if self.category:
            products = products.filter(category__slug=self.category)
        if self.request.GET.get("inactive") != "1":
            products = products.filter(is_active=True)
        return products

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        params = self.request.GET.copy()
        params.pop("page", None)
        context.update(
            categories=Category.objects.all(),
            query=self.query,
            selected_category=self.category,
            show_inactive=self.request.GET.get("inactive") == "1",
            filter_params=params.urlencode(),
        )
        return context
