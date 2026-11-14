from django.urls import path

from . import views

urlpatterns = [
    path("posts/", views.PostListView.as_view(), name="post_list"),
    path("posts/new/", views.post_edit, name="post_create"),
    path("posts/preview/", views.post_preview, name="post_preview"),
    path("posts/<int:pk>/edit/", views.post_edit, name="post_update"),
]
