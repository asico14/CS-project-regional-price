// Live Telegram-style preview for the post form.
// The server builds the text (hashtags, length, limit), this script
// only shows it, so the preview matches what the worker will send.
(function () {
  const form = document.getElementById("post-form");
  if (!form) {
    return;
  }
  const field = (name) => form.elements[name];
  const title = document.getElementById("preview-title");
  const text = document.getElementById("preview-text");
  const hashtags = document.getElementById("preview-hashtags");
  const empty = document.getElementById("preview-empty");
  const counter = document.getElementById("preview-counter");
  const photo = document.getElementById("preview-photo");
  const photoInput = field("photo");
  const clearPhoto = field("photo-clear");
  const savedPhotoUrl = form.dataset.photoUrl;
  let chosenPhotoUrl = "";

  function hasPhoto() {
    if (photoInput && photoInput.files.length > 0) {
      return true;
    }
    return Boolean(savedPhotoUrl) && !(clearPhoto && clearPhoto.checked);
  }

  function showPhoto() {
    if (chosenPhotoUrl) {
      URL.revokeObjectURL(chosenPhotoUrl);
      chosenPhotoUrl = "";
    }
    if (photoInput && photoInput.files.length > 0) {
      chosenPhotoUrl = URL.createObjectURL(photoInput.files[0]);
      photo.src = chosenPhotoUrl;
      photo.hidden = false;
    } else if (hasPhoto()) {
      photo.src = savedPhotoUrl;
      photo.hidden = false;
    } else {
      photo.hidden = true;
      photo.removeAttribute("src");
    }
  }

  function show(data) {
    // textContent, never innerHTML: what staff type is shown as text.
    title.textContent = data.title;
    text.textContent = data.text;
    hashtags.textContent = data.hashtags.join(" ");
    empty.hidden = Boolean(data.title || data.text);
    counter.textContent =
      data.length + " / " + data.limit + " characters" +
      (data.over ? " — " + data.over + " too many" : "");
    counter.classList.toggle("over", data.over > 0);
  }

  let timer = null;
  let requestNumber = 0;

  async function refresh() {
    const body = new FormData();
    ["rubric", "language", "city", "title", "text"].forEach((name) => {
      body.append(name, field(name).value);
    });
    body.append("has_photo", hasPhoto() ? "1" : "0");
    body.append("csrfmiddlewaretoken", field("csrfmiddlewaretoken").value);
    const thisRequest = ++requestNumber;
    try {
      const response = await fetch(form.dataset.previewUrl, { method: "POST", body: body });
      if (!response.ok) {
        throw new Error("status " + response.status);
      }
      const data = await response.json();
      // Ignore answers that arrive after a newer request was sent.
      if (thisRequest === requestNumber) {
        show(data);
      }
    } catch (error) {
      counter.textContent = "Preview is not available right now.";
    }
  }

  function schedule() {
    clearTimeout(timer);
    timer = setTimeout(refresh, 250);
  }

  form.addEventListener("input", schedule);
  form.addEventListener("change", () => {
    showPhoto();
    schedule();
  });
  showPhoto();
  refresh();
})();
