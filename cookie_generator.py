import asyncio
import os
from pathlib import Path
from dotenv import load_dotenv
from playwright.async_api import async_playwright
import logging

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class YouTubeCookieGenerator:
    """Generate YouTube cookies using Playwright for yt-dlp authentication"""

    def __init__(self):
        # Load environment variables
        load_dotenv()
        self.email = os.getenv('YOUTUBE_EMAIL')
        self.password = os.getenv('YOUTUBE_PASSWORD')
        self.cookies_path = os.path.join('assets', 'cookies.txt')

        if not self.email or not self.password:
            raise ValueError("YOUTUBE_EMAIL and YOUTUBE_PASSWORD must be set in .env file")

    async def generate_cookies(self):
        """Generate YouTube cookies by automating login"""
        logger.info("Starting YouTube cookie generation...")

        async with async_playwright() as p:
            # Launch browser with realistic settings
            browser = await p.chromium.launch(
                headless=True,
                args=[
                    '--no-sandbox',
                    '--disable-setuid-sandbox',
                    '--disable-dev-shm-usage',
                    '--disable-accelerated-2d-canvas',
                    '--no-first-run',
                    '--no-zygote',
                    '--single-process',
                    '--disable-gpu',
                    '--disable-web-security',
                    '--disable-features=VizDisplayCompositor'
                ]
            )

            context = await browser.new_context(
                viewport={'width': 1280, 'height': 720},
                user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
            )

            page = await context.new_page()

            try:
                logger.info("Navigating to YouTube...")
                await page.goto('https://www.youtube.com', wait_until='networkidle', timeout=30000)

                # Click sign in button
                logger.info("Clicking sign in button...")
                await page.click('text=Sign in', timeout=10000)

                # Wait for Google login page
                await page.wait_for_url('**/accounts.google.com/**', timeout=15000)
                logger.info("Google login page loaded")

                # Enter email
                logger.info("Entering email...")
                await page.fill('input[type="email"]', self.email)
                await page.click('#identifierNext')

                # Wait for password field
                await page.wait_for_selector('input[type="password"]', timeout=10000)

                # Enter password
                logger.info("Entering password...")
                await page.fill('input[type="password"]', self.password)
                await page.click('#passwordNext')

                # Wait for successful login and YouTube redirect
                logger.info("Waiting for login completion...")
                await page.wait_for_url('https://www.youtube.com/**', timeout=30000)

                # Additional wait for cookies to be fully set
                await page.wait_for_timeout(5000)

                # Verify we're logged in by checking for avatar or account menu
                try:
                    await page.wait_for_selector('[aria-label*="Account"]', timeout=5000)
                    logger.info("✅ Successfully logged into YouTube!")
                except:
                    logger.warning("⚠️ Could not verify login status, but proceeding...")

                # Get all cookies
                cookies = await context.cookies()
                logger.info(f"Retrieved {len(cookies)} cookies from browser")

                # Convert to Netscape cookie format for yt-dlp
                netscape_cookies = []
                for cookie in cookies:
                    # Skip cookies that don't have required fields
                    if not all(key in cookie for key in ['name', 'value', 'domain', 'path']):
                        continue

                    # Format: domain, flag, path, secure, expiration, name, value
                    flag = 'TRUE' if cookie.get('httpOnly', False) else 'FALSE'
                    secure = 'TRUE' if cookie.get('secure', False) else 'FALSE'
                    expiry = str(int(cookie.get('expires', 2147483647)))  # Far future if no expiry

                    netscape_cookies.append(
                        f"{cookie['domain']}\t{flag}\t{cookie['path']}\t{secure}\t{expiry}\t{cookie['name']}\t{cookie['value']}"
                    )

                # Ensure output directory exists
                os.makedirs(os.path.dirname(self.cookies_path), exist_ok=True)

                # Write cookies in Netscape format
                with open(self.cookies_path, 'w', encoding='utf-8') as f:
                    f.write("# Netscape HTTP Cookie File\n")
                    f.write("# Generated by Playwright YouTube login automation\n")
                    f.write("# https://curl.se/docs/http-cookies.html\n")
                    f.write(f"# Generated on: {asyncio.get_event_loop().time()}\n\n")
                    f.write('\n'.join(netscape_cookies))

                logger.info(f"✅ Cookies saved to {self.cookies_path}")
                logger.info(f"Generated {len(netscape_cookies)} cookies")

                return True

            except Exception as e:
                logger.error(f"❌ Login failed: {e}")
                raise
            finally:
                await browser.close()

async def main():
    """Main function to run cookie generation"""
    try:
        generator = YouTubeCookieGenerator()
        await generator.generate_cookies()
        logger.info("🎉 Cookie generation completed successfully!")
        logger.info("Your music bot can now access authenticated YouTube content.")
    except ValueError as e:
        logger.error(f"Configuration error: {e}")
        logger.info("Please make sure your .env file contains:")
        logger.info("YOUTUBE_EMAIL=your.email@gmail.com")
        logger.info("YOUTUBE_PASSWORD=your_password")
    except Exception as e:
        logger.error(f"Unexpected error: {e}")
        return 1
    return 0

if __name__ == "__main__":
    exit_code = asyncio.run(main())
