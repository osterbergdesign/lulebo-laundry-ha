import logging
import voluptuous as vol
import homeassistant.helpers.config_validation as cv
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.helpers.discovery import load_platform
from .api import LuleboLaundryAPI

DOMAIN = "lulebo_laundry"
_LOGGER = logging.getLogger(__name__)

# Replace these with your actual Lulebo credentials
USERNAME = "YOUR USERNAME"
PASSWORD = "YOUR PASSWORD"

def setup(hass: HomeAssistant, config: dict):
    """Set up the Lulebo Laundry component."""
    
    # Initialize our custom API
    api = LuleboLaundryAPI(USERNAME, PASSWORD)
    
    # Store the API so sensor.py can grab it
    hass.data.setdefault(DOMAIN, {})
    hass.data[DOMAIN]["api"] = api
    
    def handle_book(call: ServiceCall):
        target_date = call.data.get("date")
        time_slot = call.data.get("slot")
        success = api.book_time(target_date, time_slot)
        if success:
            _LOGGER.info(f"Successfully booked slot {time_slot} on {target_date}")
        else:
            _LOGGER.error(f"Failed to book slot {time_slot} on {target_date}")

    def handle_cancel(call: ServiceCall):
        target_date = call.data.get("date")
        success = api.cancel_time(target_date)
        if success:
            _LOGGER.info(f"Successfully cancelled booking on {target_date}")
        else:
            _LOGGER.error(f"Failed to cancel booking on {target_date}")

    # Register the services
    hass.services.register(DOMAIN, "book", handle_book)
    hass.services.register(DOMAIN, "cancel", handle_cancel)

    # Tell Home Assistant to load our new sensor.py file
    load_platform(hass, "sensor", DOMAIN, {}, config)

    return True