import os
import time

from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeoutError


def publish_post(
    title: str,
    body_html: str,
    substack_url: str | None = None,
    email: str | None = None,
    password: str | None = None,
) -> str:
    """
    Publishes a post to Substack via Playwright.
    Returns the published post URL.

    Credentials can be passed directly (multi-user) or fall back to env vars
    (single-user / legacy).
    """
    substack_url = (substack_url or os.environ["SUBSTACK_URL"]).rstrip("/")
    email = email or os.environ["SUBSTACK_EMAIL"]
    password = password or os.environ["SUBSTACK_PASSWORD"]

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context()
        page = context.new_page()

        # ── Login ─────────────────────────────────────────────────────────────
        page.goto(f"{substack_url}/account/login", wait_until="networkidle")

        # Check if already logged in by looking for the dashboard
        if "dashboard" not in page.url and page.locator("input[type='email']").count():
            page.fill("input[type='email']", email)
            page.click("button[type='submit']")
            time.sleep(1)

            # Handle password step (some flows show it separately)
            if page.locator("input[type='password']").count():
                page.fill("input[type='password']", password)
                page.click("button[type='submit']")

            page.wait_for_url("**/dashboard/**", timeout=30_000)

        # ── Navigate to new post editor ───────────────────────────────────────
        page.goto(f"{substack_url}/publish/post", wait_until="networkidle")

        # ── Fill in title ─────────────────────────────────────────────────────
        title_selector = "[data-testid='post-title-input'], .post-title-input, h1[contenteditable]"
        page.wait_for_selector(title_selector, timeout=15_000)
        page.click(title_selector)
        page.keyboard.type(title, delay=30)

        # ── Inject body HTML ──────────────────────────────────────────────────
        # Substack's editor is ProseMirror / Tiptap; clipboard injection is
        # the most reliable way to get rich HTML in.
        body_selector = ".tiptap, .ProseMirror, [data-testid='post-body']"
        page.wait_for_selector(body_selector, timeout=15_000)
        page.click(body_selector)

        # Use clipboard to paste HTML
        page.evaluate(
            """(html) => {
                const dt = new DataTransfer();
                dt.setData('text/html', html);
                dt.setData('text/plain', html.replace(/<[^>]+>/g, ''));
                document.activeElement.dispatchEvent(
                    new ClipboardEvent('paste', {
                        bubbles: true,
                        cancelable: true,
                        clipboardData: dt
                    })
                );
            }""",
            body_html,
        )

        time.sleep(1)

        # ── Publish ───────────────────────────────────────────────────────────
        # Click the main "Publish" or "Continue" button
        publish_btn_selector = (
            "button:has-text('Publish'), "
            "button:has-text('Publish now'), "
            "[data-testid='publish-button']"
        )
        page.click(publish_btn_selector)

        # Some flows show a confirmation modal
        try:
            confirm_selector = (
                "button:has-text('Publish now'), "
                "button:has-text('Confirm'), "
                "[data-testid='confirm-publish']"
            )
            page.wait_for_selector(confirm_selector, timeout=5_000)
            page.click(confirm_selector)
        except PlaywrightTimeoutError:
            pass  # No confirmation modal

        # Wait for redirect to the published post
        page.wait_for_url(f"{substack_url}/p/**", timeout=30_000)
        post_url = page.url

        browser.close()

    return post_url
