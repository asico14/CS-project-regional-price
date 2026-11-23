from django.urls import path

from . import views

app_name = "posts"

urlpatterns = [
    path("posts/", views.PostListView.as_view(), name="post_list"),
    path("posts/new/", views.post_edit, name="post_create"),
    path("posts/preview/", views.post_preview, name="post_preview"),
    path("posts/generate/", views.post_generate, name="post_generate"),
    path("posts/<int:pk>/", views.post_edit, name="post_edit"),
    path("posts/<int:pk>/unschedule/", views.post_unschedule, name="post_unschedule"),
]
