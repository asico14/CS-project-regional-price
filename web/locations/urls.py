from django.urls import path

from . import views

urlpatterns = [
    path("stores/", views.StoreListView.as_view(), name="store_list"),
    path("stores/new/", views.StoreCreateView.as_view(), name="store_create"),
    path("stores/<int:pk>/edit/", views.StoreUpdateView.as_view(), name="store_update"),
]
