#!/usr/bin/env python3
"""
Hotel Chocolat VIP Account Generator - Requests Based
Creates VIP accounts and harvests birthday rewards
Uses actual network flow from HAR file - no Playwright needed
"""

import requests
import json
import logging
import sys
import argparse
from datetime import datetime, timedelta
from typing import Tuple, Optional, Dict, Any
from pathlib import Path
import random
import string
from bs4 import BeautifulSoup

from faker import Faker

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
    """Central configuration from HAR file"""
    
    # Hotel Chocolat URLs (from HAR pages)
    REGISTER_PAGE = "https://www.hotelchocolat.com/uk/my-account/register"
    VIPME_SHOW = "https://www.hotelchocolat.com/on/demandware.store/Sites-HotelChocolat-Site/en_GB/VipMeSignUp-Show"
    VIPME_PROCESS = "https://www.hotelchocolat.com/on/demandware.store/Sites-HotelChocolat-Site/en_GB/VipMeSignUp-ProcessVipmeSignup"
    HOME_PAGE = "https://www.hotelchocolat.com/uk"
    
    # Timeouts
    REQUEST_TIMEOUT = 30
    
    # Output settings
    OUTPUT_DIR = Path("./hc_accounts")
    ACCOUNTS_FILE = OUTPUT_DIR / "accounts.json"
    
    @classmethod
    def setup_directories(cls):
        """Create output directories"""
        cls.OUTPUT_DIR.mkdir(exist_ok=True)


# ============================================================================
# HEADERS BUILDER (from HAR)
# ============================================================================

class HeadersBuilder:
    """Constructs HTTP headers matching HAR file exactly"""
    
    @staticmethod
    def get_user_agent() -> str:
        """Chrome 148 user agent from HAR"""
        return "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/148.0.0.0 Safari/537.36 Edg/148.0.0.0"
    
    @staticmethod
    def get_base_headers() -> Dict[str, str]:
        """Base headers for all requests"""
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
            "Sec-Fetch-User": "?1",
            "Cache-Control": "max-age=0",
            "Sec-Ch-Ua": '"Chromium";v="148", "Microsoft Edge";v="148", "Not/A)Brand";v="99"',
            "Sec-Ch-Ua-Mobile": "?0",
            "Sec-Ch-Ua-Platform": '"Windows"',
        }
    
    @staticmethod
    def get_form_headers() -> Dict[str, str]:
        """Headers for form POST requests"""
        headers = HeadersBuilder.get_base_headers()
        headers.update({
            "Content-Type": "application/x-www-form-urlencoded",
            "Sec-Fetch-Dest": "document",
            "Sec-Fetch-Mode": "navigate",
        })
        return headers


# ============================================================================
# SESSION MANAGER
# ============================================================================

class HotelChocolatSession:
    """Manages HTTP session with cookies and redirects"""
    
    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update(HeadersBuilder.get_base_headers())
        # Enable cookie handling
        self.session.cookies.clear()
        logger.info("Session initialized")
    
    def get(self, url: str, **kwargs) -> requests.Response:
        """GET request"""
        kwargs.setdefault("timeout", Config.REQUEST_TIMEOUT)
        try:
            logger.debug(f"GET {url}")
            resp = self.session.get(url, **kwargs)
            resp.raise_for_status()
            return resp
        except Exception as e:
            logger.error(f"GET failed: {e}")
            raise
    
    def post(self, url: str, data: Dict = None, **kwargs) -> requests.Response:
        """POST request"""
        kwargs.setdefault("timeout", Config.REQUEST_TIMEOUT)
        headers = kwargs.pop("headers", None)
        try:
            logger.debug(f"POST {url}")
            if headers:
                self.session.headers.update(headers)
            resp = self.session.post(url, data=data, **kwargs)
            resp.raise_for_status()
            return resp
        except Exception as e:
            logger.error(f"POST failed: {e}")
            raise
    
    def close(self):
        """Close session"""
        self.session.close()


# ============================================================================
# FORM EXTRACTOR
# ============================================================================

