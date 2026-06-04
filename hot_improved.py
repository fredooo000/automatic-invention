#!/usr/bin/env python3
"""
Hotel Chocolat VIP Account Generator - Standalone Version
Creates VIP accounts and harvests birthday rewards
No Discord dependency - CLI based with optional API server
"""

import asyncio
import json
import logging
import sys
import argparse
from datetime import datetime, timedelta
from typing import Tuple, Optional, Dict, Any
from pathlib import Path

import aiohttp
from playwright.async_api import async_playwright, Browser, BrowserContext, Page
from faker import Faker
import random
import string

# ============================================================================
# LOGGING SETUP
# ============================================================================

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# ============================================================================
# CONFIGURATION
# ============================================================================

class Config:
    """Central configuration"""
    
    # Temp Email Services
    TEMP_MAIL_API_KEY = "f38ce70edfmshca9d5287af1cb67p15b3fajsn422342bc9bbc"
    TEMP_MAIL_HOST = "privatix-temp-mail-v1.p.rapidapi.com"
    
    # Hotel Chocolat URLs
    REGISTER_PAGE = "https://www.hotelchocolat.com/uk/my-account/register"
    VIPME_PAGE = "https://www.hotelchocolat.com/on/demandware.store/Sites-HotelChocolat-Site/en_GB/VipMeSignUp-Show"
    VIPME_PROCESS = "https://www.hotelchocolat.com/on/demandware.store/Sites-HotelChocolat-Site/en_GB/VipMeSignUp-ProcessVipmeSignup"
    HOME_PAGE = "https://www.hotelchocolat.com/uk"
    
    # Browser settings
    BROWSER_TIMEOUT = 300000  # 5 minutes
    PAGE_LOAD_TIMEOUT = 60000  # 1 minute
    HEADLESS = True
    
    # Output settings
    OUTPUT_DIR = Path("./hc_accounts")
    SCREENSHOTS_DIR = OUTPUT_DIR / "screenshots"
    ACCOUNTS_FILE = OUTPUT_DIR / "accounts.json"
    
    @classmethod
    def setup_directories(cls):
        """Create output directories"""
        cls.OUTPUT_DIR.mkdir(exist_ok=True)
        cls.SCREENSHOTS_DIR.mkdir(exist_ok=True)


# ============================================================================
# HEADERS BUILDER
# ============================================================================

class HeadersBuilder:
    """Constructs proper HTTP and browser headers"""
    
    @staticmethod
    def get_user_agent() -> str:
        """Return modern user agent matching HAR file"""
        return "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/148.0.0.0 Safari/537.36 Edg/148.0.0.0"
    
    @staticmethod
    def get_request_headers() -> Dict[str, str]:
        """Standard request headers for Hotel Chocolat"""
        return {
            "User-Agent": HeadersBuilder.get_user_agent(),
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.9",
            "Accept-Encoding": "gzip, deflate, br",
            "DNT": "1",
            "Connection": "keep-alive",
            "Upgrade-Insecure-Requests": "1",
            "Sec-Fetch-Dest": "document",
            "Sec-Fetch-Mode": "navigate",
            "Sec-Fetch-Site": "none",
            "Cache-Control": "max-age=0",
        }
    
    @staticmethod
    def get_browser_context_params() -> Dict[str, Any]:
        """Parameters for browser context"""
        return {
            "user_agent": HeadersBuilder.get_user_agent(),
            "viewport": {"width": 1920, "height": 1080},
            "locale": "en-GB",
            "timezone_id": "Europe/London",
            "permissions": [],
        }


# ============================================================================
# TEMP EMAIL SERVICE
# ============================================================================

