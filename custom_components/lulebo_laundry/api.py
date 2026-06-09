import requests
import re
import logging
import time
from bs4 import BeautifulSoup

_LOGGER = logging.getLogger(__name__)

class LuleboLaundryAPI:
    def __init__(self, username, password, booking_group_id="YOUR BOOKING ID", contract_id="YOUR CONTACT ID"):
        self.username = username
        self.password = password
        self.group_id = booking_group_id
        self.contract_id = contract_id
        self.base_url = "https://lulebo.aptustotal.se/AptusPortal"
        self.session = None

    def _authenticate(self):
        self.session = requests.Session()
        headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
        login_payload = {"UserId": self.username, "Password": self.password, "RememberMe": "true"}
        
        _LOGGER.warning(f"Lulebo API: Attempting login for user: {self.username}")
        
        self.session.get("https://www.lulebo.se/Account/Login", headers=headers)
        self.session.post("https://www.lulebo.se/Account/Login", headers=headers, data=login_payload)
        
        # We bypass the dashboard entirely and hit the secret backend URL
        timestamp = int(time.time() * 1000)
        links_url = f"https://www.lulebo.se/Account/EngagementLoadLinks?usergrouptype=Residents&contractid={self.contract_id}&_={timestamp}"
        
        dashboard = self.session.get(links_url, headers=headers)
        _LOGGER.warning(f"Lulebo API: Fetched background links from URL: {dashboard.url}")
        
        soup = BeautifulSoup(dashboard.text, 'html.parser')
        
        try:
            magic_link = soup.find('a', href=lambda href: href and "lulebo.aptustotal.se" in href)['href']
            _LOGGER.warning("Lulebo API: Found magic link! Jumping to Aptus...")
            self.session.get(magic_link, headers=headers)
            return True
        except (TypeError, IndexError):
            _LOGGER.error("Lulebo API: Could not find the Aptus link. Did the login fail? Check credentials.")
            return False

    def check_availability(self, target_date: str):
        if not self.session and not self._authenticate():
            return None
            
        url = f"{self.base_url}/CustomerBooking/BookingCalendar?bookingGroupId={self.group_id}"
        response = self.session.get(url)
        soup = BeautifulSoup(response.text, 'html.parser')
        
        availability = {"0": "Booked", "1": "Booked", "2": "Booked", "3": "Booked"}
        
        buttons = soup.find_all('button', class_='bookButton')
        for btn in buttons:
            onclick = btn.get('onclick', '')
            match = re.search(r'passNo=(\d+)&passDate=([^&\']+)', onclick)
            if match:
                slot_no = match.group(1)
                slot_date = match.group(2)
                if slot_date == target_date:
                    availability[slot_no] = "Available"
                    
        return availability

    def book_time(self, target_date: str, time_slot: str) -> bool:
        if not self.session and not self._authenticate():
            return False
            
        url = f"{self.base_url}/CustomerBooking/Book?passNo={time_slot}&passDate={target_date}&bookingGroupId={self.group_id}"
        response = self.session.get(url, allow_redirects=False)
        
        if response.status_code == 302:
            return True
        else:
            _LOGGER.error(f"Lulebo API: Booking failed! Server returned status code: {response.status_code}")
            return False

    def get_active_bookings(self):
        if not self.session and not self._authenticate():
            return {}
            
        active_bookings = {}
        
        # 1. Search the main "BOKA" overview page
        overview_url = f"{self.base_url}/CustomerBooking"
        _LOGGER.warning(f"Lulebo API: Searching for active bookings on {overview_url}")
        response = self.session.get(overview_url)
        soup = BeautifulSoup(response.text, 'html.parser')
        
        # 2. Search the specific calendar grid page
        calendar_url = f"{self.base_url}/CustomerBooking/BookingCalendar?bookingGroupId={self.group_id}"
        _LOGGER.warning(f"Lulebo API: Searching for active bookings on {calendar_url}")
        cal_response = self.session.get(calendar_url)
        cal_soup = BeautifulSoup(cal_response.text, 'html.parser')
        
        # Combine all <script> blocks from both pages
        all_scripts = soup.find_all('script') + cal_soup.find_all('script')
        
        for script in all_scripts:
            if script.string and 'ConfirmCancelBooking' in script.string:
                match = re.search(r"ConfirmCancelBooking\([^,]+,\s*'([^']+)'", script.string)
                if match:
                    unbook_path = match.group(1)
                    date_match = re.search(r"passDate=(\d{4}-\d{2}-\d{2})", unbook_path)
                    if date_match:
                        date_key = date_match.group(1)
                        active_bookings[date_key] = f"https://lulebo.aptustotal.se{unbook_path}"
                        _LOGGER.warning(f"Lulebo API: Found cancellation link for {date_key}!")
                        
        return active_bookings

    def cancel_time(self, target_date: str) -> bool:
        if not self.session and not self.authenticate():
            return False

        _LOGGER.warning(f"Lulebo API: Attempting to cancel booking for {target_date}...")

        # 1. Hämta listan med aktiva bokningar som vi REDAN VET fungerar!
        active_bookings = self.get_active_bookings()

        # 2. Kolla om datumet finns i vår lista
        if target_date in active_bookings:
            unbook_url = active_bookings[target_date]
            _LOGGER.warning(f"Lulebo API: Found unbook URL directly! Cancelling: {unbook_url}")
            
            # 3. Skicka avbokningssignalen (vi tillåter inte redirects eftersom Aptus brukar svara med 302 vid success)
            resp = self.session.get(unbook_url, allow_redirects=False)
            
            if resp.status_code == 302 or resp.status_code == 200:
                _LOGGER.warning("Lulebo API: Cancellation successful!")
                return True
            else:
                _LOGGER.error(f"Lulebo API: Cancellation failed with status code {resp.status_code}")
                return False
        else:
            _LOGGER.error(f"Lulebo API: Failed to find an active booking for {target_date}. It might already be cancelled!")
            return False

        # --- STRATEGY 2: Fallback to scraping the overview page ---
        # If Strategy 1 fails, we look at the main list and match the date using Swedish text
        overview_url = f"{self.base_url}/CustomerBooking"
        response = self.session.get(overview_url)
        soup = BeautifulSoup(response.text, 'html.parser')
        
        # Convert YYYY-MM-DD to Swedish text (e.g., 2026-06-09 -> "9 juni")
        months = ["", "januari", "februari", "mars", "april", "maj", "juni", "juli", "augusti", "september", "oktober", "november", "december"]
        try:
            y, m, d = target_date.split("-")
            swe_date = f"{int(d)} {months[int(m)]}"
        except Exception:
            swe_date = target_date # Fallback if formatting fails
            
        unbook_links = soup.find_all('a', href=re.compile(r'/CustomerBooking/Unbook/\d+'))
        for link in unbook_links:
            parent_text = link.parent.parent.text.lower()
            if target_date in parent_text or swe_date in parent_text:
                unbook_url = f"https://lulebo.aptustotal.se{link.get('href')}"
                _LOGGER.warning(f"Lulebo API: Found ID via Overview! Cancelling: {unbook_url}")
                resp = self.session.get(unbook_url, allow_redirects=False)
                return resp.status_code == 302

        _LOGGER.error(f"Lulebo API: Failed to find an active booking for {target_date}. It might already be cancelled!")
        return False
    
    def get_week_availability(self):
        if not self.session and not self._authenticate():
            return {}

        available_slots = {}
        # Calculate next week's date to fetch the 2nd page
        from datetime import datetime, timedelta
        next_week = (datetime.now() + timedelta(days=7)).strftime("%Y-%m-%d")
        
        # We will fetch two pages: Default (Current Week) and Next Week
        pages_to_fetch = [
            f"{self.base_url}/CustomerBooking/BookingCalendar?bookingGroupId={self.group_id}",
            f"{self.base_url}/CustomerBooking/BookingCalendar?bookingGroupId={self.group_id}&passDate={next_week}"
        ]
        
        for url in pages_to_fetch:
            response = self.session.get(url)
            soup = BeautifulSoup(response.text, 'html.parser')
            buttons = soup.find_all('button', class_='bookButton')
            
            for btn in buttons:
                onclick = btn.get('onclick', '')
                match = re.search(r'passNo=(\d+)&passDate=([^&\']+)', onclick)
                if match:
                    slot_no = match.group(1)
                    slot_date = match.group(2)
                    
                    if slot_date not in available_slots:
                        available_slots[slot_date] = []
                    available_slots[slot_date].append(slot_no)
        
        _LOGGER.warning(f"Lulebo API: Found {len(available_slots)} days with available slots.")
        return available_slots