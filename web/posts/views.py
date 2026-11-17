from django.contrib import messages
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST
from django.views.generic import ListView

from core.permissions import StaffRequiredMixin, staff_required
from locations.models import City

from .forms import PostForm
from .hashtags import build_hashtags
from .models import Post
from .telegram import compose_html, compose_plain, length_limit, telegram_length


class PostListView(StaffRequiredMixin, ListView):
    model = Post
    paginate_by = 30
    template_name = "posts/post_list.html"

    def get_queryset(self):
        self.status = self.request.GET.get("status", "")
        posts = Post.objects.select_related("city")
        if self.status in Post.Status.values:
            posts = posts.filter(status=self.status)
        return posts

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context.update(
            statuses=Post.Status.choices,
            selected_status=self.status,
            filter_params=f"status={self.status}" if self.status else "",
        )
        return context


@staff_required
def post_edit(request, pk=None):
    post = get_object_or_404(Post, pk=pk) if pk else Post()
    if post.pk and not post.is_editable:
        messages.warning(request, f"A {post.get_status_display().lower()} post "
                                  "cannot be edited.")
        return redirect("posts:post_list")

    action = request.POST.get("action", PostForm.ACTION_DRAFT)
    form = PostForm(request.POST or None, request.FILES or None,
                    instance=post, action=action)
    if request.method == "POST" and form.is_valid():
        if post.pk is None:
            form.instance.created_by = request.user
        post = form.save()
        if post.status == Post.Status.SCHEDULED:
            messages.success(request, f"“{post}” is scheduled for "
                                      f"{post.scheduled_at:%d.%m.%Y %H:%M}.")
        else:
            messages.success(request, f"Draft “{post}” saved.")
        return redirect("posts:post_edit", pk=post.pk)
    return render(request, "posts/post_form.html", {
        "form": form,
        "post": post if post.pk else None,
    })


@staff_required
@require_POST
def post_unschedule(request, pk):
    post = get_object_or_404(Post, pk=pk)
    if post.can_change_status(Post.Status.DRAFT):
        post.unschedule()
        messages.success(request, f"“{post}” moved back to drafts.")
    else:
        messages.error(request, "This post can no longer be changed.")
    return redirect("posts:post_edit", pk=post.pk)


@staff_required
@require_POST
def post_preview(request):
    """JSON for the live preview: the message exactly as it will be sent."""
    data = request.POST
    city = City.objects.filter(pk=data.get("city") or None).first()
    hashtags = " ".join(build_hashtags(
        data.get("rubric", ""), data.get("language", "uz"),
        city.name if city else "", data.get("extra_tags", ""),
    ))
    title, body = data.get("title", ""), data.get("body", "")
    has_image = data.get("has_image") == "1"
    return JsonResponse({
        "html": compose_html(title, body, hashtags),
        "hashtags": hashtags,
        "length": telegram_length(compose_plain(title, body, hashtags)),
        "limit": length_limit(has_image),
    })
