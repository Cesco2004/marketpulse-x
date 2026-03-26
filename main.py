#!/usr/bin/env python3
"""
Quantum Brief Bot - CLI Orchestrator

Usage:
    python main.py fetch              Fetch RSS, score articles, rank with Mistral, generate posts
    python main.py review             Review and approve/reject pending posts
    python main.py post               Post the next approved tweet immediately
    python main.py run                Start the 24h scheduler daemon
    python main.py status             Show current queue stats
    python main.py verify             Verify API credentials
    python main.py kill [reason]      Activate kill switch (stops all API calls)
    python main.py unkill             Deactivate kill switch
    python main.py limits             Show current usage limits and today's usage
    python main.py engage status      Show engagement system status
    python main.py engage add @user   Add a target account to monitor
    python main.py engage list        List target accounts
    python main.py engage poll        Run one poll cycle manually
    python main.py engage start       Start engagement monitor (foreground, Ctrl+C to stop)
    python main.py engage start -d    Start engagement monitor as background daemon
    python main.py engage stop        Stop the engagement monitor (daemon or in-process)
"""

import sys

from storage.database import (
    init_db,
    save_articles,
    save_posts,
    get_pending_posts,
    get_approved_posts,
    update_post_status,
    update_post_content,
    mark_as_posted,
    get_stats,
)
from publisher.x_publisher import post_tweet, verify_credentials
from scheduler.scheduler import scheduler as bot_scheduler
from pipeline import run_fetch_pipeline


def cmd_fetch():
    """Fetch all sources (RSS + HN + Reddit), score + rank articles, generate posts."""
    print("\n=== FETCH & GENERATE ===\n")

    print("[*] Running full pipeline (RSS + HackerNews + Reddit → rank → generate)...")
    result = run_fetch_pipeline()

    print(f"\n  Articles fetched: {result['articles_fetched']}")
    print(f"  New articles saved: {result['articles_saved']}")

    if result.get("skipped_reason"):
        print(f"  Skipped: {result['skipped_reason']}")
        return

    if result.get("errors"):
        for err in result["errors"]:
            print(f"  Error: {err}")

    if result.get("prefiltered"):
        print(f"\n  Pre-filtered (top {len(result['prefiltered'])}):")
        for i, a in enumerate(result["prefiltered"][:10], 1):
            kw = ", ".join(a["keywords"][:3]) if a.get("keywords") else ""
            print(f"    {i}. [score={a['score']}] [{a['source']}] {a['title'][:60]}  ({kw})")

    if result.get("selected"):
        print(f"\n  Selected for generation ({len(result['selected'])}):")
        for i, a in enumerate(result["selected"], 1):
            print(f"    {i}. [{a['source']}] {a['title'][:70]}")

    if result.get("posts"):
        print(f"\n  Generated {len(result['posts'])} posts (batch: {result.get('batch_id', '?')})")
        print(f"    Auto-approved: {result.get('auto_approved', 0)}")
        print(f"    Auto-rejected: {result.get('auto_rejected', 0)}")
        print(f"    Needs review: {result.get('needs_review', 0)}")

        for i, p in enumerate(result["posts"], 1):
            score = p.get("quality_score", "?")
            ptype = p.get("type", "?")
            hint = f" [img: {p['image_hint']}]" if p.get("image_hint") else ""
            print(f"\n  --- Post {i} ({ptype}, score={score}){hint} ---")
            print(f"  {p['content'][:200]}")

    if result["success"]:
        print("\n  Done. Run 'python main.py review' to approve pending posts.\n")
    else:
        print("\n  Pipeline finished with errors.\n")


