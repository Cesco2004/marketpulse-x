from flask import Blueprint, redirect
from storage.database import get_post_by_id, update_post_status, mark_as_posted
from pipeline import publish_post

bp = Blueprint("queue", __name__)


@bp.route("/queue")
def queue_page():
    return redirect("/pipeline")


@bp.route("/api/posts/<int:post_id>/post-now", methods=["POST"])
def post_now(post_id):
    post = get_post_by_id(post_id)
    if not post:
        return '<div class="post-card"><p style="color:var(--qb-red)">Post not found.</p></div>'

    try:
        tweet_id, has_image = publish_post(post)
        mark_as_posted(post_id, tweet_id)
        img_badge = ' IMG' if has_image else ''
        return f'''
        <div class="post-card" style="border-color:var(--qb-green);opacity:0.7">
            <div class="post-content">{post["content"]}</div>
            <div class="post-meta">
                <strong style="color:var(--qb-green)">Posted!{img_badge}</strong>
                <a href="https://x.com/QEdgeIntel/status/{tweet_id}" target="_blank">View on X</a>
            </div>
        </div>
        '''
    except Exception as e:
        return f'''
        <div class="post-card" style="border-color:var(--qb-red)">
            <div class="post-content">{post["content"]}</div>
            <div class="post-meta">
                <strong style="color:var(--qb-red)">Error: {e}</strong>
            </div>
        </div>
        '''


@bp.route("/api/posts/<int:post_id>/unqueue", methods=["POST"])
def unqueue_post(post_id):
    update_post_status(post_id, "pending_review")
    return f'''
    <div class="post-card" id="queue-card-{post_id}" style="opacity:0.5">
        <p>Moved back to review.</p>
    </div>
    '''
