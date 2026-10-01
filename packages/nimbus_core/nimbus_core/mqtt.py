"""Small paho-mqtt helpers: a client that connects with retry and reconnects on its own."""
from __future__ import annotations

import json
import logging
import time
import uuid
from typing import Any, Callable

import paho.mqtt.client as mqtt

from .config import get_settings

log = logging.getLogger("nimbus.mqtt")


def make_client(name: str, on_message: Callable[[str, dict[str, Any]], None] | None = None,
                subscriptions: list[str] | None = None) -> mqtt.Client:
    client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id=f"{name}-{uuid.uuid4().hex[:6]}")
    client.reconnect_delay_set(min_delay=1, max_delay=10)
    s = get_settings()
    if s.mqtt_username:
        client.username_pw_set(s.mqtt_username, s.mqtt_password or None)
    if s.mqtt_tls:
        client.tls_set()

    def _on_connect(c, _userdata, _flags, reason_code, _props):
        log.info("%s connected to MQTT (%s)", name, reason_code)
        for t in subscriptions or []:
            c.subscribe(t, qos=1)

    def _on_message(_c, _userdata, msg):
        if on_message is None:
            return
        try:
            payload = json.loads(msg.payload.decode("utf-8") or "{}")
        except (ValueError, UnicodeDecodeError):
            log.warning("bad payload on %s", msg.topic)
            return
        try:
            on_message(msg.topic, payload)
        except Exception:  # noqa: BLE001
            log.exception("handler failed for %s", msg.topic)

    client.on_connect = _on_connect
    client.on_message = _on_message
    while True:
        try:
            client.connect(s.mqtt_host, s.mqtt_port, keepalive=30)
            break
        except OSError as e:
            log.info("%s waiting for MQTT broker at %s:%s (%s)", name, s.mqtt_host, s.mqtt_port, e)
            time.sleep(2)
    return client


def publish_json(client: mqtt.Client, topic: str, payload: dict[str, Any], retain: bool = False) -> None:
    client.publish(topic, json.dumps(payload), qos=1, retain=retain)


def publish_once(topic: str, payload: dict[str, Any], retain: bool = False) -> None:
    """Fire-and-forget publish used by the API's scenario control."""
    import paho.mqtt.publish as publish

    s = get_settings()
    auth = {"username": s.mqtt_username, "password": s.mqtt_password} if s.mqtt_username else None
    publish.single(topic, json.dumps(payload), qos=1, retain=retain, hostname=s.mqtt_host, port=s.mqtt_port,
                   auth=auth, tls={} if s.mqtt_tls else None)
