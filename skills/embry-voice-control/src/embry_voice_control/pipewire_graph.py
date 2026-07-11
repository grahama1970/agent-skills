"""PipeWire graph parsing for explicit Embry playback authority."""

from __future__ import annotations

from collections import deque
from typing import Any


def props(item: dict[str, Any]) -> dict[str, Any]:
    return item.get("info", {}).get("props", {})


def resolve_sink(
    dump: list[dict[str, Any]], *, node_name: str, description: str
) -> dict[str, Any]:
    """Resolve exactly one named Jabra audio sink."""
    matches = [
        item for item in dump
        if item.get("type") == "PipeWire:Interface:Node"
        and props(item).get("node.name") == node_name
        and props(item).get("media.class") == "Audio/Sink"
        and props(item).get("node.description") == description
    ]
    if len(matches) != 1:
        raise ValueError("sink_not_one_exact_match")
    return matches[0]


def _active_links(dump: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        item for item in dump
        if item.get("type") == "PipeWire:Interface:Link"
        and item.get("info", {}).get("state") == "active"
    ]


def observe_route(
    dump: list[dict[str, Any]], *, stream_node_name: str, child_pid: int, sink_node_name: str
) -> dict[str, Any] | None:
    """Return a running stream-to-sink route observation, allowing converters."""
    nodes = {item["id"]: item for item in dump if item.get("type") == "PipeWire:Interface:Node"}
    clients = {item["id"]: item for item in dump if item.get("type") == "PipeWire:Interface:Client"}
    streams = []
    for item in nodes.values():
        node_props = props(item)
        client = clients.get(node_props.get("client.id"), {})
        process_id = props(client).get("application.process.id")
        if (
            node_props.get("node.name") == stream_node_name
            and str(process_id) == str(child_pid)
            and item.get("info", {}).get("state") == "running"
        ):
            streams.append(item)
    sinks = [item for item in nodes.values() if props(item).get("node.name") == sink_node_name]
    if len(streams) != 1 or len(sinks) != 1:
        return None
    start, target = streams[0]["id"], sinks[0]["id"]
    adjacency: dict[int, list[tuple[int, int]]] = {}
    for link in _active_links(dump):
        link_props = props(link)
        source = link_props.get("link.output.node")
        destination = link_props.get("link.input.node")
        if isinstance(source, int) and isinstance(destination, int):
            adjacency.setdefault(source, []).append((destination, link["id"]))
    queue = deque([(start, [start], [])])
    seen = {start}
    while queue:
        current, node_path, link_path = queue.popleft()
        if current == target:
            return {
                "stream_node_id": start,
                "stream_object_serial": props(streams[0]).get("object.serial"),
                "stream_state": "running",
                "target_object": sink_node_name,
                "active_link_path": node_path,
                "active_link_ids": link_path,
            }
        for destination, link_id in adjacency.get(current, []):
            if destination not in seen:
                seen.add(destination)
                queue.append((destination, [*node_path, destination], [*link_path, link_id]))
    return None
