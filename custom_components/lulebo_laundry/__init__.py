import logging
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, ServiceCall
from .const import DOMAIN
from .api import LuleboLaundryAPI

_LOGGER = logging.getLogger(__name__)
PLATFORMS = ["sensor", "calendar"]

async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Sätt upp Lulebo Tvättstuga från en Config Entry (Popupen)."""
    hass.data.setdefault(DOMAIN, {})
    
    # Hämtar exakt det användaren skrev i popupen
    api = LuleboLaundryAPI(
        username=entry.data["username"],
        password=entry.data["password"],
        booking_group_id=entry.data["booking_group_id"],
        contract_id=entry.data["contract_id"]
    )
    
    # Sparar API-instansen
    hass.data[DOMAIN][entry.entry_id] = api

    # --- REGISTRERA TJÄNSTERNA FÖR ATT BOKA OCH AVBOKA ---
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

    hass.services.async_register(DOMAIN, "book", handle_book)
    hass.services.async_register(DOMAIN, "cancel", handle_cancel)
    
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True

async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Ta bort sparad data om användaren raderar integrationen."""
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        hass.data[DOMAIN].pop(entry.entry_id)
    return unload_ok
