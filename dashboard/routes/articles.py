from flask import Blueprint, render_template, request
from storage.database import get_articles, get_recent_articles, set_article_override, get_connection

bp = Blueprint("articles", __name__)


def _get_counts():
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) FROM articles")
    all_count = cursor.fetchone()[0]
    cursor.execute("SELECT COUNT(*) FROM articles WHERE stage IN ('prefiltered', 'ranked', 'selected')")
    prefiltered = cursor.fetchone()[0]
    cursor.execute("SELECT COUNT(*) FROM articles WHERE stage = 'selected'")
    selected = cursor.fetchone()[0]
    conn.close()
    return {"all": all_count, "prefiltered": prefiltered, "selected": selected}


@bp.route("/articles")
def articles_page():
    stage_filter = request.args.get("filter")
    if stage_filter:
        articles = get_articles(stage_filter)
    else:
        articles = get_recent_articles(limit=50)
    counts = _get_counts()
    return render_template("articles.html", articles=articles, filter=stage_filter, counts=counts)


@bp.route("/api/articles/<int:article_id>/include", methods=["POST"])
def include_article(article_id):
    set_article_override(article_id, "include")
    return '''
    <div class="post-card" style="border-color:var(--qb-green);opacity:0.7;padding:1rem;text-align:center">
        <strong style="color:var(--qb-green)">Included</strong> &mdash;
        <a href="/articles">Refresh to see updated list</a>
    </div>
    '''


@bp.route("/api/articles/<int:article_id>/exclude", methods=["POST"])
def exclude_article(article_id):
    set_article_override(article_id, "exclude")
    return '''
    <div class="post-card" style="border-color:var(--qb-red);opacity:0.5;padding:1rem;text-align:center">
        <strong style="color:var(--qb-red)">Excluded</strong> &mdash;
        <a href="/articles">Refresh to see updated list</a>
    </div>
    '''


@bp.route("/api/articles/<int:article_id>/clear-override", methods=["POST"])
def clear_override(article_id):
    set_article_override(article_id, None)
    return '''
    <div class="post-card" style="opacity:0.7;padding:1rem;text-align:center">
        Override cleared &mdash;
        <a href="/articles">Refresh to see updated list</a>
    </div>
    '''
