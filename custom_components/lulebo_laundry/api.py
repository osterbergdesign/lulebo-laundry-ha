"""HTTP client for the Lulebo (Aptus) laundry booking portal.

Key robustness features:
  * Every request has a timeout (no more hung executor threads).
  * Sessions are re-authenticated automatically when they expire, instead of
    silently returning empty data.
  * Fetch failures return ``None`` so the sensor can keep the last good data,
    while a genuinely empty result returns ``{}``.
  * No personally identifiable information is written to the log.
"""

import logging
import re
import time
from datetime import datetime, timedelta

import requests
from bs4 import BeautifulSoup

from .const import REQUEST_TIMEOUT

_LOGGER = logging.getLogger(__name__)

_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36"
    )
}


class LuleboAuthError(Exception):
    """Raised when we cannot establish an authenticated session."""


class LuleboLaundryAPI:
    def __init__(self, username, password, booking_group_id="", contract_id=""):
        self.username = username
        self.password = password
        self.group_id = booking_group_id
        self.contract_id = contract_id
        self.base_url = "https://lulebo.aptustotal.se/AptusPortal"
        self.session = None

    # ------------------------------------------------------------------ #
    # Authentication / session handling
    # ------------------------------------------------------------------ #
    def _authenticate(self) -> bool:
        """Log in to lulebo.se and follow the magic link into the Aptus portal."""
        session = requests.Session()
        session.headers.update(_HEADERS)

        # NOTE: do not log the username — it is a personnummer (national ID).
        _LOGGER.debug("Lulebo API: attempting login")

        try:
            # GET the login page first, so we can pick up any anti-forgery token
            # and the session cookie the POST expects.
            login_page = session.get(
                "https://www.lulebo.se/Account/Login", timeout=REQUEST_TIMEOUT
            )

            login_payload = {
                "UserId": self.username,
                "Password": self.password,
                "RememberMe": "true",
            }

            # ASP.NET MVC login forms usually require a __RequestVerificationToken.
            # Include it if present; harmless if the site doesn't use one.
            token = self._extract_verification_token(login_page.text)
            if token:
                login_payload["__RequestVerificationToken"] = token

            session.post(
                "https://www.lulebo.se/Account/Login",
                data=login_payload,
                timeout=REQUEST_TIMEOUT,
            )

            timestamp = int(time.time() * 1000)
            links_url = (
                "https://www.lulebo.se/Account/EngagementLoadLinks"
                f"?usergrouptype=Residents&contractid={self.contract_id}&_={timestamp}"
            )
            dashboard = session.get(links_url, timeout=REQUEST_TIMEOUT)
        except requests.RequestException as err:
            _LOGGER.error("Lulebo API: network error during login: %s", err)
            return False

        soup = BeautifulSoup(dashboard.text, "html.parser")
        magic = soup.find("a", href=lambda h: h and "lulebo.aptustotal.se" in h)
        if not magic or not magic.get("href"):
            _LOGGER.error(
                "Lulebo API: could not find the Aptus link after login. "
                "Check credentials / contract_id."
            )
            return False

        try:
            session.get(magic["href"], timeout=REQUEST_TIMEOUT)
        except requests.RequestException as err:
            _LOGGER.error("Lulebo API: network error following magic link: %s", err)
            return False

        self.session = session
        _LOGGER.debug("Lulebo API: login successful")
        return True

    @staticmethod
    def _extract_verification_token(html: str):
        try:
            soup = BeautifulSoup(html, "html.parser")
            field = soup.find("input", attrs={"name": "__RequestVerificationToken"})
            if field and field.get("value"):
                return field["value"]
        except Exception:  # pragma: no cover - defensive only
            pass
        return None

    @staticmethod
    def _looks_like_login(resp) -> bool:
        """Detect that a protected request was bounced to a login page.

        Aptus/Lulebo redirect expired sessions to an /Account/Login URL, and
        ``requests`` follows redirects by default, so the final URL is the
        most reliable signal.
        """
        if resp is None:
            return True
        final_url = (resp.url or "").lower()
        return "login" in final_url or "/account/" in final_url

    def _ensure_session(self) -> bool:
        if self.session is not None:
            return True
        return self._authenticate()

    def _get(self, url, *, allow_redirects=True):
        """GET a URL, transparently re-authenticating once if the session died.

        Returns the response, or ``None`` on a hard failure (network error or
        we could not re-establish a session).
        """
        if not self._ensure_session():
            return None

        try:
            resp = self.session.get(
                url, timeout=REQUEST_TIMEOUT, allow_redirects=allow_redirects
            )
        except requests.RequestException as err:
            _LOGGER.error("Lulebo API: request error for %s: %s", url, err)
            return None

        # Only redirect-following requests can be checked for the login bounce.
        if allow_redirects and self._looks_like_login(resp):
            _LOGGER.debug("Lulebo API: session expired, re-authenticating")
            self.session = None
            if not self._authenticate():
                return None
            try:
                resp = self.session.get(
                    url, timeout=REQUEST_TIMEOUT, allow_redirects=allow_redirects
                )
            except requests.RequestException as err:
                _LOGGER.error("Lulebo API: retry request error for %s: %s", url, err)
                return None

        return resp

    # ------------------------------------------------------------------ #
    # Availability
    # ------------------------------------------------------------------ #
    def get_week_availability(self):
        """Return {date: [slot_no, ...]} of free slots.

        Returns ``None`` if *every* page fetch failed (so the caller can keep
        the previous data), or ``{}`` when the calendar loaded but is full.
        """
        available_slots = {}
        next_week = (datetime.now() + timedelta(days=7)).strftime("%Y-%m-%d")

        pages = [
            f"{self.base_url}/CustomerBooking/BookingCalendar?bookingGroupId={self.group_id}",
            f"{self.base_url}/CustomerBooking/BookingCalendar?bookingGroupId={self.group_id}&passDate={next_week}",
        ]

        got_any_page = False
        for url in pages:
            resp = self._get(url)
            if resp is None or self._looks_like_login(resp):
                continue
            got_any_page = True

            soup = BeautifulSoup(resp.text, "html.parser")
            for btn in soup.find_all("button", class_="bookButton"):
                onclick = btn.get("onclick", "")
                match = re.search(r"passNo=(\d+)&passDate=([^&']+)", onclick)
                if match:
                    slot_no, slot_date = match.group(1), match.group(2)
                    available_slots.setdefault(slot_date, [])
                    if slot_no not in available_slots[slot_date]:
                        available_slots[slot_date].append(slot_no)

        if not got_any_page:
            _LOGGER.warning("Lulebo API: could not load any availability page")
            return None

        _LOGGER.debug("Lulebo API: %d day(s) with free slots", len(available_slots))
        return available_slots

    # ------------------------------------------------------------------ #
    # Active bookings
    # ------------------------------------------------------------------ #
    def get_active_bookings(self, detailed=False):
        """Return the user's current bookings.

        ``detailed=False`` (default, backwards compatible): ``{date: unbook_url}``
        ``detailed=True``:  ``{date: {"url": unbook_url, "slot": passNo_or_None}}``

        Returns ``None`` if the pages could not be loaded at all.
        """
        collected = self._collect_bookings()
        if collected is None:
            return None
        if detailed:
            return collected
        return {date: info["url"] for date, info in collected.items()}

    def _collect_bookings(self):
        """Scrape bookings as {date: {"url": ..., "slot": ...}} or None on failure."""
        bookings = {}
        loaded_any = False

        # --- Strategy 1: overview page Unbook anchor links -------------------
        overview_url = f"{self.base_url}/CustomerBooking"
        overview = self._get(overview_url)
        overview_soup = None
        if overview is not None and not self._looks_like_login(overview):
            loaded_any = True
            overview_soup = BeautifulSoup(overview.text, "html.parser")
            for link in overview_soup.find_all(
                "a", href=re.compile(r"/CustomerBooking/Unbook/\d+")
            ):
                href = link.get("href", "")
                # Search nearby text for a YYYY-MM-DD date.
                container = link.find_parent("tr") or link.parent
                row_text = container.get_text(" ", strip=True) if container else ""
                date_match = re.search(r"(\d{4}-\d{2}-\d{2})", row_text)
                if date_match:
                    date_key = date_match.group(1)
                    slot = self._slot_from_path(href)
                    bookings[date_key] = {
                        "url": f"https://lulebo.aptustotal.se{href}",
                        "slot": slot,
                    }

        # --- Strategy 2: inline ConfirmCancelBooking() calls -----------------
        calendar_url = (
            f"{self.base_url}/CustomerBooking/BookingCalendar?bookingGroupId={self.group_id}"
        )
        calendar = self._get(calendar_url)
        cal_soup = None
        if calendar is not None and not self._looks_like_login(calendar):
            loaded_any = True
            cal_soup = BeautifulSoup(calendar.text, "html.parser")

        scripts = []
        if overview_soup:
            scripts += overview_soup.find_all("script")
        if cal_soup:
            scripts += cal_soup.find_all("script")

        for script in scripts:
            if not script.string:
                continue
            # findall (not search) so we catch ALL bookings in a script block.
            for path in re.findall(
                r"ConfirmCancelBooking\([^,]+,\s*'([^']+)'", script.string
            ):
                date_match = re.search(r"passDate=(\d{4}-\d{2}-\d{2})", path)
                if date_match:
                    date_key = date_match.group(1)
                    bookings.setdefault(
                        date_key,
                        {
                            "url": f"https://lulebo.aptustotal.se{path}",
                            "slot": self._slot_from_path(path),
                        },
                    )

        # --- Strategy 3: "booked by me" button classes on the grid ----------
        if cal_soup:
            for btn in cal_soup.find_all(
                "button", class_=re.compile(r"[Mm]y|[Bb]ooked[Bb]y[Mm]e|ownBook")
            ):
                onclick = btn.get("onclick", "")
                date_match = re.search(r"passDate=(\d{4}-\d{2}-\d{2})", onclick)
                path_match = re.search(r"'(/CustomerBooking[^']+)'", onclick)
                if date_match and path_match:
                    date_key = date_match.group(1)
                    bookings.setdefault(
                        date_key,
                        {
                            "url": f"https://lulebo.aptustotal.se{path_match.group(1)}",
                            "slot": self._slot_from_path(path_match.group(1)),
                        },
                    )

        if not loaded_any:
            _LOGGER.warning("Lulebo API: could not load any bookings page")
            return None

        _LOGGER.debug("Lulebo API: found %d active booking(s)", len(bookings))
        return bookings

    @staticmethod
    def _slot_from_path(path: str):
        """Extract the passNo from an unbook URL/path, if present."""
        m = re.search(r"passNo=(\d+)", path or "")
        return m.group(1) if m else None

    # ------------------------------------------------------------------ #
    # Booking / cancelling
    # ------------------------------------------------------------------ #
    def book_time(self, target_date: str, time_slot: str) -> bool:
        if not self._ensure_session():
            return False

        url = (
            f"{self.base_url}/CustomerBooking/Book"
            f"?passNo={time_slot}&passDate={target_date}&bookingGroupId={self.group_id}"
        )

        result = self._booking_request(url)
        if result == "expired":
            # Session was dead; re-auth and try exactly once more.
            self.session = None
            if not self._authenticate():
                return False
            result = self._booking_request(url)

        if result is True:
            _LOGGER.info("Lulebo API: booked slot %s on %s", time_slot, target_date)
            return True

        _LOGGER.error("Lulebo API: booking failed for slot %s on %s", time_slot, target_date)
        return False

    def _booking_request(self, url):
        """Perform a booking GET. Returns True (ok), False (failed), or 'expired'."""
        try:
            resp = self.session.get(
                url, timeout=REQUEST_TIMEOUT, allow_redirects=False
            )
        except requests.RequestException as err:
            _LOGGER.error("Lulebo API: network error during booking: %s", err)
            return False

        if resp.status_code == 302:
            # A dead session ALSO 302s — but to a login page. Only treat a
            # redirect that is NOT to login as a real success.
            location = (resp.headers.get("Location") or "").lower()
            if "login" in location or "/account/" in location:
                return "expired"
            return True
        return False

    def cancel_time(self, target_date: str) -> bool:
        if not self._ensure_session():
            return False

        _LOGGER.debug("Lulebo API: cancelling booking for %s", target_date)

        active = self.get_active_bookings()
        if active is None:
            _LOGGER.error("Lulebo API: could not load bookings while cancelling %s", target_date)
            return False

        if target_date not in active:
            _LOGGER.error(
                "Lulebo API: no active booking for %s (known: %s)",
                target_date,
                list(active.keys()),
            )
            return False

        unbook_url = active[target_date]
        resp = self._get(unbook_url, allow_redirects=False)
        if resp is not None and resp.status_code in (200, 302):
            _LOGGER.info("Lulebo API: cancelled booking on %s", target_date)
            return True

        code = resp.status_code if resp is not None else "no response"
        _LOGGER.error("Lulebo API: cancellation failed for %s (status %s)", target_date, code)
        return False