def cmd_review():
    """Interactive review of pending posts."""
    print("\n=== REVIEW POSTS ===\n")

    posts = get_pending_posts()
    if not posts:
        print("No posts pending review. Run 'python main.py fetch' first.\n")
        return

    print(f"{len(posts)} post(s) pending review.\n")
    print("Commands: [a]pprove  [r]eject  [e]dit  [s]kip  [q]uit\n")

    for post in posts:
        print(f"--- Post #{post['id']} ({post['post_type']}) ---")
        print(f"{post['content']}")
        print(f"({len(post['content'])} chars)")
        print()

        while True:
            action = input("Action [a/r/e/s/q]: ").strip().lower()

            if action == "a":
                update_post_status(post["id"], "approved")
                print("  -> Approved.\n")
                break
            elif action == "r":
                update_post_status(post["id"], "rejected")
                print("  -> Rejected.\n")
                break
            elif action == "e":
                print("  Enter new content (press Enter when done):")
                new_content = input("  > ").strip()
                if new_content:
                    update_post_content(post["id"], new_content)
                    update_post_status(post["id"], "approved")
                    print(f"  -> Edited and approved. ({len(new_content)} chars)\n")
                else:
                    print("  -> No change.\n")
                break
            elif action == "s":
                print("  -> Skipped.\n")
                break
            elif action == "q":
                print("  Exiting review.\n")
                return
            else:
                print("  Invalid action. Use a/r/e/s/q.")

    print("Review complete.\n")


def cmd_post():
    """Post the next approved tweet immediately."""
    print("\n=== POST NEXT TWEET ===\n")

    posts = get_approved_posts()
    if not posts:
        print("No approved posts in queue. Run 'python main.py review' first.\n")
        return

    post = posts[0]
    print(f"Posting: {post['content']}")
    print(f"({len(post['content'])} chars)\n")

    confirm = input("Confirm? [y/n]: ").strip().lower()
    if confirm != "y":
        print("Cancelled.\n")
        return

    try:
        tweet_id = post_tweet(post["content"])
        mark_as_posted(post["id"], tweet_id)
        print(f"\nPosted successfully. Tweet ID: {tweet_id}\n")
    except Exception as e:
        print(f"\nError posting: {e}\n")


def cmd_run():
    """Start the scheduler daemon."""
    print("\n=== SCHEDULER ===\n")

    approved = get_approved_posts()
    print(f"Approved posts in queue: {len(approved)}\n")

    if not approved:
        print("No approved posts. Run fetch + review first.\n")
        return

    bot_scheduler.start()

    # Keep main thread alive while scheduler runs
    try:
        while bot_scheduler.is_running:
            import time
            time.sleep(1)
    except KeyboardInterrupt:
        bot_scheduler.stop()
        print("\nScheduler stopped.")


def cmd_status():
    """Show current queue stats."""
    print("\n=== STATUS ===\n")

    stats = get_stats()
    print(f"  Articles in DB:    {stats.get('total_articles', 0)}")
    print(f"  Pending review:    {stats.get('pending_review', 0)}")
    print(f"  Approved (queue):  {stats.get('approved', 0)}")
    print(f"  Posted:            {stats.get('posted', 0)}")
    print(f"  Rejected:          {stats.get('rejected', 0)}")
    print()


def cmd_verify():
    """Verify API credentials."""
    print("\n=== VERIFY CREDENTIALS ===\n")

    print("[Mistral]")
    try:
        from mistralai import Mistral
        import config
        client = Mistral(api_key=config.MISTRAL_API_KEY)
        response = client.chat.complete(
            model="mistral-small-latest",
            messages=[{"role": "user", "content": "Say 'OK' if you can read this."}],
        )
        print(f"  Mistral OK: {response.choices[0].message.content.strip()}")
    except Exception as e:
        print(f"  Mistral error: {e}")
    print()

    print("[X/Twitter]")
    verify_credentials()
    print()


