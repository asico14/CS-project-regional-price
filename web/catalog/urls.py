from django.urls import path

from . import views

urlpatterns = [
    path("products/", views.ProductListView.as_view(), name="product_list"),
    path("products/new/", views.ProductCreateView.as_view(), name="product_create"),
    path("products/<int:pk>/", views.ProductDetailView.as_view(), name="product_detail"),
    path(
        "products/<int:pk>/edit/",
        views.ProductUpdateView.as_view(),
        name="product_update",
    ),
    path("prices/entry/", views.price_entry, name="price_entry"),
]
