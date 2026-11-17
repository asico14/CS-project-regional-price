"""Small reusable pieces for the create/edit views of all apps."""

from django.contrib import messages


class FormPageMixin:
    """Fills the context of ``core/object_form.html`` and shows a message.

    Set ``noun`` (e.g. "product") and ``cancel_url_name`` on the view.
    """

    template_name = "core/object_form.html"
    noun = "object"
    cancel_url_name = None

    def get_cancel_url(self):
        from django.urls import reverse

        return reverse(self.cancel_url_name)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        editing = getattr(self, "object", None) is not None and self.object.pk
        context["form_title"] = (
            f"Edit {self.noun}: {self.object}" if editing else f"New {self.noun}"
        )
        context["cancel_url"] = self.get_cancel_url()
        return context

    def form_valid(self, form):
        created = form.instance.pk is None
        response = super().form_valid(form)
        verb = "created" if created else "saved"
        messages.success(self.request, f"{self.noun.capitalize()} “{self.object}” {verb}.")
        return response
