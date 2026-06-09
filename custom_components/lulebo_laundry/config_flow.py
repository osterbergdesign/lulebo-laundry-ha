import voluptuous as vol
from homeassistant import config_entries
from .const import DOMAIN

class LuleboConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Hantera konfigurationsflödet (popupen) för Lulebo Tvättstuga."""
    VERSION = 1

    async def async_step_user(self, user_input=None):
        """Första steget när användaren klickar på Lägg till integration."""
        if user_input is not None:
            # Sparar värdena och skapar en Config Entry i Home Assistant
            return self.async_create_entry(title="Lulebo Tvättstuga", data=user_input)

        # Definiera fälten och ge ID-numren dina standardvärden som förslag
        data_schema = vol.Schema({
            vol.Required("username"): str,
            vol.Required("password"): str,
            vol.Required("booking_group_id", default="96"): str,
            vol.Required("contract_id", default="334931"): str,
        })

        return self.async_show_form(
            step_id="user", data_schema=data_schema
        )