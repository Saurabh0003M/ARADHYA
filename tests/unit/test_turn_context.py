import re
from pathlib import Path

from src.aradhya.tools.runtime_policy import ToolRuntimePolicy
from src.aradhya.turn_context import TurnContext, _generate_turn_id, build_turn_context


def test_generate_turn_id():
    """Test that turn IDs are generated in the correct format."""
    turn_id = _generate_turn_id()
    assert isinstance(turn_id, str)
    assert turn_id.startswith("turn_")
    # Prefix length is 5, plus 12 hex chars = 17 total length
    assert len(turn_id) == 17
    # Ensure remaining characters are hex digits
    assert re.match(r"^turn_[a-f0-9]{12}$", turn_id)


def test_turn_context_to_dict():
    """Test that TurnContext serializes to a dict correctly."""
    context = TurnContext(
        turn_id="turn_12345",
        session_id="session_abc",
        cwd="/tmp/test",
        timestamp="2023-10-27T10:00:00+00:00",
        timezone="UTC",
        execution_policy="live",
        permission_profile={"network": "restricted"},
    )

    expected_dict = {
        "turn_id": "turn_12345",
        "session_id": "session_abc",
        "cwd": "/tmp/test",
        "timestamp": "2023-10-27T10:00:00+00:00",
        "timezone": "UTC",
        "execution_policy": "live",
        "permission_profile": {"network": "restricted"},
    }

    assert context.to_dict() == expected_dict


def test_turn_context_to_prompt_block_minimal():
    """Test to_prompt_block output without read/write roots."""
    context = TurnContext(
        turn_id="turn_12345",
        session_id="session_abc",
        cwd="/tmp/test",
        timestamp="2023-10-27T10:00:00+00:00",
        timezone="UTC",
        execution_policy="dry-run",
        permission_profile={},
    )

    block = context.to_prompt_block()

    assert "[Turn Context]" in block
    assert "Turn: turn_12345" in block
    assert "Session: session_abc" in block
    assert "Time: 2023-10-27T10:00:00+00:00 (UTC)" in block
    assert "CWD: /tmp/test" in block
    assert "Execution policy: dry-run" in block
    assert "Read access:" not in block
    assert "Write access:" not in block
    assert "Network: restricted" in block  # Defaults to restricted


def test_turn_context_to_prompt_block_with_roots():
    """Test to_prompt_block output with read/write roots and custom network."""
    context = TurnContext(
        turn_id="turn_12345",
        session_id="session_abc",
        cwd="/tmp/test",
        timestamp="2023-10-27T10:00:00+00:00",
        timezone="UTC",
        execution_policy="live",
        permission_profile={
            "read_roots": ["/tmp/read1", "/tmp/read2"],
            "write_roots": ["/tmp/write1"],
            "network": "allowed",
        },
    )

    block = context.to_prompt_block()

    assert "Read access: /tmp/read1, /tmp/read2" in block
    assert "Write access: /tmp/write1" in block
    assert "Network: allowed" in block


def test_build_turn_context_live_execution():
    """Test build_turn_context when execution is live and mutation is granted."""
    policy = ToolRuntimePolicy(
        live_execution_enabled=True,
        mutation_granted=True,
        allowed_roots=(Path("/tmp/allowed"),)
    )

    context = build_turn_context(policy, session_id="sess_live")

    assert context.session_id == "sess_live"
    assert context.execution_policy == "live"
    assert isinstance(context.turn_id, str)
    assert context.turn_id.startswith("turn_")

    # Verify permission profile includes paths
    assert "read_roots" in context.permission_profile
    assert str(Path("/tmp/allowed")) in context.permission_profile["read_roots"]


def test_build_turn_context_pending_confirmation():
    """Test build_turn_context when execution is live but mutation is not granted yet."""
    policy = ToolRuntimePolicy(
        live_execution_enabled=True,
        mutation_granted=False,
    )

    context = build_turn_context(policy, session_id="sess_pending")

    assert context.execution_policy == "live (pending task confirmation)"


def test_build_turn_context_dry_run():
    """Test build_turn_context when execution is not live."""
    policy = ToolRuntimePolicy(
        live_execution_enabled=False,
        mutation_granted=False,
    )

    context = build_turn_context(policy, session_id="sess_dry")

    assert context.execution_policy == "dry-run"


def test_build_turn_context_explicit_turn_id():
    """Test build_turn_context handles explicit turn_id properly."""
    policy = ToolRuntimePolicy()

    context = build_turn_context(policy, session_id="sess_id", turn_id="custom_turn_id")

    assert context.turn_id == "custom_turn_id"


def test_build_turn_context_cwd_and_timestamp():
    """Test that build_turn_context captures cwd and timestamp."""
    policy = ToolRuntimePolicy()

    context = build_turn_context(policy)

    # cwd should match current working directory
    assert context.cwd == str(Path.cwd())
    # Timestamp should be ISO 8601 string
    assert "T" in context.timestamp
    # Timezone should be a string (e.g., UTC, PST, etc.)
    assert isinstance(context.timezone, str)
    assert len(context.timezone) > 0
