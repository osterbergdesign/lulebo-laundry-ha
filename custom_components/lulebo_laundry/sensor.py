import logging
import traceback
from datetime import date, timedelta

from homeassistant.components.sensor import SensorEntity
from homeassistant.util import dt as dt_util

from .const import DOMAIN, SLOT_LABELS, SLOT_TIMES

_LOGGER = logging.getLogger(__name__)

SCAN_INTERVAL = timedelta(hours=1)


async def async_setup_entry(hass, entry, async_add_entities):
    """Set up the availability sensor from a config entry."""
    api = hass.data[DOMAIN][entry.entry_id]
    sensor = LuleboAvailabilitySensor(api, entry)
    # so the book/cancel actions can refresh it straight away
    hass.data[DOMAIN].setdefault(f"{entry.entry_id}_entities", []).append(sensor)
    async_add_entities([sensor], True)


class LuleboAvailabilitySensor(SensorEntity):
    _attr_icon = "mdi:washing-machine"

    def __init__(self, api, entry):
        self.api = api
        self._state = None
        self._attributes = {
            "available_dates": {},
            "raw_slots": {},
            "current_bookings": {},
            "my_bookings": {},
            "days": [],
            "slot_times": {slot: [start, end] for slot, (start, end) in SLOT_TIMES.items()},
        }
        self._name = "Lulebo Laundry Availability"
        # Stable unique_id so the entity can be customised in the UI.
        self._attr_unique_id = f"{entry.entry_id}_availability"

    @property
    def name(self):
        return self._name

    @property
    def state(self):
        return self._state

    @property
    def extra_state_attributes(self):
        return self._attributes

    def update(self):
        """Fetch new data from the Lulebo API (runs in the executor)."""
        _LOGGER.debug("Lulebo sensor: starting update")

        try:
            # The two weeks the booking calendar shows (this week and next), Monday first.
            # The card uses this so fully booked days still show up.
            monday = date.today() - timedelta(days=date.today().weekday())
            self._attributes["days"] = [(monday + timedelta(days=i)).isoformat() for i in range(14)]

            # 1. Active bookings. None => fetch failed, keep previous value.
            detailed = self.api.get_active_bookings(detailed=True)
            if detailed is None:
                _LOGGER.warning(
                    "Lulebo sensor: could not fetch bookings, keeping last known data"
                )
            else:
                # {date: unbook_url} - unchanged, for existing scripts and cards
                self._attributes["current_bookings"] = {d: info["url"] for d, info in detailed.items()}
                # {date: slot number ("0"-"3"), or None if the start time didn't match a slot}
                self._attributes["my_bookings"] = {d: info.get("slot") for d, info in detailed.items()}

            # 2. Available slots. None => fetch failed, keep previous value.
            data = self.api.get_week_availability()
            if data is None:
                _LOGGER.warning(
                    "Lulebo sensor: could not fetch availability, keeping last known data"
                )
                return

            self._state = sum(len(slots) for slots in data.values())

            readable = {
                date: [SLOT_LABELS.get(s, s) for s in slots]
                for date, slots in data.items()
            }
            self._attributes["available_dates"] = readable
            self._attributes["raw_slots"] = data
            self._attributes["updated"] = dt_util.now().isoformat()
            _LOGGER.debug("Lulebo sensor: update complete")

        except Exception as err:  # pragma: no cover - defensive
            _LOGGER.error("Lulebo sensor: crashed during update: %s", err)
            _LOGGER.debug(traceback.format_exc())
