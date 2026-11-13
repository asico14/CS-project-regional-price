from django.urls import path

from . import views

urlpatterns = [
    path("baskets/", views.BasketListView.as_view(), name="basket_list"),
    path("baskets/new/", views.basket_edit, name="basket_create"),
    path("baskets/<int:pk>/", views.basket_detail, name="basket_detail"),
    path("baskets/<int:pk>/edit/", views.basket_edit, name="basket_update"),
]
