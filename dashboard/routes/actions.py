import json
from flask import Blueprint, make_response
from pipeline import run_fetch_pipeline, run_post_next

bp = Blueprint("actions", __name__)


@bp.route("/api/fetch", methods=["POST"])
def fetch_action():
    result = run_fetch_pipeline()

    if result.get("skipped_reason") == "no_new_articles":
        html = f'''
        <article style="border-left:4px solid var(--qb-accent);padding-left:1rem">
            <h4 style="color:var(--qb-accent-soft)">No New Articles</h4>
            <p><strong>{result["articles_fetched"]}</strong> articles fetched from RSS feeds, but all were already in the database.</p>
            <p style="color:var(--qb-dim);font-size:0.85rem">No Mistral tokens spent. Try again later when feeds have new content.</p>
        </article>
        '''
        resp = make_response(html)
        resp.headers["HX-Trigger"] = json.dumps({
            "showToast": {"type": "info", "message": "No new articles found — no tokens spent."}
        })
        return resp

    if result["success"]:
        posts_count = len(result["posts"])
        auto_approved = result.get("auto_approved", 0)
        auto_rejected = result.get("auto_rejected", 0)
        needs_review = result.get("needs_review", 0)

        review_link = ""
        if needs_review > 0:
            review_link = f'<p><a href="/review">Review {needs_review} post(s) &rarr;</a></p>'
        elif auto_approved > 0:
            review_link = '<p><a href="/queue">View approved queue &rarr;</a></p>'

        html = f'''
        <article style="border-left:4px solid var(--qb-green);padding-left:1rem">
            <h4 style="color:var(--qb-green)">Fetch & Generate Complete</h4>
            <ul>
                <li><strong>{result["articles_fetched"]}</strong> articles fetched from RSS</li>
                <li><strong>{result["articles_saved"]}</strong> new articles saved</li>
                <li><strong>{len(result["selected"])}</strong> articles selected by Mistral</li>
                <li><strong>{posts_count}</strong> posts generated (batch: {result["batch_id"]})</li>
            </ul>
            <div style="display:flex;gap:1rem;font-size:0.85rem;margin:0.5rem 0">
                <span style="color:var(--qb-green)"><strong>{auto_approved}</strong> auto-approved</span>
                <span style="color:var(--qb-accent-soft)"><strong>{needs_review}</strong> to review</span>
                <span style="color:var(--qb-red)"><strong>{auto_rejected}</strong> auto-rejected</span>
            </div>
            {review_link}
        </article>
        '''
        resp = make_response(html)
        toast_msg = f"{posts_count} posts generated"
        if auto_approved > 0:
            toast_msg += f", {auto_approved} auto-approved"
        if needs_review > 0:
            toast_msg += f", {needs_review} to review"
        resp.headers["HX-Trigger"] = json.dumps({
            "showToast": {"type": "success", "message": toast_msg}
        })
        return resp
    else:
        errors = "<br>".join(result["errors"])
        html = f'''
        <article style="border-left:4px solid var(--qb-red);padding-left:1rem">
            <h4 style="color:var(--qb-red)">Error</h4>
            <p>{errors}</p>
        </article>
        '''
        resp = make_response(html)
        resp.headers["HX-Trigger"] = json.dumps({
            "showToast": {"type": "error", "message": "Pipeline failed. Check errors below."}
        })
        return resp


@bp.route("/api/post-next", methods=["POST"])
def post_next_action():
    result = run_post_next()

    if result["success"]:
        html = f'''
        <article style="border-left:4px solid var(--qb-green);padding-left:1rem">
            <h4 style="color:var(--qb-green)">Tweet Posted!</h4>
            <p>{result["content"]}</p>
            <p><a href="https://x.com/QEdgeIntel/status/{result["tweet_id"]}" target="_blank">View on X</a></p>
        </article>
        '''
        resp = make_response(html)
        resp.headers["HX-Trigger"] = json.dumps({
            "showToast": {"type": "success", "message": "Tweet posted successfully!"}
        })
        return resp
    else:
        html = f'''
        <article style="border-left:4px solid var(--qb-red);padding-left:1rem">
            <h4 style="color:var(--qb-red)">Error</h4>
            <p>{result["error"]}</p>
        </article>
        '''
        resp = make_response(html)
        resp.headers["HX-Trigger"] = json.dumps({
            "showToast": {"type": "error", "message": f"Post failed: {result['error']}"}
        })
        return resp
