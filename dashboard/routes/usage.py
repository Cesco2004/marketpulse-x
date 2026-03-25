from flask import Blueprint, render_template
from storage.database import get_api_usage_summary, get_monthly_usage, get_monthly_usage_by_day, get_monthly_usage_by_endpoint
from limiter.budget_forecaster import get_budget_status

bp = Blueprint("usage", __name__)


@bp.route("/usage")
def usage_page():
    usage = get_api_usage_summary()

    # Monthly data
    mistral_monthly = get_monthly_usage("mistral")
    groq_monthly = get_monthly_usage("groq")
    mistral_by_day = get_monthly_usage_by_day("mistral")
    groq_by_day = get_monthly_usage_by_day("groq")
    mistral_by_endpoint = get_monthly_usage_by_endpoint("mistral")
    groq_by_endpoint = get_monthly_usage_by_endpoint("groq")
    mistral_budget = get_budget_status("mistral")
    groq_budget = get_budget_status("groq")

    return render_template("usage.html", usage=usage,
                           mistral_monthly=mistral_monthly,
                           groq_monthly=groq_monthly,
                           mistral_by_day=mistral_by_day,
                           groq_by_day=groq_by_day,
                           mistral_by_endpoint=mistral_by_endpoint,
                           groq_by_endpoint=groq_by_endpoint,
                           mistral_budget=mistral_budget,
                           groq_budget=groq_budget)