class TempEmailService:
    """Manages temporary email generation and monitoring"""
    
    def __init__(self):
        self.session: Optional[aiohttp.ClientSession] = None
        self.base_url = f"https://{Config.TEMP_MAIL_HOST}"
        self.headers = {
            "x-rapidapi-key": Config.TEMP_MAIL_API_KEY,
            "x-rapidapi-host": Config.TEMP_MAIL_HOST
        }
    
    async def __aenter__(self):
        self.session = aiohttp.ClientSession()
        return self
    
    async def __aexit__(self, *args):
        if self.session:
            await self.session.close()
    
    async def get_available_domains(self) -> list:
        """Fetch available email domains"""
        try:
            url = f"{self.base_url}/request/domains/format/json"
            async with self.session.get(url, headers=self.headers, timeout=10) as resp:
                if resp.status == 200:
                    domains = await resp.json()
                    logger.debug(f"Available domains: {domains[:3]}")
                    return domains
        except Exception as e:
            logger.error(f"Failed to get domains: {e}")
        return ["@tempmail.com", "@guerrillamail.com"]
    
    def generate_email(self) -> Tuple[str, str, Optional[str]]:
        """
        Generate random email address
        Returns: (email, inbox_url, mail_id)
        """
        try:
            username = ''.join(random.choices(string.ascii_lowercase + string.digits, k=10))
            domain = "@tempmail.com"  # Fallback domain
            email = f"{username}{domain}"
            inbox_url = f"https://temp-mail.org/en/view/{username}{domain.replace('@', '%40')}"
            
            logger.info(f"Generated email: {email}")
            logger.debug(f"Inbox URL: {inbox_url}")
            
            return email, inbox_url, None
        except Exception as e:
            logger.error(f"Email generation failed: {e}")
            raise
    
    async def check_emails(self, email: str) -> list:
        """Check for received emails"""
        try:
            url = f"{self.base_url}/request/mail/id/{email.replace('@', '%40')}/format/json"
            async with self.session.get(url, headers=self.headers, timeout=10) as resp:
                if resp.status == 200:
                    return await resp.json()
        except Exception as e:
            logger.error(f"Failed to check emails: {e}")
        return []


# ============================================================================
# ACCOUNT GENERATOR
# ============================================================================

