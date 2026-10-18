import logging
import os

import voluptuous as vol

from homeassistant.components import frontend
from homeassistant.components.http import StaticPathConfig
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.exceptions import HomeAssistantError
import homeassistant.helpers.config_validation as cv

from .const import CARD_URL, DOMAIN, SLOT_TIMES, STATIC_URL
from .api import LuleboLaundryAPI

_LOGGER = logging.getLogger(__name__)
PLATFORMS = ["sensor", "calendar"]

_DATE = vol.All(cv.string, vol.Match(r"^\d{4}-\d{2}-\d{2}$", msg="Use the format YYYY-MM-DD"))
BOOK_SCHEMA = vol.Schema({
    vol.Required("date"): _DATE,
    vol.Required("slot"): vol.All(vol.Coerce(str), vol.In(list(SLOT_TIMES))),
})
CANCEL_SCHEMA = vol.Schema({vol.Required("date"): _DATE})


def _version() -> str:
    import json
    with open(os.path.join(os.path.dirname(__file__), "manifest.json"), encoding="utf-8") as f:
        return json.load(f).get("version", "0")


async def _async_register_card(hass: HomeAssistant) -> None:
    """Serve the booking card and add it to every dashboard (once per Home Assistant run)."""
    if hass.data.get(f"{DOMAIN}_card"):
        return
    hass.data[f"{DOMAIN}_card"] = True
    www = os.path.join(os.path.dirname(__file__), "www")
    await hass.http.async_register_static_paths([StaticPathConfig(STATIC_URL, www, False)])
    version = await hass.async_add_executor_job(_version)
    frontend.add_extra_js_url(hass, f"{CARD_URL}?v={version}")


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

    async def _refresh_entities() -> None:
        """Re-read availability and bookings so the card and calendar update right away."""
        for entity in list(hass.data[DOMAIN].get(f"{entry.entry_id}_entities", [])):
            try:
                await entity.async_update_ha_state(force_refresh=True)
            except Exception as err:  # noqa: BLE001 - a failed refresh shouldn't fail the booking
                _LOGGER.debug("Lulebo: refresh of %s failed: %s", entity.entity_id, err)

    # --- REGISTRERA TJÄNSTERNA FÖR ATT BOKA OCH AVBOKA ---
    async def handle_book(call: ServiceCall):
        target_date = call.data["date"]
        time_slot = str(call.data["slot"])
        success = await hass.async_add_executor_job(api.book_time, target_date, time_slot)
        if not success:
            start, end = SLOT_TIMES.get(time_slot, ("?", "?"))
            raise HomeAssistantError(f"Kunde inte boka {target_date} {start}–{end}. Tiden kan redan vara tagen.")
        _LOGGER.info("Successfully booked slot %s on %s", time_slot, target_date)
        await _refresh_entities()

    async def handle_cancel(call: ServiceCall):
        target_date = call.data["date"]
        success = await hass.async_add_executor_job(api.cancel_time, target_date)
        if not success:
            raise HomeAssistantError(f"Kunde inte avboka tiden {target_date}.")
        _LOGGER.info("Successfully cancelled booking on %s", target_date)
        await _refresh_entities()

    async def handle_refresh(call: ServiceCall):
        await _refresh_entities()

    hass.services.async_register(DOMAIN, "book", handle_book, schema=BOOK_SCHEMA)
    hass.services.async_register(DOMAIN, "cancel", handle_cancel, schema=CANCEL_SCHEMA)
    hass.services.async_register(DOMAIN, "refresh", handle_refresh)

    await _async_register_card(hass)
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Ta bort sparad data om användaren raderar integrationen."""
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        hass.data[DOMAIN].pop(entry.entry_id)
        hass.data[DOMAIN].pop(f"{entry.entry_id}_entities", None)
    return unload_ok
