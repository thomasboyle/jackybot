#!/usr/bin/env python3
"""
YouTube Cookie Authentication Setup for JackyBot VPS

This script extracts YouTube cookies from your browser for VPS authentication.
Since yt-dlp dropped OAuth2 support, cookies are now the only authentication method.

Usage:
1. Log into YouTube in your browser (Chrome, Firefox, etc.)
2. Run locally: python setup_youtube_auth.py
3. Transfer cookies.txt to your VPS assets/ folder
4. Restart bot
"""

import os
import sys
import json
import yt_dlp
from yt_dlp.utils import YoutubeDLError
import subprocess
import platform

def extract_browser_cookies():
    """Extract YouTube cookies from browser using yt-dlp"""
    print("YouTube Cookie Extraction Setup")
    print("=" * 50)

    # Create assets directory if it doesn't exist
    assets_dir = os.path.join(os.path.dirname(__file__), 'assets')
    os.makedirs(assets_dir, exist_ok=True)

    cookies_file = os.path.join(assets_dir, 'cookies.txt')

    print("This will extract YouTube cookies from your browser.")
    print("Make sure you're logged into YouTube in your browser first!")
    print()

    # Detect available browsers
    system = platform.system().lower()
    browsers = []

    if system == "windows":
        browsers = ["chrome", "firefox", "edge"]
    elif system == "darwin":  # macOS
        browsers = ["chrome", "firefox", "safari"]
    else:  # Linux
        browsers = ["chrome", "firefox"]

    print("Available browsers to extract from:")
    for i, browser in enumerate(browsers, 1):
        print(f"{i}. {browser}")

    while True:
        try:
            choice = input(f"\nChoose browser (1-{len(browsers)}): ").strip()
            browser_idx = int(choice) - 1
            if 0 <= browser_idx < len(browsers):
                selected_browser = browsers[browser_idx]
                break
            else:
                print("Invalid choice. Please enter a valid number.")
        except ValueError:
            print("Invalid input. Please enter a number.")

    print(f"\nExtracting cookies from {selected_browser}...")

    try:
        # Use yt-dlp to extract cookies
        cmd = [
            sys.executable, "-m", "yt_dlp",
            "--cookies-from-browser", selected_browser,
            "--cookies", cookies_file,
            "--skip-download",
            "--print", "%(id)s",
            "https://www.youtube.com/watch?v=dQw4w9WgXcQ"
        ]

        result = subprocess.run(cmd, capture_output=True, text=True, cwd=os.path.dirname(__file__))

        if result.returncode == 0:
            print("[SUCCESS] Cookies extracted successfully!")
            print(f"Cookies saved to: {cookies_file}")
            print()
            print("Transfer instructions for VPS:")
            print("1. Copy assets/cookies.txt to your VPS")
            print("2. Place it in the jackybot/assets/ directory")
            print("3. Restart your bot: docker compose restart")
            print()
            print("Note: Cookies expire periodically. Re-run this script when needed.")
            return True
        else:
            print("[ERROR] Cookie extraction failed!")
            print("Error output:", result.stderr)
            print()
            print("Troubleshooting:")
            print("1. Make sure you're logged into YouTube in your browser")
            print("2. Close all browser instances and try again")
            print("3. Try a different browser")
            print("4. Check if your browser version is supported")
            return False

    except Exception as e:
        print(f"[ERROR] Unexpected error: {e}")
        return False

def test_current_auth():
    """Test current authentication method"""
    print("\nTesting Current Authentication")
    print("=" * 40)

    assets_dir = os.path.join(os.path.dirname(__file__), 'assets')
    cookies_file = os.path.join(assets_dir, 'cookies.txt')

    if os.path.exists(cookies_file):
        print("[INFO] Cookies file found")
        try:
            ydl_opts = {
                'cookiefile': cookies_file,
                'quiet': True,
            }
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info('https://www.youtube.com/watch?v=dQw4w9WgXcQ', download=False)
            print(f"[OK] Cookies working - Test video: {info.get('title', 'Unknown')}")
        except Exception as e:
            print(f"[ERROR] Cookie test failed: {e}")
            print("   Cookies may be expired. Run setup script to refresh them.")
    else:
        print("[ERROR] No authentication found")
        print("   Run this script to set up cookie authentication")

def main():
    if len(sys.argv) > 1 and sys.argv[1] == '--test':
        test_current_auth()
        return

    print("YouTube Cookie Authentication Setup")
    print("Since yt-dlp dropped OAuth2 support, cookies are now required for YouTube access.")
    print()

    print("Choose an option:")
    print("1. Extract cookies from browser (recommended)")
    print("2. Test current authentication")
    print("3. Exit")

    while True:
        try:
            choice = input("\nEnter choice (1-3): ").strip()
            if choice == '1':
                extract_browser_cookies()
                break
            elif choice == '2':
                test_current_auth()
                break
            elif choice == '3':
                print("Goodbye!")
                break
            else:
                print("Invalid choice. Please enter 1, 2, or 3.")
        except KeyboardInterrupt:
            print("\n\nGoodbye!")
            break

if __name__ == '__main__':
    main()