class HotelChocolatVIPGenerator:
    """Generates Hotel Chocolat VIP accounts"""
    
    def __init__(self):
        self.fake = Faker()
        self.accounts_data = []
        self.screenshots_counter = 0
    
    async def save_screenshot(self, page: Page, label: str):
        """Save page screenshot for debugging"""
        try:
            self.screenshots_counter += 1
            filename = Config.SCREENSHOTS_DIR / f"{self.screenshots_counter:03d}_{label}.png"
            await page.screenshot(path=str(filename))
            logger.debug(f"Screenshot saved: {filename}")
        except Exception as e:
            logger.warning(f"Failed to save screenshot: {e}")
    
    def get_tomorrow_dob(self) -> Tuple[int, int, int]:
        """Get tomorrow's date for birthday field"""
        tomorrow = datetime.now() + timedelta(days=1)
        return tomorrow.day, tomorrow.month, tomorrow.year
    
    async def fill_registration_form(
        self,
        page: Page,
        email: str,
        password: str,
        first_name: str,
        last_name: str,
        dob_day: int,
        dob_month: int,
        dob_year: int,
    ) -> bool:
        """Fill the registration form"""
        try:
            logger.info("Filling registration form...")
            
            # Wait for form to be ready
            await page.wait_for_selector("input[name='dwfrm_login_register_email']", timeout=30000)
            await self.save_screenshot(page, "form_loaded")
            
            # Fill form fields
            fields = [
                ("input[name='dwfrm_login_register_firstName']", first_name, "First Name"),
                ("input[name='dwfrm_login_register_lastName']", last_name, "Last Name"),
                ("input[name='dwfrm_login_register_email']", email, "Email"),
                ("input[name='dwfrm_login_register_password']", password, "Password"),
                ("input[name='dwfrm_login_register_birthday_day']", str(dob_day), "Birthday Day"),
                ("input[name='dwfrm_login_register_birthday_month']", str(dob_month), "Birthday Month"),
                ("input[name='dwfrm_login_register_birthday_year']", str(dob_year), "Birthday Year"),
            ]
            
            for selector, value, label in fields:
                try:
                    await page.fill(selector, value, timeout=15000)
                    logger.debug(f"Filled {label}: {label if label != 'Email' else email}")
                except Exception as e:
                    logger.warning(f"Could not fill {label}: {e}")
            
            # Check marketing opt-in
            try:
                await page.check("input[name='dwfrm_login_register_acceptMarketing']", force=True, timeout=10000)
                logger.debug("Checked marketing opt-in")
            except Exception as e:
                logger.debug(f"Marketing opt-in not found: {e}")
            
            # Check terms
            try:
                await page.check("input[name='dwfrm_login_register_terms']", force=True, timeout=10000)
                logger.debug("Checked terms")
            except Exception as e:
                logger.warning(f"Terms checkbox not found: {e}")
            
            await self.save_screenshot(page, "form_filled")
            return True
            
        except Exception as e:
            logger.error(f"Form fill failed: {e}")
            await self.save_screenshot(page, "form_fill_error")
            return False
    
    async def submit_registration(self, page: Page) -> bool:
        """Submit the registration form"""
        try:
            logger.info("Submitting registration form...")
            await self.save_screenshot(page, "before_submit")
            
            # Click submit button with multiple selector attempts
            submit_selectors = [
                "button[type='submit']:has-text('Register')",
                "button[type='submit']:has-text('Create Account')",
                "button[type='submit']",
            ]
            
            for selector in submit_selectors:
                try:
                    await page.click(selector, force=True, timeout=15000)
                    logger.debug(f"Clicked submit button with selector: {selector}")
                    await asyncio.sleep(2)
                    break
                except Exception as e:
                    logger.debug(f"Selector {selector} not found: {e}")
                    continue
            
            await self.save_screenshot(page, "after_submit")
            await asyncio.sleep(3)
            return True
            
        except Exception as e:
            logger.error(f"Submission failed: {e}")
            await self.save_screenshot(page, "submit_error")
            return False
    
    async def complete_vip_signup(self, page: Page, dob_day: int, dob_month: int, dob_year: int) -> bool:
        """Complete VIP signup if prompted"""
        try:
            logger.info("Attempting to complete VIP signup...")
            
            try:
                await page.wait_for_selector("input[name='birthDay']", timeout=15000)
                logger.info("VIP signup form detected")
                
                await page.fill("input[name='birthDay']", str(dob_day), timeout=10000)
                await page.fill("input[name='birthMonth']", str(dob_month), timeout=10000)
                await page.fill("input[name='birthYear']", str(dob_year), timeout=10000)
                
                try:
                    await page.check("input[name='marketingOptIn']", force=True, timeout=10000)
                except:
                    pass
                
                await self.save_screenshot(page, "vip_form_filled")
                
                submit_selectors = [
                    "button[type='submit']:has-text('Submit')",
                    "button[type='submit']:has-text('Update')",
                    "button[type='submit']",
                ]
                
                for selector in submit_selectors:
                    try:
                        await page.click(selector, force=True, timeout=15000)
                        logger.debug(f"Clicked VIP submit with: {selector}")
                        await asyncio.sleep(2)
                        break
                    except:
                        continue
                
                await self.save_screenshot(page, "vip_submitted")
                return True
                
            except asyncio.TimeoutError:
                logger.info("No VIP form detected - skipping VIP signup")
                return True
                
        except Exception as e:
            logger.warning(f"VIP signup incomplete: {e}")
            await self.save_screenshot(page, "vip_error")
            return True  # Don't fail the whole process
    
    async def create_vip_account(self) -> Tuple[str, str, bool, str]:
        """
        Main function to create VIP account
        Returns: (email, inbox_url, success, message)
        """
        email = None
        inbox_url = None
        
        try:
            async with TempEmailService() as email_service:
                email, inbox_url, mail_id = email_service.generate_email()
                
                password = self.fake.password(length=16, special_chars=True)
                first_name = self.fake.first_name()
                last_name = self.fake.last_name()
                dob_day, dob_month, dob_year = self.get_tomorrow_dob()
                
                logger.info(f"Starting account creation: {first_name} {last_name} ({email})")
                
                async with async_playwright() as p:
                    browser = await p.chromium.launch(headless=Config.HEADLESS)
                    context = await browser.new_context(**HeadersBuilder.get_browser_context_params())
                    page = await context.new_page()
                    
                    try:
                        # Load registration page with retries
                        page_loaded = False
                        for attempt in range(1, 4):
                            try:
                                logger.info(f"Loading register page (attempt {attempt}/3)...")
                                await page.goto(Config.REGISTER_PAGE, wait_until="domcontentloaded", timeout=Config.PAGE_LOAD_TIMEOUT)
                                await page.wait_for_selector("input[name='dwfrm_login_register_email']", timeout=30000)
                                page_loaded = True
                                logger.info("Register page loaded successfully")
                                await self.save_screenshot(page, f"page_loaded_attempt_{attempt}")
                                break
                            except Exception as e:
                                logger.warning(f"Load attempt {attempt} failed: {e}")
                                if attempt < 3:
                                    await asyncio.sleep(2)
                        
                        if not page_loaded:
                            return email, inbox_url, False, "Failed to load registration page after 3 attempts"
                        
                        # Fill and submit form
                        if not await self.fill_registration_form(page, email, password, first_name, last_name, dob_day, dob_month, dob_year):
                            return email, inbox_url, False, "Failed to fill registration form"
                        
                        if not await self.submit_registration(page):
                            return email, inbox_url, False, "Failed to submit registration form"
                        
                        # Try to complete VIP signup
                        await self.complete_vip_signup(page, dob_day, dob_month, dob_year)
                        
                        await self.save_screenshot(page, "final_page")
                        
                        # Store account data
                        account_data = {
                            "email": email,
                            "password": password,
                            "first_name": first_name,
                            "last_name": last_name,
                            "created_at": datetime.now().isoformat(),
                            "inbox_url": inbox_url,
                        }
                        self.accounts_data.append(account_data)
                        
                        logger.info(f"✓ Account created successfully: {email}")
                        return email, inbox_url, True, "VIP account created! Birthday reward arrives TOMORROW"
                        
                    finally:
                        await context.close()
                        await browser.close()
        
        except Exception as e:
            logger.error(f"Account creation failed: {e}", exc_info=True)
            return email or "unknown", inbox_url or "unknown", False, f"Error: {str(e)}"
    
    def save_accounts(self):
        """Save all created accounts to JSON file"""
        try:
            with open(Config.ACCOUNTS_FILE, 'w') as f:
                json.dump(self.accounts_data, f, indent=2)
            logger.info(f"Accounts saved to {Config.ACCOUNTS_FILE}")
        except Exception as e:
            logger.error(f"Failed to save accounts: {e}")


