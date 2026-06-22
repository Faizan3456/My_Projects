from playwright.sync_api import sync_playwright

with sync_playwright() as p:
    context = p.chromium.launch_persistent_context(
        user_data_dir="./linkedin_profile",
        headless=False
    )

    page = context.new_page()
    page.goto("https://www.linkedin.com")

    input("Log in once, then press Enter...")
    context.close()
