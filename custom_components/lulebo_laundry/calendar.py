"""Calendar platform: exposes active laundry bookings as calendar events.

Each booking becomes a CalendarEvent. When the booked slot number is known,
the event uses the real time window (e.g. 14:00-17:30); otherwise it falls
back to an all-day event on the booked date.
"""

import logging
from datetime import datetime, time, timedelta

from homeassistant.components.calendar import CalendarEntity, CalendarEvent
from homeassistant.util import dt as dt_util

from .const import DOMAIN, SLOT_TIMES

_LOGGER = logging.getLogger(__name__)

SCAN_INTERVAL = timedelta(hours=1)


async def async_setup_entry(hass, entry, async_add_entities):
    api = hass.data[DOMAIN][entry.entry_id]
    async_add_entities([LuleboCalendar(api, entry)], True)


class LuleboCalendar(CalendarEntity):
    _attr_icon = "mdi:washing-machine"

    def __init__(self, api, entry):
        self.api = api
        self._events: list[CalendarEvent] = []
        self._attr_name = "Lulebo Tvättstuga"
        self._attr_unique_id = f"{entry.entry_id}_calendar"

    @property
    def event(self):
        """Return the next (or currently ongoing) event."""
        now = dt_util.now()
        upcoming = [e for e in self._events if self._event_end(e) >= now]
        upcoming.sort(key=lambda e: self._event_start(e))
        return upcoming[0] if upcoming else None

    async def async_get_events(self, hass, start_date, end_date):
        """Return events that overlap the requested [start_date, end_date] range."""
        return [
            e
            for e in self._events
            if self._event_start(e) < end_date and self._event_end(e) > start_date
        ]

    async def async_update(self):
        """Refresh bookings (blocking scrape runs in the executor)."""
        bookings = await self.hass.async_add_executor_job(
            self.api.get_active_bookings, True  # detailed=True
        )

        # None => fetch failed; keep the previous events rather than clearing.
        if bookings is None:
            _LOGGER.debug("Lulebo calendar: fetch failed, keeping existing events")
            return

        events = []
        for date_str, info in bookings.items():
            event = self._build_event(date_str, info.get("slot"))
            if event:
                events.append(event)
        self._events = events

    def _build_event(self, date_str, slot):
        try:
            date_obj = datetime.strptime(date_str, "%Y-%m-%d").date()
        except (ValueError, TypeError):
            _LOGGER.debug("Lulebo calendar: bad date %s", date_str)
            return None

        summary = "Tvättstuga 🧺"

        if slot is not None and str(slot) in SLOT_TIMES:
            start_s, end_s = SLOT_TIMES[str(slot)]
            tz = dt_util.DEFAULT_TIME_ZONE
            start = datetime.combine(
                date_obj, time.fromisoformat(start_s), tzinfo=tz
            )
            end = datetime.combine(date_obj, time.fromisoformat(end_s), tzinfo=tz)
            return CalendarEvent(
                start=start,
                end=end,
                summary=f"{summary} {start_s}-{end_s}",
                description="Bokad tvättid via Home Assistant",
                uid=f"lulebo-{date_str}-{slot}",
            )

        # Unknown slot -> all-day event.
        return CalendarEvent(
            start=date_obj,
            end=date_obj + timedelta(days=1),
            summary=summary,
            description="Bokad tvättid via Home Assistant",
            uid=f"lulebo-{date_str}",
        )

    @staticmethod
    def _event_start(event):
        start = event.start
        if isinstance(start, datetime):
            return start
        return dt_util.start_of_local_day(start)

    @staticmethod
    def _event_end(event):
        end = event.end
        if isinstance(end, datetime):
            return end
        return dt_util.start_of_local_day(end)
