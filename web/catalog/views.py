from decimal import Decimal, InvalidOperation

from django import forms
from django.contrib import messages
from django.contrib.messages.views import SuccessMessageMixin
from django.db.models import Q
from django.shortcuts import redirect, render
from django.urls import reverse, reverse_lazy
from django.views.generic import CreateView, DetailView, ListView, UpdateView

from core.access import StaffRequiredMixin, staff_required
from locations.models import City, Store

from .forms import ProductForm
from .models import Category, Price, Product
from .services import HISTORY_DAYS, current_prices, price_history

MAX_PRICE = Decimal("9999999999.99")


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


class ProductDetailView(StaffRequiredMixin, DetailView):
    """Compare the current prices of one product between stores."""

    model = Product
    template_name = "catalog/product_detail.html"
    context_object_name = "product"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        city_id = self.request.GET.get("city", "")
        city = City.objects.filter(pk=city_id).first() if city_id.isdigit() else None
        context["city"] = city
        context["cities"] = City.objects.all()
        context["rows"] = current_prices(self.object, city=city)
        context["history"] = price_history(self.object, city=city)
        context["history_days"] = HISTORY_DAYS
        return context


class ProductCreateView(StaffRequiredMixin, SuccessMessageMixin, CreateView):
    model = Product
    form_class = ProductForm
    template_name = "catalog/product_form.html"
    success_url = reverse_lazy("product_list")
    success_message = "Product “%(name)s” was added."


class ProductUpdateView(StaffRequiredMixin, SuccessMessageMixin, UpdateView):
    model = Product
    form_class = ProductForm
    template_name = "catalog/product_form.html"
    success_url = reverse_lazy("product_list")
    success_message = "Product “%(name)s” was saved."


def parse_amount(raw):
    """Turn typed text like "12 500" or "12500,50" into a Decimal.

    Returns None for text that is not a valid positive price.
    """
    cleaned = raw.replace(" ", "").replace("\u00a0", "").replace(",", ".")
    try:
        amount = Decimal(cleaned)
    except InvalidOperation:
        return None
    if not amount.is_finite() or amount <= 0 or amount > MAX_PRICE:
        return None
    return amount.quantize(Decimal("0.01"))


@staff_required
def price_entry(request):
    """Enter today's prices for one store on a single page.

    Empty fields are skipped, and a price equal to the current one is
    not saved again, so a new row appears only when a price changes.
    """
    stores = Store.objects.filter(is_active=True).select_related("city")
    store_id = request.POST.get("store") or request.GET.get("store") or ""
    store = stores.filter(pk=store_id).first() if store_id.isdigit() else None

    rows = []
    promo_ends_raw = request.POST.get("promo_ends", "")
    promo_ends_error = ""
    if store:
        current = {
            price.product_id: price
            for price in Price.objects.current().filter(store=store)
        }
        products = Product.objects.filter(is_active=True).select_related("category")
        for product in products.order_by("category__name", "name", "brand"):
            rows.append(
                {
                    "product": product,
                    "current": current.get(product.pk),
                    "value": request.POST.get(f"price_{product.pk}", "").strip(),
                    "promo": f"promo_{product.pk}" in request.POST,
                    "error": "",
                }
            )

    if request.method == "POST" and store:
        promo_ends = None
        if promo_ends_raw:
            try:
                promo_ends = forms.DateField().clean(promo_ends_raw)
            except forms.ValidationError:
                promo_ends_error = "Enter a valid date."

        new_prices = []
        unchanged = 0
        for row in rows:
            if not row["value"]:
                continue
            amount = parse_amount(row["value"])
            if amount is None:
                row["error"] = "Enter a price greater than zero."
                continue
            last = row["current"]
            if last and last.amount == amount and last.is_promo == row["promo"]:
                unchanged += 1
                continue
            new_prices.append(
                Price(
                    product=row["product"],
                    store=store,
                    amount=amount,
                    is_promo=row["promo"],
                    promo_ends=promo_ends if row["promo"] else None,
                )
            )

        has_errors = promo_ends_error or any(row["error"] for row in rows)
        if not has_errors:
            # Nothing is saved unless the whole page is valid.
            Price.objects.bulk_create(new_prices)
            messages.success(
                request,
                f"{store.name}: {len(new_prices)} new price(s) saved, "
                f"{unchanged} unchanged.",
            )
            return redirect(f"{reverse('price_entry')}?store={store.pk}")

    return render(
        request,
        "catalog/price_entry.html",
        {
            "stores": stores,
            "store": store,
            "rows": rows,
            "promo_ends": promo_ends_raw,
            "promo_ends_error": promo_ends_error,
        },
    )