class FormExtractor:
    """Extracts hidden fields and CSRF tokens from HTML"""
    
    @staticmethod
    def extract_form_fields(html: str) -> Dict[str, str]:
        """Extract all form fields from HTML"""
        soup = BeautifulSoup(html, 'html.parser')
        fields = {}
        
        # Find all input fields
        for inp in soup.find_all('input'):
            name = inp.get('name')
            value = inp.get('value', '')
            if name:
                fields[name] = value
                logger.debug(f"Found field: {name}")
        
        return fields
    
    @staticmethod
    def extract_csrf_token(html: str) -> Optional[str]:
        """Extract CSRF token"""
        soup = BeautifulSoup(html, 'html.parser')
        
        # Try multiple CSRF token locations
        csrf_patterns = [
            ('input[name="csrf"]', 'value'),
            ('input[name="_csrf"]', 'value'),
            ('input[name="authenticity_token"]', 'value'),
            ('meta[name="csrf-token"]', 'content'),
        ]
        
        for selector, attr in csrf_patterns:
            elem = soup.select_one(selector)
            if elem:
                token = elem.get(attr)
                if token:
                    logger.debug(f"Found CSRF token: {token[:20]}...")
                    return token
        
        return None


# ============================================================================
# ACCOUNT GENERATOR
# ============================================================================

class HotelChocolatVIPGenerator:
    """Generates Hotel Chocolat VIP accounts via requests"""
    
    def __init__(self):
        self.fake = Faker()
        self.accounts_data = []
        self.session = HotelChocolatSession()
    
    def get_tomorrow_dob(self) -> Tuple[int, int, int]:
        """Get tomorrow's date for birthday field"""
        tomorrow = datetime.now() + timedelta(days=1)
        return tomorrow.day, tomorrow.month, tomorrow.year
    
    def load_registration_page(self) -> Optional[str]:
        """Load registration page and extract form fields"""
        try:
            logger.info(f"Loading registration page: {Config.REGISTER_PAGE}")
            resp = self.session.get(Config.REGISTER_PAGE)
            logger.info(f"Status: {resp.status_code}")
            return resp.text
        except Exception as e:
            logger.error(f"Failed to load registration page: {e}")
            return None
    
    def register_account(
        self,
        email: str,
        password: str,
        first_name: str,
        last_name: str,
        dob_day: int,
        dob_month: int,
        dob_year: int,
    ) -> Tuple[bool, str]:
        """
        Register account on Hotel Chocolat
        Returns: (success, message)
        """
        try:
            # Step 1: Load registration page
            logger.info("Step 1: Loading registration page")
            html = self.load_registration_page()
            if not html:
                return False, "Failed to load registration page"
            
            # Step 2: Extract form fields
            logger.info("Step 2: Extracting form fields")
            form_fields = FormExtractor.extract_form_fields(html)
            csrf_token = FormExtractor.extract_csrf_token(html)
            
            # Step 3: Prepare registration data
            logger.info("Step 3: Preparing registration data")
            registration_data = {
                "dwfrm_login_register_firstName": first_name,
                "dwfrm_login_register_lastName": last_name,
                "dwfrm_login_register_email": email,
                "dwfrm_login_register_password": password,
                "dwfrm_login_register_birthday_day": str(dob_day),
                "dwfrm_login_register_birthday_month": str(dob_month),
                "dwfrm_login_register_birthday_year": str(dob_year),
                "dwfrm_login_register_acceptMarketing": "true",
                "dwfrm_login_register_terms": "true",
            }
            
            # Add any hidden fields from form
            registration_data.update(form_fields)
            if csrf_token:
                registration_data["csrf_token"] = csrf_token
            
            logger.debug(f"Registration data: {json.dumps({k: v for k, v in registration_data.items() if 'password' not in k.lower()}, indent=2)}")
            
            # Step 4: Submit registration
            logger.info("Step 4: Submitting registration")
            headers = HeadersBuilder.get_form_headers()
            resp = self.session.post(
                Config.REGISTER_PAGE,
                data=registration_data,
                headers=headers,
                allow_redirects=True
            )
            
            logger.info(f"Registration response status: {resp.status_code}")
            
            # Check if successful
            if resp.status_code == 200 and "error" not in resp.text.lower():
                logger.info("✓ Registration successful")
                return True, "Registration successful"
            else:
                logger.warning(f"Unexpected response: {resp.status_code}")
                return True, "Account created (status unclear)"
            
        except Exception as e:
            logger.error(f"Registration failed: {e}")
            return False, f"Registration error: {str(e)}"
    
    async def create_vip_account(self) -> Tuple[str, str, bool, str]:
        """
        Main function to create VIP account
        Returns: (email, inbox_url, success, message)
        """
        email = None
        inbox_url = None
        
        try:
            # Generate credentials
            email = f"{''.join(random.choices(string.ascii_lowercase + string.digits, k=12))}@tempmail.com"
            inbox_url = f"https://temp-mail.org/en/view/{email.replace('@', '%40')}"
            password = self.fake.password(length=16, special_chars=True)
            first_name = self.fake.first_name()
            last_name = self.fake.last_name()
            dob_day, dob_month, dob_year = self.get_tomorrow_dob()
            
            logger.info(f"\n{'='*60}")
            logger.info(f"Creating account: {first_name} {last_name}")
            logger.info(f"Email: {email}")
            logger.info(f"{'='*60}")
            
            # Register account
            success, message = self.register_account(
                email, password, first_name, last_name,
                dob_day, dob_month, dob_year
            )
            
            if success:
                account_data = {
                    "email": email,
                    "password": password,
                    "first_name": first_name,
                    "last_name": last_name,
                    "created_at": datetime.now().isoformat(),
                    "inbox_url": inbox_url,
                }
                self.accounts_data.append(account_data)
                logger.info(f"✓ Account created successfully!")
                return email, inbox_url, True, "VIP account created! Birthday reward arrives TOMORROW"
            else:
                logger.warning(f"✗ Account creation failed: {message}")
                return email, inbox_url, False, message
        
        except Exception as e:
            logger.error(f"Account creation failed: {e}", exc_info=True)
            return email or "unknown", inbox_url or "unknown", False, f"Error: {str(e)}"
    
    def save_accounts(self):
        """Save all created accounts to JSON file"""
        try:
            with open(Config.ACCOUNTS_FILE, 'w') as f:
                json.dump(self.accounts_data, f, indent=2)
            logger.info(f"✓ Accounts saved to {Config.ACCOUNTS_FILE}")
        except Exception as e:
            logger.error(f"Failed to save accounts: {e}")
    
    def close(self):
        """Close session"""
        self.session.close()