def cmd_engage():
    """Engagement system commands."""
    if len(sys.argv) < 3:
        print("""
Usage:
    python main.py engage status      Show engagement system status
    python main.py engage add @user   Add a target account to monitor
    python main.py engage list        List target accounts
    python main.py engage poll        Run one poll cycle manually
    python main.py engage start       Start engagement monitor (foreground, Ctrl+C to stop)
    python main.py engage start -d    Start engagement monitor as background daemon
    python main.py engage stop        Stop the engagement monitor (daemon or in-process)
""")
        return

    from storage.database import (
        get_engagement_config,
        get_target_accounts,
        add_target_account,
        get_engagement_replies_today,
        get_engagement_history,
    )

    subcmd = sys.argv[2]

    if subcmd == "status":
        cfg = get_engagement_config()
        accounts = get_target_accounts()
        today = get_engagement_replies_today()
        recent = get_engagement_history(limit=5)

        print("\n=== ENGAGEMENT STATUS ===\n")
        print(f"  Enabled:              {'Yes' if cfg.get('is_enabled') else 'No'}")
        print(f"  Poll interval:        {cfg.get('poll_interval_minutes', 10)} min")
        print(f"  Target accounts:      {len(accounts)} ({sum(1 for a in accounts if a['is_enabled'])} active)")
        print(f"  Replies today:        {today} / {cfg.get('max_replies_per_day', 10)}")
        print(f"  Active hours:         {cfg.get('active_start_hour', 8)}h - {cfg.get('active_end_hour', 23)}h ({cfg.get('timezone', 'Europe/Paris')})")
        print(f"  Reply delay:          {cfg.get('reply_delay_min_minutes', 2)}-{cfg.get('reply_delay_max_minutes', 15)} min")
        print(f"  Auto-reject below:    {cfg.get('auto_reject_below', 35)}")

        if recent:
            print(f"\n  Last 5 replies:")
            for r in recent:
                status_icon = {"posted": "+", "approved": "~", "rejected": "x"}.get(r["status"], "?")
                print(f"    [{status_icon}] @{r['target_username']}: {r['reply_content'][:60]}...")
        print()

    elif subcmd == "add":
        if len(sys.argv) < 4:
            print("Usage: python main.py engage add @username [category] [style]")
            return
        username = sys.argv[3].lstrip("@")
        category = sys.argv[4] if len(sys.argv) > 4 else "general"
        style = sys.argv[5] if len(sys.argv) > 5 else "mixed"

        result = add_target_account(username, category, style)
        if result:
            print(f"\n  Added @{username} (category={category}, style={style})\n")
        else:
            print(f"\n  @{username} already exists.\n")

    elif subcmd == "list":
        accounts = get_target_accounts()
        if not accounts:
            print("\n  No target accounts. Use 'python main.py engage add @username' to add one.\n")
            return

        print(f"\n=== TARGET ACCOUNTS ({len(accounts)}) ===\n")
        for a in accounts:
            status = "ON" if a["is_enabled"] else "OFF"
            polled = a.get("last_polled_at", "never")
            errors = a.get("poll_errors", 0)
            err_str = f" [!{errors} errors]" if errors else ""
            print(f"  [{status}] @{a['username']} (cat={a['category']}, style={a['reply_style']}, prio={a['priority']}){err_str}")
            print(f"        user_id={a.get('user_id', '?')} | last_polled={polled}")
        print()

    elif subcmd == "poll":
        print("\n=== MANUAL POLL ===\n")
        from engagement.monitor import engagement_monitor
        result = engagement_monitor.poll_once()
        print(f"\n  Poll complete:")
        print(f"    New tweets found:   {result.get('new_tweets', 0)}")
        print(f"    Replies generated:  {result.get('replies_generated', 0)}")
        print(f"    Replies posted:     {result.get('replies_posted', 0)}")
        print(f"    Errors:             {result.get('errors', 0)}")
        print()

    elif subcmd == "start":
        print("\n=== ENGAGEMENT MONITOR ===\n")
        from engagement.monitor import engagement_monitor
        import signal

        accounts = get_target_accounts(enabled_only=True)
        if not accounts:
            print("  No active target accounts. Add one first with 'engage add @username'.\n")
            return

        daemon_mode = "--daemon" in sys.argv or "-d" in sys.argv

        if daemon_mode:
            # Write PID file for stop command
            import os
            pid_file = os.path.join(os.path.dirname(__file__), "data", "engage.pid")
            with open(pid_file, "w") as f:
                f.write(str(os.getpid()))
            print(f"  PID {os.getpid()} written to {pid_file}")

        print(f"  Monitoring {len(accounts)} account(s).")
        if not daemon_mode:
            print("  Press Ctrl+C to stop.\n")
        else:
            print("  Running as daemon. Stop with 'python main.py engage stop'.\n")

        engagement_monitor.start()

        def _handle_stop(signum, frame):
            engagement_monitor.stop()
            if daemon_mode:
                try:
                    os.remove(pid_file)
                except OSError:
                    pass
            sys.exit(0)

        signal.signal(signal.SIGTERM, _handle_stop)

        try:
            while engagement_monitor.is_running:
                import time
                time.sleep(1)
        except KeyboardInterrupt:
            engagement_monitor.stop()
            if daemon_mode:
                try:
                    os.remove(pid_file)
                except OSError:
                    pass
            print("\n  Monitor stopped.\n")

    elif subcmd == "stop":
        import os, signal as sig
        from storage.database import update_engagement_config
        pid_file = os.path.join(os.path.dirname(__file__), "data", "engage.pid")

        # Set is_enabled=0 in DB (stops the loop)
        update_engagement_config(is_enabled=0)

        # Kill daemon process if running
        if os.path.exists(pid_file):
            try:
                pid = int(open(pid_file).read().strip())
                os.kill(pid, sig.SIGTERM)
                print(f"\n  Sent SIGTERM to daemon (PID {pid}).")
            except (ProcessLookupError, ValueError):
                print("\n  Daemon process not found (already stopped?).")
            try:
                os.remove(pid_file)
            except OSError:
                pass
        else:
            # In-process stop (from dashboard or same process)
            from engagement.monitor import engagement_monitor
            engagement_monitor.stop()

        print("  Engagement monitor stopped.\n")

    else:
        print(f"\n  Unknown subcommand: {subcmd}")
        print("  Use: status, add, list, poll, start, stop\n")


