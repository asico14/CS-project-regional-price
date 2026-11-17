from django.contrib import messages
from django.db import transaction
from django.db.models import Q
from django.shortcuts import redirect, render
from django.urls import reverse_lazy
from django.views.generic import CreateView, ListView, UpdateView

from core.permissions import StaffRequiredMixin, staff_required
from core.views_mixins import FormPageMixin

from .forms import PriceEntryForm, PriceEntryStartForm, ProductForm
from .models import Category, Price, Product


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


class ProductFormMixin(StaffRequiredMixin, FormPageMixin):
    model = Product
    form_class = ProductForm
    noun = "product"
    cancel_url_name = "catalog:product_list"
    success_url = reverse_lazy("catalog:product_list")


class ProductCreateView(ProductFormMixin, CreateView):
    pass


class ProductUpdateView(ProductFormMixin, UpdateView):
    pass


@staff_required
def price_entry(request):
    """Fast daily price entry: pick a store and a day, then type the prices.

    Step 1 (no store chosen yet) shows a small form. Step 2 lists every
    active product with the last known price in that store as placeholder;
    only the filled rows are saved, all in one transaction.
    """
    start = PriceEntryStartForm(request.GET or None)
    if not start.is_valid():
        return render(request, "catalog/price_entry_start.html", {"form": start})

    store = start.cleaned_data["store"]
    day = start.cleaned_data["observed_on"]
    products = Product.objects.filter(is_active=True).select_related("category")
    category = request.GET.get("category", "")
    if category:
        products = products.filter(category__slug=category)
    products = products.order_by("category__name", "name", "brand")
    last_prices = dict(
        Price.objects.current()
        .filter(store=store, observed_on__lte=day)
        .values_list("product_id", "price")
    )

    form = PriceEntryForm(
        request.POST or None, products=products, last_prices=last_prices
    )
    if request.method == "POST" and form.is_valid():
        rows = [
            Price(product=product, store=store, price=price,
                  regular_price=regular, promo_until=until,
                  observed_on=day, created_by=request.user)
            for product, price, regular, until in form.entered_prices()
        ]
        if rows:
            with transaction.atomic():
                Price.objects.bulk_create(rows)
            messages.success(
                request, f"Saved {len(rows)} prices for {store} on {day:%d.%m.%Y}."
            )
            return redirect(request.get_full_path())
        messages.warning(request, "Nothing to save: all price fields were empty.")

    already = Price.objects.filter(store=store, observed_on=day).count()
    return render(request, "catalog/price_entry.html", {
        "form": form,
        "store": store,
        "day": day,
        "already": already,
        "categories": Category.objects.all(),
        "selected_category": category,
    })
