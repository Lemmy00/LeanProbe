from lean_probe.mcp_server import MCP_SERVER_NAME, TOOL_NAMES, create_server


def test_mcp_public_names_are_stable():
    assert MCP_SERVER_NAME == "lean-probe"
    assert TOOL_NAMES == [
        "lean_probe_prepare",
        "lean_probe_check",
        "lean_probe_feedback",
        "lean_probe_state",
        "lean_probe_step",
    ]


def test_mcp_server_constructs():
    server = create_server()
    assert server is not None
