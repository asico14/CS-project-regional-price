from django.db.models import Q
from django.views.generic import ListView

from core.access import StaffRequiredMixin

from .models import Category, Product


class ProductListView(StaffRequiredMixin, ListView):
    """Product list with a text search and a category filter."""

    model = Product
    template_name = "catalog/product_list.html"
    context_object_name = "products"
    paginate_by = 25

    def get_queryset(self):
        products = Product.objects.select_related("category")
        self.query = self.request.GET.get("q", "").strip()
        self.category_id = self.request.GET.get("category", "")
        if self.query:
            products = products.filter(
                Q(name__icontains=self.query) | Q(brand__icontains=self.query)
            )
        if self.category_id.isdigit():
            products = products.filter(category_id=self.category_id)
        return products

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["query"] = self.query
        context["category_id"] = self.category_id
        context["categories"] = Category.objects.all()
        # Keep the filters when moving between pages.
        params = self.request.GET.copy()
        params.pop("page", None)
        context["filter_query"] = params.urlencode()
        return context
