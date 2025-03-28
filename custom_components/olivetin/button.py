from homeassistant.core import HomeAssistant
from homeassistant.components.button import ButtonEntity
from homeassistant.config_entries import ConfigEntry

from homeassistant.const import CONF_HOST, CONF_PASSWORD, CONF_USERNAME

class OliveTinActionEntity(ButtonEntity):
    def __init__(self, name, entry):
        self._attr_name = name
        self.entry = entry

    @property
    def name(self):
        return self._attr_name

    async def async_press(self) -> None:
        print(f"Button press {self}")
        print(f"Button press {self._attr_name}")
        print(f"Button press {self.entry.title}")
        print(f"Button press {self.entry.data[CONF_HOST]}")
        print(f"Button press {self.entry.hub}")
        print(f"Button press {self.entry.apiclient}")

        self.entry.apiclient.start_action(self.entry.hub, self.self._attr_name)


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry, async_add_entities):
    my_entity = OliveTinActionEntity("Test", entry)

    async_add_entities([my_entity])
