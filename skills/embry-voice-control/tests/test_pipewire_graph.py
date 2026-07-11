from embry_voice_control.pipewire_graph import observe_route, resolve_sink


def node(identifier, name, *, media_class=None, description=None, state="running", pid=None):
    values = {"node.name": name, "object.serial": identifier + 100}
    if media_class: values["media.class"] = media_class
    if description: values["node.description"] = description
    if pid: values["client.id"] = identifier + 50
    return {"id": identifier, "type": "PipeWire:Interface:Node", "info": {"state": state, "props": values}}


def client(identifier, pid):
    return {"id": identifier, "type": "PipeWire:Interface:Client", "info": {"props": {"application.process.id": pid}}}


def link(identifier, source, destination, state="active"):
    return {"id": identifier, "type": "PipeWire:Interface:Link", "info": {"state": state, "props": {"link.output.node": source, "link.input.node": destination}}}


def test_exact_sink_and_direct_route():
    dump = [node(1, "embry.playback.x", pid=44), client(51, 44), node(2, "jabra", media_class="Audio/Sink", description="Jabra"), link(3, 1, 2)]
    assert resolve_sink(dump, node_name="jabra", description="Jabra")["id"] == 2
    assert observe_route(dump, stream_node_name="embry.playback.x", child_pid=44, sink_node_name="jabra")["active_link_ids"] == [3]


def test_wrong_sink_and_nonrunning_stream_fail_closed():
    dump = [node(1, "embry.playback.x", state="idle", pid=44), client(51, 44), node(2, "other", media_class="Audio/Sink", description="Other"), link(3, 1, 2)]
    assert observe_route(dump, stream_node_name="embry.playback.x", child_pid=44, sink_node_name="jabra") is None
