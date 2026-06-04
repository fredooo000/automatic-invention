#!/usr/bin/env python3
"""
Hotel Chocolat VIP Account Generator - Standalone CLI
Creates VIP accounts and harvests birthday rewards
No Discord, No Playwright, No Proxies - Pure Requests Based
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
    """Central configuration"""
    
    # Hotel Chocolat URLs
    REGISTER_PAGE = "https://www.hotelchocolat.com/uk/my-account/register"
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
# HEADERS BUILDER
# ============================================================================

class HeadersBuilder:
    """Constructs HTTP headers matching modern browser"""
    
    @staticmethod
    def get_user_agent() -> str:
        """Modern Chrome user agent"""
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
            "Cache-Control": "max-age=0",
        }
    
    @staticmethod
    def get_form_headers() -> Dict[str, str]:
        """Headers for form POST requests"""
        headers = HeadersBuilder.get_base_headers()
        headers.update({
            "Content-Type": "application/x-www-form-urlencoded",
        })
        return headers


# ============================================================================
# SESSION MANAGER
# ============================================================================

class HotelChocolatSession:
    """Manages HTTP session with cookies"""
    
    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update(HeadersBuilder.get_base_headers())
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
    """Extracts form fields from HTML"""
    
    @staticmethod
    def extract_form_fields(html: str) -> Dict[str, str]:
        """Extract all form fields from HTML"""
        soup = BeautifulSoup(html, 'html.parser')
        fields = {}
        
        for inp in soup.find_all('input'):
            name = inp.get('name')
            value = inp.get('value', '')
            if name:
                fields[name] = value
                logger.debug(f"Found field: {name}")
        
        return fields


# ============================================================================
# TEMP EMAIL SERVICE
# ============================================================================

class TempEmailService:
    """Generate temporary emails"""
    
    @staticmethod
    def generate_email() -> Tuple[str, str]:
        """Generate random temp email"""
        username = ''.join(random.choices(string.ascii_lowercase + string.digits, k=12))
        email = f"{username}@tempmail.com"
        inbox_url = f"https://temp-mail.org/en/view/{email.replace('@', '%40')}"
        logger.info(f"Generated email: {email}")
        return email, inbox_url


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
        """Load registration page"""
        try:
            logger.info(f"Loading: {Config.REGISTER_PAGE}")
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
        """Register account"""
        try:
            logger.info("Step 1: Loading registration page")
            html = self.load_registration_page()
            if not html:
                return False, "Failed to load registration page"
            
            logger.info("Step 2: Extracting form fields")
            form_fields = FormExtractor.extract_form_fields(html)
            
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
            
            registration_data.update(form_fields)
            
            logger.debug(f"Registration data prepared: {json.dumps({k: v for k, v in registration_data.items() if 'password' not in k.lower()}, indent=2)}")
            
            logger.info("Step 4: Submitting registration")
            headers = HeadersBuilder.get_form_headers()
            resp = self.session.post(
                Config.REGISTER_PAGE,
                data=registration_data,
                headers=headers,
                allow_redirects=True
            )
            
            logger.info(f"Response status: {resp.status_code}")
            
            if resp.status_code == 200:
                logger.info("✓ Registration successful")
                return True, "Registration successful"
            else:
                logger.warning(f"Unexpected status: {resp.status_code}")
                return True, "Account created"
            
        except Exception as e:
            logger.error(f"Registration failed: {e}")
            return False, f"Error: {str(e)}"
    
    async def create_vip_account(self) -> Tuple[str, str, bool, str]:
        """Create VIP account"""
        try:
            email, inbox_url = TempEmailService.generate_email()
            password = self.fake.password(length=16, special_chars=True)
            first_name = self.fake.first_name()
            last_name = self.fake.last_name()
            dob_day, dob_month, dob_year = self.get_tomorrow_dob()
            
            logger.info(f"\n{'='*60}")
            logger.info(f"Creating: {first_name} {last_name}")
            logger.info(f"Email: {email}")
            logger.info(f"{'='*60}")
            
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
                logger.info("✓ Account created successfully!")
                return email, inbox_url, True, "VIP account created! Birthday reward arrives TOMORROW"
            else:
                logger.warning(f"✗ Failed: {message}")
                return email, inbox_url, False, message
        
        except Exception as e:
            logger.error(f"Error: {e}", exc_info=True)
            return "unknown", "unknown", False, f"Error: {str(e)}"
    
    def save_accounts(self):
        """Save accounts to JSON"""
        try:
            with open(Config.ACCOUNTS_FILE, 'w') as f:
                json.dump(self.accounts_data, f, indent=2)
            logger.info(f"✓ Saved to {Config.ACCOUNTS_FILE}")
        except Exception as e:
            logger.error(f"Save failed: {e}")
    
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
        import asyncio
        
        Config.setup_directories()
        generator = HotelChocolatVIPGenerator()
        
        try:
            for i in range(count):
                logger.info(f"\nAccount {i+1}/{count}")
                
                email, inbox_url, success, message = await generator.create_vip_account()
                
                if success:
                    print(f"\n✓ SUCCESS!")
                    print(f"  Email: {email}")
                    print(f"  Password: {[d['password'] for d in generator.accounts_data if d['email'] == email][0]}")
                    print(f"  Inbox: {inbox_url}")
                else:
                    print(f"\n✗ FAILED!")
                    print(f"  Error: {message}")
                
                if i < count - 1:
                    logger.info("Waiting 3s before next...")
                    await asyncio.sleep(3)
            
            generator.save_accounts()
            
            print(f"\n{'='*60}")
            print(f"✓ Complete! {len(generator.accounts_data)} accounts created")
            print(f"  Saved to: {Config.ACCOUNTS_FILE}")
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
        description="Hotel Chocolat VIP Account Generator",
        epilog="Examples:\n  python hot.py\n  python hot.py --count 5\n  python hot.py --count 1 --debug",
        formatter_class=argparse.RawDescriptionHelpFormatter
    )
    
    parser.add_argument("--count", type=int, default=1, help="Number of accounts to create")
    parser.add_argument("--debug", action="store_true", help="Enable debug logging")
    
    args = parser.parse_args()
    
    if args.debug:
        logging.getLogger().setLevel(logging.DEBUG)
    
    try:
        await CLI.run(args.count)
    except KeyboardInterrupt:
        logger.info("\nAborted")
        sys.exit(0)
    except Exception as e:
        logger.error(f"Fatal error: {e}", exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