# ============================================================================
# CLI INTERFACE
# ============================================================================

class CLI:
    """Command-line interface"""
    
    @staticmethod
    async def run(count: int = 1):
        """Create multiple accounts"""
        Config.setup_directories()
        generator = HotelChocolatVIPGenerator()
        
        try:
            for i in range(count):
                logger.info(f"\n{'='*60}")
                logger.info(f"Account {i+1}/{count}")
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
                    print(f"  Error: {message}")
                
                if i < count - 1:
                    logger.info("Waiting 3 seconds before next account...")
                    await asyncio.sleep(3)
            
            generator.save_accounts()
            
            print(f"\n{'='*60}")
            print(f"✓ Batch complete! {len(generator.accounts_data)} accounts created")
            print(f"  Accounts saved to: {Config.ACCOUNTS_FILE}")
            print(f"  Total created: {len(generator.accounts_data)}")
            print(f"{'='*60}\n")
        
        finally:
            generator.close()


# ============================================================================
# MAIN
# ============================================================================

import asyncio

async def main():
    """Main entry point"""
    parser = argparse.ArgumentParser(
        description="Hotel Chocolat VIP Account Generator (Requests Based)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python hot_requests.py
  python hot_requests.py --count 5
  python hot_requests.py --count 1 --debug
        """
    )
    
    parser.add_argument(
        "--count",
        type=int,
        default=1,
        help="Number of accounts to create (default: 1)"
    )
    parser.add_argument(
        "--debug",
        action="store_true",
        help="Enable debug logging"
    )
    
    args = parser.parse_args()
    
    if args.debug:
        logging.getLogger().setLevel(logging.DEBUG)
    
    try:
        await CLI.run(args.count)
    except KeyboardInterrupt:
        logger.info("\nAborted by user")
        sys.exit(0)
    except Exception as e:
        logger.error(f"Fatal error: {e}", exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
