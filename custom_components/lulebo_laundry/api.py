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

        # --- STRATEGY 1: Scrape the /CustomerBooking overview page for Unbook links ---
        # This is the most reliable source — it lists all your current bookings as anchor tags.
        overview_url = f"{self.base_url}/CustomerBooking"
        _LOGGER.warning(f"Lulebo API: Fetching active bookings from overview: {overview_url}")
        response = self.session.get(overview_url)
        soup = BeautifulSoup(response.text, 'html.parser')

        # Look for direct /CustomerBooking/Unbook/ anchor links (the cancel button on the overview page)
        unbook_links = soup.find_all('a', href=re.compile(r'/CustomerBooking/Unbook/\d+'))
        for link in unbook_links:
            href = link.get('href', '')
            # Try to find a date in the surrounding row text (format: YYYY-MM-DD)
            row_text = link.parent.parent.get_text(' ', strip=True)
            date_match = re.search(r'(\d{4}-\d{2}-\d{2})', row_text)
            if date_match:
                date_key = date_match.group(1)
                active_bookings[date_key] = f"https://lulebo.aptustotal.se{href}"
                _LOGGER.warning(f"Lulebo API: [Strategy 1] Found booking via Unbook link for {date_key}")

        if active_bookings:
            return active_bookings

        # --- STRATEGY 2: Scrape <script> tags for ConfirmCancelBooking calls ---
        # The calendar page embeds cancel URLs inside inline JS. We must use findall
        # (not search) so we catch ALL bookings, not just the first one.
        _LOGGER.warning("Lulebo API: No Unbook links found, trying script-tag strategy...")

        calendar_url = f"{self.base_url}/CustomerBooking/BookingCalendar?bookingGroupId={self.group_id}"
        cal_response = self.session.get(calendar_url)
        cal_soup = BeautifulSoup(cal_response.text, 'html.parser')

        all_scripts = soup.find_all('script') + cal_soup.find_all('script')

        for script in all_scripts:
            if not script.string:
                continue
            # BUG FIX: was re.search (finds only the FIRST match).
            # Must use re.findall to catch ALL bookings in one script block.
            matches = re.findall(r"ConfirmCancelBooking\([^,]+,\s*'([^']+)'", script.string)
            for unbook_path in matches:
                date_match = re.search(r"passDate=(\d{4}-\d{2}-\d{2})", unbook_path)
                if date_match:
                    date_key = date_match.group(1)
                    active_bookings[date_key] = f"https://lulebo.aptustotal.se{unbook_path}"
                    _LOGGER.warning(f"Lulebo API: [Strategy 2] Found cancellation link for {date_key}")

        # --- STRATEGY 3: Look for booked-slot CSS classes on the calendar grid ---
        # Aptus renders your own bookings with a distinct button class (e.g. 'myBookedButton'
        # or 'bookedByMeButton'). Log what we find so we can extend this if needed.
        booked_buttons = cal_soup.find_all('button', class_=re.compile(r'[Mm]y|[Bb]ooked[Bb]y[Mm]e|ownBook'))
        for btn in booked_buttons:
            onclick = btn.get('onclick', '')
            # These buttons typically call ConfirmCancelBooking or navigate to an unbook URL
            date_match = re.search(r"passDate=(\d{4}-\d{2}-\d{2})", onclick)
            path_match = re.search(r"'(/CustomerBooking[^']+)'", onclick)
            if date_match and path_match:
                date_key = date_match.group(1)
                if date_key not in active_bookings:
                    active_bookings[date_key] = f"https://lulebo.aptustotal.se{path_match.group(1)}"
                    _LOGGER.warning(f"Lulebo API: [Strategy 3] Found booking via booked-button class for {date_key}")

        if not active_bookings:
            _LOGGER.warning(
                "Lulebo API: get_active_bookings() returned empty. "
                "To debug, check the raw HTML of the calendar and overview pages in your HA logs "
                "by temporarily adding: _LOGGER.warning(cal_response.text[:3000])"
            )

        return active_bookings

    def cancel_time(self, target_date: str) -> bool:
        # BUG FIX: was self.authenticate() (missing underscore) — would crash with AttributeError
        if not self.session and not self._authenticate():
            return False

        _LOGGER.warning(f"Lulebo API: Attempting to cancel booking for {target_date}...")

        active_bookings = self.get_active_bookings()

        if target_date in active_bookings:
            unbook_url = active_bookings[target_date]
            _LOGGER.warning(f"Lulebo API: Found unbook URL! Cancelling: {unbook_url}")
            resp = self.session.get(unbook_url, allow_redirects=False)
            
            if resp.status_code in (200, 302):
                _LOGGER.warning("Lulebo API: Cancellation successful!")
                return True
            else:
                _LOGGER.error(f"Lulebo API: Cancellation failed with status code {resp.status_code}")
                return False
        else:
            _LOGGER.error(
                f"Lulebo API: No active booking found for {target_date}. "
                f"Known bookings: {list(active_bookings.keys())}"
            )
            return False

    def get_week_availability(self):
        if not self.session and not self._authenticate():
            return {}

        available_slots = {}
        from datetime import datetime, timedelta
        next_week = (datetime.now() + timedelta(days=7)).strftime("%Y-%m-%d")
        
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
