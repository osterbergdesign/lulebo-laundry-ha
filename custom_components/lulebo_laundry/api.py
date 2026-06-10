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
        soup = BeautifulSoup(dashboard.text, 'html.parser')
        
        try:
            magic_link = soup.find('a', href=lambda href: href and "lulebo.aptustotal.se" in href)['href']
            self.session.get(magic_link, headers=headers)
            _LOGGER.info("Lulebo API: Successfully authenticated!")
            return True
        except (TypeError, IndexError):
            _LOGGER.error("Lulebo API: Could not find the Aptus link. Did the login fail?")
            self.session = None
            return False

    def check_availability(self, target_date: str):
        if not self.session and not self._authenticate():
            return None
            
        url = f"{self.base_url}/CustomerBooking/BookingCalendar?bookingGroupId={self.group_id}"
        response = self.session.get(url)
        
        # Check if session timed out and we got redirected
        if "Account/Login" in response.url:
            self.session = None
            if self._authenticate():
                response = self.session.get(url)
            else:
                return None
                
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
        
        # If we get a 302 to the login page instead of a successful booking redirect
        if response.status_code == 302 and "Account/Login" in response.headers.get('Location', ''):
            _LOGGER.warning("Lulebo API: Session timeout during booking. Re-authenticating...")
            self.session = None
            if self._authenticate():
                response = self.session.get(url, allow_redirects=False)
            else:
                return False
        
        if response.status_code == 302:
            return True
        else:
            _LOGGER.error(f"Lulebo API: Booking failed! Server returned status code: {response.status_code}")
            return False

    def get_active_bookings(self, retry=True):
        if not self.session and not self._authenticate():
            return {}
            
        active_bookings = {}
        overview_url = f"{self.base_url}/CustomerBooking"
        response = self.session.get(overview_url)
        
        if "Account/Login" in response.url or response.status_code != 200:
            if retry:
                _LOGGER.warning("Lulebo API: Session timeout detected. Re-authenticating...")
                self.session = None
                return self.get_active_bookings(retry=False)
            return {}

        soup = BeautifulSoup(response.text, 'html.parser')
        
        calendar_url = f"{self.base_url}/CustomerBooking/BookingCalendar?bookingGroupId={self.group_id}"
        cal_response = self.session.get(calendar_url)
        cal_soup = BeautifulSoup(cal_response.text, 'html.parser')
        
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
                        
        return active_bookings

    def cancel_time(self, target_date: str) -> bool:
        if not self.session and not self._authenticate():
            return False

        active_bookings = self.get_active_bookings()

        if target_date in active_bookings:
            unbook_url = active_bookings[target_date]
            resp = self.session.get(unbook_url, allow_redirects=False)
            
            if resp.status_code == 302 and "Account/Login" in resp.headers.get('Location', ''):
                _LOGGER.warning("Lulebo API: Session timeout during cancellation. Re-authenticating...")
                self.session = None
                if self._authenticate():
                    resp = self.session.get(unbook_url, allow_redirects=False)
                else:
                    return False
            
            if resp.status_code == 302 or resp.status_code == 200:
                return True
            else:
                _LOGGER.error(f"Lulebo API: Cancellation failed with status code {resp.status_code}")
                return False
        
        _LOGGER.error(f"Lulebo API: Failed to find an active booking for {target_date}.")
        return False
    
    def get_week_availability(self, retry=True):
        if not self.session and not self._authenticate():
            return None

        from datetime import datetime, timedelta
        next_week = (datetime.now() + timedelta(days=7)).strftime("%Y-%m-%d")
        
        pages_to_fetch = [
            f"{self.base_url}/CustomerBooking/BookingCalendar?bookingGroupId={self.group_id}",
            f"{self.base_url}/CustomerBooking/BookingCalendar?bookingGroupId={self.group_id}&passDate={next_week}"
        ]
        
        available_slots = {}
        
        for idx, url in enumerate(pages_to_fetch):
            response = self.session.get(url)
            
            # --- DETTA ÄR MAGIN SOM RÄDDAR TIMEOUTS ---
            if "Account/Login" in response.url or response.status_code != 200:
                if retry:
                    _LOGGER.warning("Lulebo API: Session timeout detected on kalender fetch! Reconnecting...")
                    self.session = None
                    return self.get_week_availability(retry=False)
                else:
                    _LOGGER.error("Lulebo API: Reconnection failed.")
                    return None
            # ------------------------------------------

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
        
        return available_slots
