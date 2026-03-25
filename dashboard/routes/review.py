from flask import Blueprint, render_template, request
from storage.database import get_pending_posts, update_post_status, update_post_content, get_post_by_id, clear_post_image, get_connection

bp = Blueprint("review", __name__)


@bp.route("/review")
def review_page():
    posts = get_pending_posts()

    # Get stats from the latest batch for the info banner
    batch_stats = {}
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT status, COUNT(*) as cnt FROM posts
        WHERE batch_id = (SELECT batch_id FROM posts ORDER BY created_at DESC LIMIT 1)
        GROUP BY status
    """)
    for row in cursor.fetchall():
        batch_stats[row["status"]] = row["cnt"]
    conn.close()

    return render_template("review.html", posts=posts, batch_stats=batch_stats)


@bp.route("/api/posts/<int:post_id>/approve", methods=["POST"])
def approve_post(post_id):
    update_post_status(post_id, "approved")
    post = get_post_by_id(post_id)
    return f'''
    <div class="post-card" id="post-card-{post_id}" style="border-color:var(--qb-green);opacity:0.7">
        <div class="post-content">{post["content"]}</div>
        <div class="post-meta">
            <span class="badge badge-{post["post_type"]}">{post["post_type"]}</span>
            <strong style="color:var(--qb-green)">Approved</strong>
        </div>
    </div>
    '''


@bp.route("/api/posts/<int:post_id>/reject", methods=["POST"])
def reject_post(post_id):
    update_post_status(post_id, "rejected")
    return f'''
    <div class="post-card" id="post-card-{post_id}" style="border-color:var(--qb-red);opacity:0.5">
        <div class="post-meta"><strong style="color:var(--qb-red)">Rejected</strong></div>
    </div>
    '''


@bp.route("/api/posts/<int:post_id>/edit-form", methods=["GET"])
def edit_form(post_id):
    post = get_post_by_id(post_id)
    return f'''
    <div class="post-card" id="post-card-{post_id}">
        <form hx-post="/api/posts/{post_id}/save-edit" hx-target="#post-card-{post_id}" hx-swap="outerHTML">
            <textarea name="content" rows="4" style="width:100%">{post["content"]}</textarea>
            <div class="post-actions">
                <button type="submit" style="border-color:var(--qb-green);color:var(--qb-green)" class="outline">Save & Approve</button>
                <button type="button" class="outline secondary"
                        hx-get="/api/posts/{post_id}/cancel-edit"
                        hx-target="#post-card-{post_id}"
                        hx-swap="outerHTML">Cancel</button>
            </div>
        </form>
    </div>
    '''


@bp.route("/api/posts/<int:post_id>/save-edit", methods=["POST"])
def save_edit(post_id):
    new_content = request.form.get("content", "").strip()
    if new_content:
        update_post_content(post_id, new_content)
        update_post_status(post_id, "approved")
    post = get_post_by_id(post_id)
    clen = len(post["content"])
    chars_class = "chars-ok" if clen <= 260 else ("chars-warn" if clen <= 280 else "chars-over")
    return f'''
    <div class="post-card" id="post-card-{post_id}" style="border-color:var(--qb-green);opacity:0.7">
        <div class="post-content">{post["content"]}</div>
        <div class="post-meta">
            <span class="badge badge-{post["post_type"]}">{post["post_type"]}</span>
            <span class="{chars_class}">{clen} chars</span>
            <strong style="color:var(--qb-green)">Edited & Approved</strong>
        </div>
    </div>
    '''


@bp.route("/api/posts/<int:post_id>/cancel-edit", methods=["GET"])
def cancel_edit(post_id):
    post = get_post_by_id(post_id)
    clen = len(post["content"])
    chars_class = "chars-ok" if clen <= 260 else ("chars-warn" if clen <= 280 else "chars-over")
    return f'''
    <div class="post-card" id="post-card-{post_id}">
        <div class="post-content">{post["content"]}</div>
        <div class="post-meta">
            <span class="badge badge-{post["post_type"]}">{post["post_type"]}</span>
            <span class="{chars_class}">{clen} chars</span>
        </div>
        <div class="post-actions">
            <button class="outline" style="border-color:var(--qb-green);color:var(--qb-green)"
                    hx-post="/api/posts/{post_id}/approve"
                    hx-target="#post-card-{post_id}"
                    hx-swap="outerHTML">Approve</button>
            <button class="outline" style="border-color:var(--qb-red);color:var(--qb-red)"
                    hx-post="/api/posts/{post_id}/reject"
                    hx-target="#post-card-{post_id}"
                    hx-swap="outerHTML">Reject</button>
            <button class="outline"
                    hx-get="/api/posts/{post_id}/edit-form"
                    hx-target="#post-card-{post_id}"
                    hx-swap="outerHTML">Edit</button>
        </div>
    </div>
    '''


@bp.route("/api/posts/approve-all", methods=["POST"])
def approve_all():
    posts = get_pending_posts()
    for post in posts:
        update_post_status(post["id"], "approved")
    return f'<p style="color:var(--qb-green)"><strong>{len(posts)} post(s) approved.</strong> <a href="/review">Refresh</a></p>'


@bp.route("/api/posts/reject-all", methods=["POST"])
def reject_all():
    posts = get_pending_posts()
    for post in posts:
        update_post_status(post["id"], "rejected")
    return f'<p style="color:var(--qb-red)"><strong>{len(posts)} post(s) rejected.</strong> <a href="/review">Refresh</a></p>'


@bp.route("/api/posts/<int:post_id>/remove-image", methods=["POST"])
def remove_image(post_id):
    clear_post_image(post_id)
    # Return refreshed card — redirect to review to reload
    return f'''
    <div class="post-card" id="post-card-{post_id}" style="opacity:0.8">
        <div style="color:var(--qb-dim);font-size:0.8rem;padding:0.5rem">Image removed. <a href="/review">Refresh</a> to see updated card.</div>
    </div>
    '''
