import logging
import traceback
from datetime import timedelta

from homeassistant.components.sensor import SensorEntity

from .const import DOMAIN, SLOT_LABELS

_LOGGER = logging.getLogger(__name__)

SCAN_INTERVAL = timedelta(hours=1)


async def async_setup_entry(hass, entry, async_add_entities):
    """Set up the availability sensor from a config entry."""
    api = hass.data[DOMAIN][entry.entry_id]
    async_add_entities([LuleboAvailabilitySensor(api, entry)], True)


class LuleboAvailabilitySensor(SensorEntity):
    _attr_icon = "mdi:washing-machine"

    def __init__(self, api, entry):
        self.api = api
        self._state = None
        self._attributes = {
            "available_dates": {},
            "raw_slots": {},
            "current_bookings": {},
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
            # 1. Active bookings. None => fetch failed, keep previous value.
            my_bookings = self.api.get_active_bookings()
            if my_bookings is None:
                _LOGGER.warning(
                    "Lulebo sensor: could not fetch bookings, keeping last known data"
                )
            else:
                self._attributes["current_bookings"] = my_bookings

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
            _LOGGER.debug("Lulebo sensor: update complete")

        except Exception as err:  # pragma: no cover - defensive
            _LOGGER.error("Lulebo sensor: crashed during update: %s", err)
            _LOGGER.debug(traceback.format_exc())