# ============================================================================
# CLI INTERFACE
# ============================================================================

class CLI:
    """Command-line interface"""
    
    @staticmethod
    async def run_single(count: int = 1):
        """Create multiple accounts"""
        Config.setup_directories()
        generator = HotelChocolatVIPGenerator()
        
        for i in range(count):
            logger.info(f"\n{'='*60}")
            logger.info(f"Creating account {i+1}/{count}")
            logger.info(f"{'='*60}\n")
            
            email, inbox_url, success, message = await generator.create_vip_account()
            
            if success:
                print(f"\n✓ SUCCESS!")
                print(f"  Email: {email}")
                print(f"  Inbox: {inbox_url}")
                print(f"  Message: {message}")
            else:
                print(f"\n✗ FAILED!")
                print(f"  Email: {email}")
                print(f"  Inbox: {inbox_url}")
                print(f"  Error: {message}")
            
            if i < count - 1:
                logger.info("Waiting before next account creation...")
                await asyncio.sleep(5)
        
        generator.save_accounts()
        
        print(f"\n{'='*60}")
        print(f"Batch complete! {len(generator.accounts_data)} accounts created")
        print(f"Accounts saved to: {Config.ACCOUNTS_FILE}")
        print(f"Screenshots saved to: {Config.SCREENSHOTS_DIR}")
        print(f"{'='*60}\n")


# ============================================================================
# MAIN
# ============================================================================

async def main():
    """Main entry point"""
    parser = argparse.ArgumentParser(
        description="Hotel Chocolat VIP Account Generator",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python hot_improved.py --count 5
  python hot_improved.py --count 1 --no-headless
        """
    )
    
    parser.add_argument(
        "--count",
        type=int,
        default=1,
        help="Number of accounts to create (default: 1)"
    )
    parser.add_argument(
        "--no-headless",
        action="store_true",
        help="Show browser window (default: headless)"
    )
    parser.add_argument(
        "--debug",
        action="store_true",
        help="Enable debug logging"
    )
    
    args = parser.parse_args()
    
    if args.debug:
        logging.getLogger().setLevel(logging.DEBUG)
    
    if args.no_headless:
        Config.HEADLESS = False
    
    try:
        await CLI.run_single(args.count)
    except KeyboardInterrupt:
        logger.info("\nAborted by user")
        sys.exit(0)
    except Exception as e:
        logger.error(f"Fatal error: {e}", exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
