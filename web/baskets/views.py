from django.contrib import messages
from django.db import transaction
from django.db.models import Count
from django.shortcuts import get_object_or_404, redirect, render
from django.views.generic import ListView

from core.access import StaffRequiredMixin, staff_required
from locations.models import City

from .forms import BasketForm, BasketItemFormSet
from .models import Basket
from .services import compare_basket


class BasketListView(StaffRequiredMixin, ListView):
    template_name = "baskets/basket_list.html"
    context_object_name = "baskets"

    def get_queryset(self):
        return Basket.objects.annotate(item_count=Count("items"))


@staff_required
def basket_edit(request, pk=None):
    """Create a basket (no pk) or edit one, together with its products."""
    basket = get_object_or_404(Basket, pk=pk) if pk else None
    form = BasketForm(request.POST or None, instance=basket)
    formset = BasketItemFormSet(request.POST or None, instance=basket)

    if request.method == "POST" and form.is_valid():
        # The formset must be checked against the basket being saved.
        formset = BasketItemFormSet(request.POST, instance=form.instance)
        if formset.is_valid():
            with transaction.atomic():
                saved = form.save()
                formset.save()
            messages.success(request, f"Basket “{saved.name}” was saved.")
            return redirect("basket_detail", pk=saved.pk)

    return render(
        request,
        "baskets/basket_form.html",
        {"form": form, "formset": formset, "basket": basket},
    )


@staff_required
def basket_detail(request, pk):
    """Ranking of stores for one basket, cheapest first."""
    basket = get_object_or_404(Basket, pk=pk)
    city_id = request.GET.get("city", "")
    city = City.objects.filter(pk=city_id).first() if city_id.isdigit() else None
    results = compare_basket(basket, city=city)
    return render(
        request,
        "baskets/basket_detail.html",
        {
            "basket": basket,
            "items": basket.items.select_related("product"),
            "city": city,
            "cities": City.objects.all(),
            "results": results,
            "has_incomplete": any(not result.complete for result in results),
        },
    )
