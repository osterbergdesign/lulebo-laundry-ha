import logging
from datetime import timedelta
from homeassistant.components.sensor import SensorEntity
from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)

SCAN_INTERVAL = timedelta(hours=1) 

async def async_setup_entry(hass, entry, async_add_entities):
    """Sätt upp sensorn via Config Flow (Popupen)."""
    # Hämtar API-objektet baserat på det unika entry_id som skapades i __init__.py
    api = hass.data[DOMAIN][entry.entry_id]
    async_add_entities([LuleboAvailabilitySensor(api)], True)

class LuleboAvailabilitySensor(SensorEntity):
    def __init__(self, api):
        self.api = api
        self._state = None
        self._attributes = {}
        self._name = "Lulebo Laundry Availability"

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
        """Fetch new state data for the sensor."""
        _LOGGER.info("Lulebo Sensor: Fetching latest week availability...")
        data = self.api.get_week_availability()
        
        if data is not None:
            total_slots = sum(len(slots) for slots in data.values())
            self._state = total_slots

            readable_data = {}
            slot_map = {
                "0": "07:00 - 10:30",
                "1": "10:30 - 14:00",
                "2": "14:00 - 17:30",
                "3": "17:30 - 21:00"
            }

            for date, slots in data.items():
                readable_data[date] = [slot_map.get(s, s) for s in slots]

            my_bookings = self.api.get_active_bookings()

            if my_bookings is None:
                my_bookings = self._attributes.get("current_bookings", {})

            self._attributes = {
                "available_dates": readable_data,
                "raw_slots": data,
                "current_bookings": my_bookings
            }
        else:
            _LOGGER.warning("Kunde inte nå Lulebo. Behåller tidigare känd data för att undvika glitchar på dashboarden.")