from django.urls import path

from . import views

app_name = "baskets"

urlpatterns = [
    path("baskets/", views.BasketListView.as_view(), name="basket_list"),
    path("baskets/new/", views.basket_edit, name="basket_create"),
    path("baskets/<int:pk>/", views.basket_compare, name="basket_compare"),
    path("baskets/<int:pk>/edit/", views.basket_edit, name="basket_edit"),
]
