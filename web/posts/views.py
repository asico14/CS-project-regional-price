from django.contrib import messages
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST
from django.views.generic import ListView

from core.access import StaffRequiredMixin, staff_required
from locations.models import City

from .formatting import compose_text, limit_for, telegram_length
from .forms import PostForm, PricePostForm, PromotionPostForm
from .generators import NothingToPost, generate_price_post, generate_promotion_post
from .hashtags import build_hashtags
from .models import Post

# Posts in these states can still be changed by staff.
EDITABLE = [Post.Status.DRAFT, Post.Status.SCHEDULED, Post.Status.FAILED]


class PostListView(StaffRequiredMixin, ListView):
    template_name = "posts/post_list.html"
    context_object_name = "posts"
    paginate_by = 25

    def get_queryset(self):
        posts = Post.objects.select_related("city")
        self.status = self.request.GET.get("status", "")
        if self.status in Post.Status.values:
            posts = posts.filter(status=self.status)
        return posts

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["status"] = self.status
        context["statuses"] = Post.Status.choices
        params = self.request.GET.copy()
        params.pop("page", None)
        context["filter_query"] = params.urlencode()
        return context


@staff_required
def post_edit(request, pk=None):
    """Create a post (no pk) or edit one that is not published yet."""
    post = get_object_or_404(Post, pk=pk) if pk else None
    if post and post.status not in EDITABLE:
        status = post.get_status_display().lower()
        messages.error(request, f"“{post.title}” is {status} and cannot be edited.")
        return redirect("post_list")

    form = PostForm(request.POST or None, request.FILES or None, instance=post)
    if request.method == "POST" and form.is_valid():
        saved = form.save(commit=False)
        if post is None:
            saved.created_by = request.user
        saved.save()
        if saved.status == Post.Status.SCHEDULED:
            messages.success(request, f"“{saved.title}” was scheduled.")
        else:
            messages.success(request, f"“{saved.title}” was saved as a draft.")
        return redirect("post_list")

    return render(request, "posts/post_form.html", {"form": form, "post": post})


@staff_required
@require_POST
def post_preview(request):
    """Data for the live preview: the same text the channel will get.

    The preview is built on the server so that the page and the worker
    always agree on hashtags and on the length of the message.
    """
    city_id = request.POST.get("city", "")
    city = City.objects.filter(pk=city_id).first() if city_id.isdigit() else None
    title = request.POST.get("title", "").strip()
    text = request.POST.get("text", "").replace("\r\n", "\n").strip()
    hashtags = build_hashtags(
        request.POST.get("rubric"), request.POST.get("language") or "uz", city
    )
    has_photo = request.POST.get("has_photo") == "1"
    length = telegram_length(compose_text(title, text, hashtags))
    limit = limit_for(has_photo)
    return JsonResponse(
        {
            "title": title,
            "text": text,
            "hashtags": hashtags,
            "length": length,
            "limit": limit,
            "over": max(0, length - limit),
        }
    )


# kind -> (heading, description, form class, function that builds the draft)
GENERATORS = {
    "promotion": (
        "Promotion post",
        "Lists the promotions that are running now, biggest discounts first.",
        PromotionPostForm,
        lambda data, user: generate_promotion_post(
            data["city"], data["language"], user
        ),
    ),
    "price": (
        "Price post",
        "Compares the current price of one product between stores.",
        PricePostForm,
        lambda data, user: generate_price_post(
            data["product"], data["city"], data["language"], user
        ),
    ),
}


@staff_required
def post_generate(request):
    """Build a draft post from the data and open it for review.

    A generated post is never published directly: it is saved as a
    draft so that a person reads it before it is scheduled.
    """
    chosen = request.POST.get("kind") if request.method == "POST" else None
    generators = []
    for kind, (heading, description, form_class, build) in GENERATORS.items():
        form = form_class(request.POST if kind == chosen else None, prefix=kind)
        if kind == chosen and form.is_valid():
            try:
                draft = build(form.cleaned_data, request.user)
            except NothingToPost as error:
                form.add_error(None, str(error))
            else:
                draft.save()
                messages.success(
                    request, "Draft created. Check the text, then schedule it."
                )
                return redirect("post_update", pk=draft.pk)
        generators.append(
            {"kind": kind, "heading": heading, "description": description, "form": form}
        )
    return render(request, "posts/post_generate.html", {"generators": generators})
