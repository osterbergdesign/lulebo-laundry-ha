import logging
import traceback
from datetime import timedelta
from homeassistant.components.sensor import SensorEntity
from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)

SCAN_INTERVAL = timedelta(hours=1) 

async def async_setup_entry(hass, entry, async_add_entities):
    """Sätt upp sensorn via Config Flow (Popupen)."""
    api = hass.data[DOMAIN][entry.entry_id]
    async_add_entities([LuleboAvailabilitySensor(api)], True)

class LuleboAvailabilitySensor(SensorEntity):
    def __init__(self, api):
        self.api = api
        self._state = None
        # Vi förbereder tomma fält direkt från start så de aldrig är spårlöst borta
        self._attributes = {
            "available_dates": {},
            "raw_slots": {},
            "current_bookings": {}
        }
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
        """Hämta ny data från Lulebo API."""
        _LOGGER.warning("Lulebo Sensor: Startar uppdatering...")
        
        try:
            # 1. Hämta aktiva bokningar FÖRST och spara direkt
            my_bookings = self.api.get_active_bookings()
            
            if not my_bookings or my_bookings == "None":
                my_bookings = {}
                
            self._attributes["current_bookings"] = my_bookings
            _LOGGER.warning(f"Lulebo Sensor: Sparade aktiva bokningar i attribut: {my_bookings}")

            # 2. Hämta lediga tider efteråt
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

                self._attributes["available_dates"] = readable_data
                self._attributes["raw_slots"] = data
                _LOGGER.warning("Lulebo Sensor: Hela uppdateringen kördes utan problem!")
            else:
                _LOGGER.warning("Lulebo Sensor: Kunde inte nå kalendern för lediga tider.")

        except Exception as e:
            # Om koden kraschar kommer den skriva ut EXAKT varför och på vilken rad i din HA-logg!
            _LOGGER.error(f"Lulebo Sensor: DET BLEV EN CRASH! Felmeddelande: {e}")
            _LOGGER.error(traceback.format_exc())
