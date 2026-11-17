from django.contrib import messages
from django.db import transaction
from django.db.models import Count
from django.shortcuts import get_object_or_404, redirect, render
from django.views.generic import ListView

from core.permissions import StaffRequiredMixin, staff_required
from locations.models import City

from .forms import BasketForm, BasketItemFormSet
from .models import Basket
from .services import compare_basket


class BasketListView(StaffRequiredMixin, ListView):
    model = Basket
    template_name = "baskets/basket_list.html"
    queryset = Basket.objects.annotate(item_count=Count("items"))


@staff_required
def basket_edit(request, pk=None):
    """Create or edit a basket together with its products (inline formset)."""
    basket = get_object_or_404(Basket, pk=pk) if pk else Basket()
    form = BasketForm(request.POST or None, instance=basket)
    formset = BasketItemFormSet(request.POST or None, instance=basket)
    if request.method == "POST" and form.is_valid() and formset.is_valid():
        with transaction.atomic():
            if basket.pk is None:
                form.instance.created_by = request.user
            basket = form.save()
            formset.instance = basket
            formset.save()
        messages.success(request, f"Basket “{basket}” saved.")
        return redirect("baskets:basket_compare", pk=basket.pk)
    return render(request, "baskets/basket_form.html", {
        "form": form,
        "formset": formset,
        "basket": basket if basket.pk else None,
    })


@staff_required
def basket_compare(request, pk):
    """Ranking of the stores by the cost of the whole basket."""
    basket = get_object_or_404(Basket, pk=pk)
    city = None
    city_slug = request.GET.get("city", "")
    if city_slug:
        city = get_object_or_404(City, slug=city_slug)
    comparison = compare_basket(basket, city=city)
    return render(request, "baskets/basket_compare.html", {
        "basket": basket,
        "comparison": comparison,
        "items": basket.items.select_related("product"),
        "cities": City.objects.all(),
        "selected_city": city_slug,
    })
