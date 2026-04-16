/**
 * X/Twitter Scraper for Social Bridge
 *
 * Inspired by likes-sync approach - extracts tweet data from the DOM
 * when browsing x.com with surf browser automation.
 *
 * Usage with surf CDP:
 *   surf cdp start
 *   surf go "https://x.com/malwaretechblog"
 *   surf wait 3
 *   # Inject this script via CDP JavaScript execution
 */

(function() {
    'use strict';

    const CONFIG = {
        maxTweets: 100,
        scrollDelay: 1000,
        loadTimeout: 5000,
    };

    /**
     * Extract tweet data from a single article element
     */
    function extractTweet(article) {
        try {
            // Author info
            const authorLink = article.querySelector('[data-testid="User-Name"] a[role="link"]');
            const authorName = authorLink ? authorLink.textContent.trim() : '';
            const authorHandle = article.querySelector('[data-testid="User-Name"] a[href^="/"]');
            const handle = authorHandle ? authorHandle.getAttribute('href').replace('/', '') : '';

            // Tweet content
            const tweetText = article.querySelector('[data-testid="tweetText"]');
            const content = tweetText ? tweetText.innerText : '';

            // Skip if no content
            if (!content) return null;

            // Timestamp and link
            const timeEl = article.querySelector('time');
            const timestamp = timeEl ? timeEl.getAttribute('datetime') : new Date().toISOString();

            const statusLink = article.querySelector('a[href*="/status/"]');
            const tweetUrl = statusLink ? 'https://x.com' + statusLink.getAttribute('href') : '';

            // Extract tweet ID from URL
            const tweetId = tweetUrl.match(/status\/(\d+)/)?.[1] || '';

            // Engagement metrics
            const metrics = {};

            const replyButton = article.querySelector('[data-testid="reply"]');
            const retweetButton = article.querySelector('[data-testid="retweet"]');
            const likeButton = article.querySelector('[data-testid="like"]');
            const viewsEl = article.querySelector('a[href$="/analytics"]');

            if (replyButton) {
                const replyText = replyButton.getAttribute('aria-label') || '';
                metrics.replies = parseInt(replyText.match(/(\d+)/)?.[1] || '0');
            }

            if (retweetButton) {
                const rtText = retweetButton.getAttribute('aria-label') || '';
                metrics.retweets = parseInt(rtText.match(/(\d+)/)?.[1] || '0');
            }

            if (likeButton) {
                const likeText = likeButton.getAttribute('aria-label') || '';
                metrics.likes = parseInt(likeText.match(/(\d+)/)?.[1] || '0');
            }

            if (viewsEl) {
                const viewText = viewsEl.textContent || '';
                metrics.views = viewText;
            }

            // Check for media
            const hasImage = article.querySelector('[data-testid="tweetPhoto"]') !== null;
            const hasVideo = article.querySelector('[data-testid="videoPlayer"]') !== null;
            const hasQuote = article.querySelector('[data-testid="quoteTweet"]') !== null;

            return {
                id: tweetId,
                author: authorName,
                handle: handle,
                content: content,
                url: tweetUrl,
                timestamp: timestamp,
                metrics: metrics,
                media: {
                    hasImage: hasImage,
                    hasVideo: hasVideo,
                    hasQuote: hasQuote,
                }
            };
        } catch (e) {
            console.error('Error extracting tweet:', e);
            return null;
        }
    }

    /**
     * Get all visible tweets on the page
     */
    function getAllTweets() {
        const articles = document.querySelectorAll('article[data-testid="tweet"]');
        const tweets = [];
        const seenIds = new Set();

        articles.forEach(article => {
            const tweet = extractTweet(article);
            if (tweet && tweet.id && !seenIds.has(tweet.id)) {
                seenIds.add(tweet.id);
                tweets.push(tweet);
            }
        });

        return tweets;
    }

    /**
     * Scroll and collect tweets until limit or no new tweets
     */
    async function collectTweets(maxTweets = CONFIG.maxTweets) {
        const allTweets = [];
        const seenIds = new Set();
        let noNewTweetsCount = 0;
        const maxNoNewTweets = 3;

        while (allTweets.length < maxTweets && noNewTweetsCount < maxNoNewTweets) {
            // Get current tweets
            const currentTweets = getAllTweets();
            let newTweetsFound = 0;

            currentTweets.forEach(tweet => {
                if (!seenIds.has(tweet.id)) {
                    seenIds.add(tweet.id);
                    allTweets.push(tweet);
                    newTweetsFound++;
                }
            });

            if (newTweetsFound === 0) {
                noNewTweetsCount++;
            } else {
                noNewTweetsCount = 0;
            }

            // Scroll down
            window.scrollBy(0, window.innerHeight);

            // Wait for new content to load
            await new Promise(resolve => setTimeout(resolve, CONFIG.scrollDelay));

            // Check if we've reached the end
            if (allTweets.length >= maxTweets) break;
        }

        return allTweets.slice(0, maxTweets);
    }

    /**
     * Get current page type
     */
    function getPageType() {
        const path = window.location.pathname;

        if (path.includes('/status/')) return 'single_tweet';
        if (path.includes('/likes')) return 'likes';
        if (path.includes('/with_replies')) return 'replies';
        if (path.includes('/media')) return 'media';
        if (path === '/' || path === '/home') return 'home';
        if (path.startsWith('/search')) return 'search';
        if (path.match(/^\/\w+$/)) return 'profile';

        return 'unknown';
    }

    /**
     * Get profile info if on a profile page
     */
    function getProfileInfo() {
        try {
            const nameEl = document.querySelector('[data-testid="UserName"]');
            const bioEl = document.querySelector('[data-testid="UserDescription"]');
            const followersEl = document.querySelector('a[href$="/verified_followers"]');
            const followingEl = document.querySelector('a[href$="/following"]');

            return {
                name: nameEl ? nameEl.textContent : '',
                bio: bioEl ? bioEl.textContent : '',
                followers: followersEl ? followersEl.textContent : '',
                following: followingEl ? followingEl.textContent : '',
            };
        } catch (e) {
            return null;
        }
    }

    // Main execution
    const pageType = getPageType();
    const tweets = getAllTweets();  // Immediate collection (no scrolling)
    const profile = getProfileInfo();

    // Return results as JSON string for parsing
    return JSON.stringify({
        success: true,
        pageType: pageType,
        url: window.location.href,
        profile: profile,
        tweets: tweets,
        count: tweets.length,
        timestamp: new Date().toISOString(),
    }, null, 2);
})();
