"""Comments on or off for a post.

Telegram has no "comments off" switch for a single channel post.
Comments exist because the channel has a linked discussion group:
Telegram copies every channel post into that group automatically, and
the copy is the comment thread of the post. If the copy is deleted
from the group, the post has no comment button.

So the worker watches the discussion group. For every automatic copy
it asks decide() what to do, and deletes the copy when the post was
saved with "Allow comments" switched off.
"""

from .models import Post

KEEP = "keep"  # leave the comments open
CLOSE = "close"  # delete the copy in the group: no comments
WAIT = "wait"  # not known yet, ask again in a moment


def decide(channel_message_id):
    """What to do with the automatic copy of a channel message.

    The copy can arrive in the group a moment before the worker has
    saved the message id of the post it just sent. In that case the
    answer is WAIT while some post is still being published.
    """
    post = Post.objects.filter(telegram_message_id=channel_message_id).first()
    if post is not None:
        return KEEP if post.comments_enabled else CLOSE
    if Post.objects.filter(status=Post.Status.PUBLISHING).exists():
        return WAIT
    # Not one of our posts (e.g. written by hand in the channel).
    return KEEP
