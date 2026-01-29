"""
Social Bridge Twitter/X Module

Handles X/Twitter account monitoring using surf browser automation.
"""

import logging
import subprocess
from datetime import datetime, timezone

from social_bridge.config import DEFAULT_X_ACCOUNTS
from social_bridge.utils import SocialPost

logger = logging.getLogger("social-bridge.twitter")


def check_surf_available() -> bool:
    """Check if surf CLI is available.

    Returns:
        True if surf is installed and accessible
    """
    try:
        result = subprocess.run(["which", "surf"], capture_output=True)
        return result.returncode == 0
    except Exception:
        return False


def check_surf_extension_connected() -> bool:
    """Check if surf browser extension is connected.

    Returns:
        True if the extension is responding
    """
    try:
        result = subprocess.run(
            ["surf", "tab.list"],
            capture_output=True,
            timeout=5
        )
        return result.returncode == 0
    except Exception:
        return False


def normalize_account_name(account: str) -> str:
    """Normalize an X/Twitter account name.

    Removes @ prefix and whitespace.

    Args:
        account: Account identifier (@name or name)

    Returns:
        Clean account username
    """
    return account.replace("@", "").strip()


def fetch_x_account(account: str, limit: int = 50) -> list[SocialPost]:
    """Fetch tweets from X account using surf browser automation.

    Inspired by likes-sync approach - uses surf to navigate and inject
    JavaScript to extract tweet data from the DOM.

    Args:
        account: X/Twitter username
        limit: Maximum tweets to fetch

    Returns:
        List of SocialPost objects
    """
    # Normalize account name to handle @ prefix
    account = normalize_account_name(account)

    if not check_surf_available():
        logger.warning(f"surf CLI not available; skipping @{account}")
        return []
    if not check_surf_extension_connected():
        logger.warning("surf extension not connected; scraping may be incomplete")

    posts = []
    url = f"https://x.com/{account}"

    try:
        # Use surf to navigate
        subprocess.run(["surf", "go", url], capture_output=True, timeout=30)

        # Wait for page to load
        subprocess.run(["surf", "wait", "3"], capture_output=True, timeout=10)

        # Scroll to load more tweets
        for _ in range(min(limit // 10, 5)):
            subprocess.run(["surf", "scroll", "down"], capture_output=True, timeout=5)
            subprocess.run(["surf", "wait", "1"], capture_output=True, timeout=5)

        # Note: surf doesn't have direct JS execution, so we use text extraction
        # Full implementation would use CDP for JS injection
        logger.debug("Using basic text extraction (full scraping requires CDP mode)")

        # Use surf read to get page content and parse
        result = subprocess.run(
            ["surf", "text"],
            capture_output=True,
            text=True,
            timeout=30
        )

        if result.returncode == 0 and result.stdout:
            # Parse text content (basic extraction)
            # This is a simplified version - full implementation would use JS injection
            lines = result.stdout.split('\n')
            current_content = []

            for line in lines:
                line = line.strip()
                if line and len(line) > 20:  # Skip short lines
                    current_content.append(line)

            # Create a single aggregated post for now
            if current_content:
                posts.append(SocialPost(
                    platform="x",
                    source=account,
                    author=f"@{account}",
                    content="\n".join(current_content[:5]),  # First 5 substantial lines
                    url=url,
                    timestamp=datetime.now(timezone.utc),
                    metadata={"extraction": "basic_text"}
                ))

    except subprocess.TimeoutExpired:
        logger.error(f"Timeout fetching @{account}")
    except Exception as e:
        logger.error(f"Error fetching @{account}: {e}")

    return posts


def fetch_accounts(accounts: list[str], limit: int = 50) -> list[SocialPost]:
    """Fetch tweets from multiple X accounts.

    Args:
        accounts: List of X/Twitter usernames
        limit: Maximum tweets per account

    Returns:
        List of SocialPost objects from all accounts
    """
    all_posts = []
    for account in accounts:
        posts = fetch_x_account(account, limit)
        all_posts.extend(posts)
    return all_posts


def get_default_accounts() -> list[dict]:
    """Get list of default security-focused X/Twitter accounts.

    Returns:
        List of dicts with 'name' and 'focus' keys
    """
    return DEFAULT_X_ACCOUNTS.copy()


# JavaScript scraper for full extraction (for reference/future use with CDP)
TWEET_SCRAPER_JS = """
(function() {
    const tweets = [];
    const articles = document.querySelectorAll('article[data-testid="tweet"]');

    articles.forEach((article, index) => {
        if (index >= MAX_LIMIT) return;

        try {
            // Get author
            const authorEl = article.querySelector('[data-testid="User-Name"] a');
            const author = authorEl ? authorEl.textContent : 'unknown';

            // Get tweet text
            const textEl = article.querySelector('[data-testid="tweetText"]');
            const content = textEl ? textEl.textContent : '';

            // Get timestamp
            const timeEl = article.querySelector('time');
            const timestamp = timeEl ? timeEl.getAttribute('datetime') : new Date().toISOString();

            // Get tweet link
            const linkEl = article.querySelector('a[href*="/status/"]');
            const url = linkEl ? 'https://x.com' + linkEl.getAttribute('href') : '';

            // Get engagement metrics
            const metrics = {};
            const replyEl = article.querySelector('[data-testid="reply"]');
            const retweetEl = article.querySelector('[data-testid="retweet"]');
            const likeEl = article.querySelector('[data-testid="like"]');

            if (replyEl) metrics.replies = replyEl.textContent || '0';
            if (retweetEl) metrics.retweets = retweetEl.textContent || '0';
            if (likeEl) metrics.likes = likeEl.textContent || '0';

            if (content) {
                tweets.push({
                    author: author,
                    content: content,
                    timestamp: timestamp,
                    url: url,
                    metrics: metrics
                });
            }
        } catch (e) {
            console.error('Error parsing tweet:', e);
        }
    });

    return JSON.stringify(tweets);
})();
"""
