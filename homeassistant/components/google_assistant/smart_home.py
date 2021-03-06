"""Support for Google Assistant Smart Home API."""
import logging

# Typing imports
# pylint: disable=using-constant-test,unused-import,ungrouped-imports
# if False:
from aiohttp.web import Request, Response  # NOQA
from typing import Dict, Tuple, Any  # NOQA
from homeassistant.helpers.entity import Entity  # NOQA
from homeassistant.core import HomeAssistant  # NOQA

from homeassistant.const import (
    ATTR_SUPPORTED_FEATURES, ATTR_ENTITY_ID,
    CONF_FRIENDLY_NAME, STATE_OFF,
    SERVICE_TURN_OFF, SERVICE_TURN_ON
)
from homeassistant.components import (
    switch, light, cover, media_player, group, fan
)

from .const import (
    ATTR_GOOGLE_ASSISTANT_NAME,
    COMMAND_BRIGHTNESS, COMMAND_ONOFF,
    PREFIX_TRAITS, PREFIX_TYPES,
    CONF_ALIASES,
)

_LOGGER = logging.getLogger(__name__)

# Mapping is [actions schema, command, optional features]
# optional is SUPPORT_* = (trait, command)
MAPPING_COMPONENT = {
    group.DOMAIN: ['SCENE', 'ActivateScene', None],
    switch.DOMAIN: ['SWITCH', 'OnOff', None],
    fan.DOMAIN: ['SWITCH', 'OnOff', None],
    light.DOMAIN: [
        'LIGHT', 'OnOff', {
            light.SUPPORT_BRIGHTNESS: 'Brightness',
            light.SUPPORT_RGB_COLOR: 'ColorSpectrum',
            light.SUPPORT_COLOR_TEMP: 'ColorTemperature'
        }
    ],
    cover.DOMAIN: [
        'LIGHT', 'OnOff', {
            cover.SUPPORT_SET_POSITION: 'Brightness'
        }
    ],
    media_player.DOMAIN: [
        'LIGHT', 'OnOff', {
            media_player.SUPPORT_VOLUME_SET: 'Brightness'
        }
    ],
}  # type: Dict[str, list]


def make_actions_response(request_id: str, payload: dict) -> dict:
    """Helper to simplify format for response."""
    return {'requestId': request_id, 'payload': payload}


def entity_to_device(entity: Entity):
    """Convert a hass entity into an google actions device."""
    class_data = MAPPING_COMPONENT.get(entity.domain)
    if class_data is None:
        return None

    device = {
        'id': entity.entity_id,
        'name': {},
        'traits': [],
        'willReportState': False,
    }
    device['type'] = PREFIX_TYPES + class_data[0]
    device['traits'].append(PREFIX_TRAITS + class_data[1])

    # handle custom names
    device['name']['name'] = \
        entity.attributes.get(ATTR_GOOGLE_ASSISTANT_NAME) or \
        entity.attributes.get(CONF_FRIENDLY_NAME)

    # use aliases
    aliases = entity.attributes.get(CONF_ALIASES)
    if isinstance(aliases, list):
        device['name']['nicknames'] = aliases
    else:
        _LOGGER.warning("%s must be a list", CONF_ALIASES)

    # add trait if entity supports feature
    if class_data[2]:
        supported = entity.attributes.get(ATTR_SUPPORTED_FEATURES, 0)
        for feature, trait in class_data[2].items():
            if feature & supported > 0:
                device['traits'].append(PREFIX_TRAITS + trait)

    return device


def query_device(entity: Entity) -> dict:
    """Take an entity and return a properly formatted device object."""
    final_state = entity.state != STATE_OFF
    final_brightness = entity.attributes.get(light.ATTR_BRIGHTNESS, 255
                                             if final_state else 0)

    if entity.domain == media_player.DOMAIN:
        level = entity.attributes.get(media_player.ATTR_MEDIA_VOLUME_LEVEL, 1.0
                                      if final_state else 0.0)
        # Convert 0.0-1.0 to 0-255
        final_brightness = round(min(1.0, level) * 255)

    if final_brightness is None:
        final_brightness = 255 if final_state else 0

    final_brightness = 100 * (final_brightness / 255)

    return {
        "on": final_state,
        "online": True,
        "brightness": int(final_brightness)
    }


# erroneous bug on old pythons and pylint
# https://github.com/PyCQA/pylint/issues/1212
# pylint: disable=invalid-sequence-index
def determine_service(entity_id: str, command: str,
                      params: dict) -> Tuple[str, dict]:
    """
    Determine service and service_data.

    Attempt to return a tuple of service and service_data based on the entity
    and action requested.
    """
    domain = entity_id.split('.')[0]
    service_data = {ATTR_ENTITY_ID: entity_id}  # type: Dict[str, Any]
    # special media_player handling
    if domain == 'media_player' and command == COMMAND_BRIGHTNESS:
        brightness = params.get('brightness', 0)
        service_data['volume'] = brightness / 100
        return (media_player.SERVICE_VOLUME_SET, service_data)

    # special cover handling
    if domain == 'cover' and command == COMMAND_BRIGHTNESS:
        service_data['position'] = params.get('brightness', 0)
        return (cover.SERVICE_SET_COVER_POSITION, service_data)
    elif domain == 'cover' and command == COMMAND_ONOFF:
        if params.get('on') is True:
            return (cover.SERVICE_OPEN_COVER, service_data)
        return (cover.SERVICE_CLOSE_COVER, service_data)

    if command == COMMAND_BRIGHTNESS:
        brightness = params.get('brightness')
        service_data['brightness'] = int(brightness / 100 * 255)
        return (SERVICE_TURN_ON, service_data)

    if COMMAND_ONOFF == command and params.get('on') is True:
        return (SERVICE_TURN_ON, service_data)
    return (SERVICE_TURN_OFF, service_data)