def cmd_kill():
    """Activate the kill switch — blocks all API calls."""
    from storage.database import set_kill_switch
    reason = " ".join(sys.argv[2:]) if len(sys.argv) > 2 else "Manual kill via CLI"
    set_kill_switch(True, reason=reason, killed_by="cli")
    print(f"\n  Kill switch ACTIVATED.")
    print(f"  Reason: {reason}")
    print(f"  All API calls are now blocked.")
    print(f"  Run 'python main.py unkill' to resume.\n")


def cmd_unkill():
    """Deactivate the kill switch."""
    from storage.database import set_kill_switch
    set_kill_switch(False)
    print("\n  Kill switch DEACTIVATED. Bot can resume API calls.\n")


def cmd_limits():
    """Show current usage limits and today's consumption."""
    from limiter.usage_limiter import usage_limiter
    status = usage_limiter.get_status()

    print("\n=== USAGE LIMITS ===\n")

    if status["kill_switch"]:
        print(f"  !! KILL SWITCH ACTIVE: {status['kill_reason']}\n")

    print(f"  Mistral API:")
    print(f"    Calls:  {status['mistral_calls']}/{status['mistral_calls_max']}  ({status['mistral_calls_pct']:.0f}%)")
    print(f"    Tokens: {status['mistral_tokens']}/{status['mistral_tokens_max']}  ({status['mistral_tokens_pct']:.0f}%)")
    print(f"    Cost:   ${status['mistral_cost']:.4f}/${status['mistral_cost_max']:.2f}  ({status['mistral_cost_pct']:.0f}%)")
    print()
    print(f"  Twitter/X:")
    print(f"    Tweets:  {status['x_tweets']}/{status['x_tweets_max']}  ({status['x_tweets_pct']:.0f}%)")
    print(f"    Replies: {status['x_replies']}/{status['x_replies_max']}  ({status['x_replies_pct']:.0f}%)")
    print()

    if status["consecutive_errors"] > 0:
        print(f"  Consecutive errors: {status['consecutive_errors']}")

    limits = status["limits"]
    print(f"  Alerts: {'enabled' if limits.get('alerts_enabled') else 'disabled'}")
    if limits.get("alert_email"):
        print(f"  Alert email: {limits['alert_email']}")
    print()


COMMANDS = {
    "fetch": cmd_fetch,
    "review": cmd_review,
    "post": cmd_post,
    "run": cmd_run,
    "status": cmd_status,
    "verify": cmd_verify,
    "engage": cmd_engage,
    "kill": cmd_kill,
    "unkill": cmd_unkill,
    "limits": cmd_limits,
}


def main():
    init_db()

    if len(sys.argv) < 2 or sys.argv[1] not in COMMANDS:
        print(__doc__)
        return

    command = sys.argv[1]
    COMMANDS[command]()


if __name__ == "__main__":
    main()
