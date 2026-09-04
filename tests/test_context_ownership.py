"""B1 Context Ownership integration tests."""

from __future__ import annotations

import tempfile
import os
import pytest
import httpx
import json

from local2api.main import create_app
from local2api.context_store import ContextStore, CanonicalContext
from local2api.context_reconstruct import (
    reconstruct_context,
    update_canonical_context,
    extract_hard_constraints,
    extract_artifacts,
    extract_decisions,
)
from tests.fakes import FakeBackend


@pytest.fixture
def temp_db():
    """Create a temporary database for testing."""
    with tempfile.NamedTemporaryFile(suffix='.db', delete=False) as f:
        db_path = f.name
    yield db_path
    # Cleanup
    try:
        os.unlink(db_path)
    except PermissionError:
        pass  # Windows file locking


@pytest.fixture
async def client_with_context():
    """Create test client with context store."""
    app = create_app()
    local = FakeBackend("local")
    cloud = FakeBackend("cloud")
    app.state.backends = {"local": local, "cloud": cloud}
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        yield client, local, cloud


class TestContextStore:
    """Test the context store persistence."""

    def test_create_and_load_conversation(self, temp_db):
        store = ContextStore(temp_db)
        ctx = store.create_conversation(
            system_instructions=["You are a coding assistant"],
            task_goal="Refactor the auth module",
        )
        assert ctx.conversation_id is not None
        assert ctx.system_instructions == ["You are a coding assistant"]
        assert ctx.task_goal == "Refactor the auth module"
        assert ctx.turn_count == 0

        # Load it back
        loaded = store.get_conversation(ctx.conversation_id)
        assert loaded is not None
        assert loaded.conversation_id == ctx.conversation_id
        assert loaded.system_instructions == ["You are a coding assistant"]
        assert loaded.task_goal == "Refactor the auth module"

    def test_update_conversation(self, temp_db):
        store = ContextStore(temp_db)
        ctx = store.create_conversation()
        original_id = ctx.conversation_id

        # Add a turn
        ctx.recent_turns.append({
            "turn_id": "turn-1",
            "user": "rewrite this function",
            "assistant": "Here's the rewritten function...",
            "backend": "local",
        })

        store.update_conversation(ctx, turn_count=1)

        # Reload
        loaded = store.get_conversation(original_id)
        assert loaded is not None
        assert len(loaded.recent_turns) == 1
        assert loaded.recent_turns[0]["user"] == "rewrite this function"

    def test_delete_conversation(self, temp_db):
        store = ContextStore(temp_db)
        ctx = store.create_conversation()
        assert store.get_conversation(ctx.conversation_id) is not None

        deleted = store.delete_conversation(ctx.conversation_id)
        assert deleted is True
        assert store.get_conversation(ctx.conversation_id) is None

        # Deleting non-existent returns False
        deleted = store.delete_conversation("non-existent")
        assert deleted is False

    def test_list_conversations(self, temp_db):
        store = ContextStore(temp_db)
        for i in range(3):
            ctx = store.create_conversation()
            ctx.recent_turns.append({"turn_id": f"turn-{i}", "user": f"msg-{i}", "assistant": f"resp-{i}", "backend": "local"})
            store.update_conversation(ctx, turn_count=1)

        conversations = store.list_conversations(limit=10)
        assert len(conversations) == 3
        # Should be ordered by updated_at DESC (most recent first)
        assert conversations[0].turn_count == 1


class TestContextReconstruction:
    """Test context reconstruction pipeline."""

    def test_reconstruct_with_system_instructions(self, temp_db):
        store = ContextStore(temp_db)
        ctx = store.create_conversation(
            system_instructions=["You are a helpful assistant"],
            task_goal="Refactor the auth module",
            hard_constraints=["Do not modify file X", "Must preserve API compatibility"],
        )

        result = reconstruct_context(
            canonical_context=ctx,
            incoming_turn={"role": "user", "content": "Continue the refactor"},
            token_budget=4096,
            backend_name="local",
        )

        assert len(result.messages) >= 3  # system + task goal + constraints + incoming
        assert any(m["role"] == "system" for m in result.messages)
        assert result.estimated_tokens > 0
        assert result.compacted is False

    def test_reconstruct_respects_token_budget(self, temp_db):
        store = ContextStore(temp_db)
        ctx = store.create_conversation(
            system_instructions=["x" * 5000],  # Large system instruction
        )

        result = reconstruct_context(
            canonical_context=ctx,
            incoming_turn={"role": "user", "content": "test"},
            token_budget=100,  # Very small budget
            backend_name="local",
        )

        # Should fit within budget
        assert result.estimated_tokens <= 150  # Some overhead allowed

    def test_reconstruct_priority_order(self, temp_db):
        store = ContextStore(temp_db)
        ctx = store.create_conversation(
            system_instructions=["System instruction"],
            task_goal="Task goal",
            hard_constraints=["Constraint 1", "Constraint 2"],
            decisions=[{"type": "selection", "content": "use Ollama"}],
            artifacts=[{"type": "file", "path": "src/foo.py", "summary": "Main entry"}],
        )

        result = reconstruct_context(
            canonical_context=ctx,
            incoming_turn={"role": "user", "content": "new message"},
            token_budget=4096,
            backend_name="local",
        )

        # System messages should come first
        system_msgs = [m for m in result.messages if m["role"] == "system"]
        assert len(system_msgs) >= 4  # system + task + constraints + decisions/artifacts

        # Check content presence
        full_text = " ".join(m["content"] for m in result.messages)
        assert "System instruction" in full_text
        assert "Task goal" in full_text
        assert "Constraint 1" in full_text
        assert "Constraint 2" in full_text

    def test_reconstruct_with_recent_turns(self, temp_db):
        store = ContextStore(temp_db)
        ctx = store.create_conversation()
        ctx.recent_turns = [
            {"turn_id": "1", "user": "first message", "assistant": "first response", "backend": "local"},
            {"turn_id": "2", "user": "second message", "assistant": "second response", "backend": "local"},
            {"turn_id": "3", "user": "third message", "assistant": "third response", "backend": "cloud"},
        ]

        result = reconstruct_context(
            canonical_context=ctx,
            incoming_turn={"role": "user", "content": "fourth message"},
            token_budget=4096,
            backend_name="local",
        )

        # Should include recent conversation history
        full_text = " ".join(m["content"] for m in result.messages)
        assert "first message" in full_text
        assert "first response" in full_text
        assert "second message" in full_text
        assert "fourth message" in full_text

    def test_compaction_when_budget_exceeded(self, temp_db):
        store = ContextStore(temp_db)
        ctx = store.create_conversation()
        # Create many turns that exceed budget - use very long messages
        ctx.recent_turns = [
            {"turn_id": str(i), "user": "x" * 500, "assistant": "y" * 500, "backend": "local"}
            for i in range(20)
        ]

        result = reconstruct_context(
            canonical_context=ctx,
            incoming_turn={"role": "user", "content": "new message"},
            token_budget=30,  # Extremely small budget - should force compaction
            backend_name="local",
        )

        # With such a small budget, even system messages won't fit all turns
        assert result.compacted is True
        assert result.compacted_turns > 0
        assert result.estimated_tokens <= 100  # Should stay near budget


class TestExtractionFunctions:
    """Test extraction functions for constraints, artifacts, decisions."""

    def test_extract_hard_constraints(self):
        text = "Do not modify file X. Must preserve API compatibility. Only edit tests. Avoid changing schema."
        constraints = extract_hard_constraints(text)
        assert "modify file X" in constraints
        assert "preserve API compatibility" in constraints
        assert "edit tests" in constraints
        assert "changing schema" in constraints

    def test_extract_artifacts(self):
        text = "The file: src/foo.py has a bug in function process_data. Also check path: utils/helper.js."
        artifacts = extract_artifacts(text)
        assert any(a["type"] == "file" and a["path"] == "src/foo.py" for a in artifacts)
        assert any(a["type"] == "function" and a["name"] == "process_data" for a in artifacts)
        assert any(a["type"] == "file" and a["path"] == "utils/helper.js" for a in artifacts)

    def test_extract_decisions(self):
        text = "We decided to use Ollama. The dense 32B is blocked. We prefer the 14B model."
        decisions = extract_decisions(text)
        assert any(d["type"] == "selection" and "Ollama" in d["content"] for d in decisions)
        assert any(d["type"] == "blocker" and "blocked" in d["content"] for d in decisions)
        assert any(d["type"] == "preference" and "14B" in d["content"] for d in decisions)


class TestUpdateCanonicalContext:
    """Test updating canonical context with new turns."""

    def test_update_adds_turn(self, temp_db):
        store = ContextStore(temp_db)
        ctx = store.create_conversation()

        updated = update_canonical_context(
            canonical_context=ctx,
            user_message={"role": "user", "content": "Do not modify file X. Rewrite the auth module."},
            assistant_response={"role": "assistant", "content": "I'll rewrite the auth module without modifying file X."},
            backend_used="local",
            routing_decision={"reason": "local_task:rewrite", "fallback_mode": "none"},
        )

        assert len(updated.recent_turns) == 1
        turn = updated.recent_turns[0]
        assert turn["user"] == "Do not modify file X. Rewrite the auth module."
        assert turn["assistant"] == "I'll rewrite the auth module without modifying file X."
        assert turn["backend"] == "local"

    def test_update_extracts_constraints(self, temp_db):
        store = ContextStore(temp_db)
        ctx = store.create_conversation()

        updated = update_canonical_context(
            canonical_context=ctx,
            user_message={"role": "user", "content": "Do not modify file X. Must preserve API compatibility."},
            assistant_response={"role": "assistant", "content": "Understood."},
            backend_used="local",
            routing_decision={"reason": "local_task:rewrite", "fallback_mode": "none"},
        )

        assert "modify file X" in updated.hard_constraints
        assert "preserve API compatibility" in updated.hard_constraints

    def test_update_extracts_artifacts(self, temp_db):
        store = ContextStore(temp_db)
        ctx = store.create_conversation()

        updated = update_canonical_context(
            canonical_context=ctx,
            user_message={"role": "user", "content": "Check file src/auth.py for bugs in function validate_token."},
            assistant_response={"role": "assistant", "content": "Found issue in validate_token."},
            backend_used="local",
            routing_decision={"reason": "local_task:rewrite", "fallback_mode": "none"},
        )

        assert any(a["type"] == "file" and a["path"] == "src/auth.py" for a in updated.artifacts)
        assert any(a["type"] == "function" and a["name"] == "validate_token" for a in updated.artifacts)

    def test_update_extracts_decisions(self, temp_db):
        store = ContextStore(temp_db)
        ctx = store.create_conversation()

        updated = update_canonical_context(
            canonical_context=ctx,
            user_message={"role": "user", "content": "We decided to use the 14B model. The 32B is blocked."},
            assistant_response={"role": "assistant", "content": "Understood, using 14B."},
            backend_used="local",
            routing_decision={"reason": "local_task:rewrite", "fallback_mode": "none"},
        )

        assert any(d["type"] == "selection" and "14B" in d["content"] for d in updated.decisions)
        assert any(d["type"] == "blocker" and "blocked" in d["content"] for d in updated.decisions)

    def test_update_records_backend_history(self, temp_db):
        store = ContextStore(temp_db)
        ctx = store.create_conversation()

        updated = update_canonical_context(
            canonical_context=ctx,
            user_message={"role": "user", "content": "test"},
            assistant_response={"role": "assistant", "content": "response"},
            backend_used="cloud",
            routing_decision={"reason": "complex_task:architecture", "fallback_mode": "safe"},
        )

        assert len(updated.backend_history) == 1
        assert updated.backend_history[0]["backend"] == "cloud"
        assert updated.backend_history[0]["reason"] == "complex_task:architecture"
        assert updated.backend_history[0]["fallback_mode"] == "safe"


class TestBackendSwitching:
    """Test that context works across backend switches."""

    @pytest.mark.asyncio
    async def test_context_survives_backend_switch(self, client_with_context):
        client, local, cloud = client_with_context

        # Turn 1 - Explicit local
        response1 = await client.post(
            "/v1/chat/completions",
            json={
                "model": "local",
                "messages": [{"role": "user", "content": "My task goal: refactor auth module"}],
            },
        )
        assert response1.status_code == 200
        conv_id = response1.headers["X-Local2API-Conversation-ID"]
        assert response1.headers["X-Local2API-Backend"] == "local"

        # Turn 2 - Explicit cloud (pass conversation ID in header)
        response2 = await client.post(
            "/v1/chat/completions",
            json={
                "model": "cloud",
                "messages": [
                    {"role": "user", "content": "My task goal: refactor auth module"},
                    {"role": "assistant", "content": "OK, I'll help refactor the auth module."},
                    {"role": "user", "content": "Do not modify file X"},
                ],
            },
            headers={"X-Local2API-Conversation-ID": conv_id},
        )
        assert response2.status_code == 200
        assert response2.headers["X-Local2API-Conversation-ID"] == conv_id
        assert response2.headers["X-Local2API-Backend"] == "cloud"

        # Turn 3 - Explicit local again (pass conversation ID in header)
        response3 = await client.post(
            "/v1/chat/completions",
            json={
                "model": "local",
                "messages": [
                    {"role": "user", "content": "My task goal: refactor auth module"},
                    {"role": "assistant", "content": "OK, I'll help refactor the auth module."},
                    {"role": "user", "content": "Do not modify file X"},
                    {"role": "assistant", "content": "Understood."},
                    {"role": "user", "content": "Now rewrite the login function"},
                ],
            },
            headers={"X-Local2API-Conversation-ID": conv_id},
        )
        assert response3.status_code == 200
        assert response3.headers["X-Local2API-Conversation-ID"] == conv_id
        assert response3.headers["X-Local2API-Backend"] == "local"


class TestRestartPersistence:
    """Test that context survives gateway restart."""

    def test_gateway_restart_persists_context(self, temp_db):
        """Simulate gateway restart by creating new store instance."""
        # First "session"
        store1 = ContextStore(temp_db)
        ctx1 = store1.create_conversation(task_goal="Test persistence")
        ctx1.recent_turns.append({
            "turn_id": "1", "user": "Hello", "assistant": "Hi", "backend": "local"
        })
        store1.update_conversation(ctx1, turn_count=1)
        conv_id = ctx1.conversation_id

        # Simulate restart - new store instance
        store2 = ContextStore(temp_db)
        loaded = store2.get_conversation(conv_id)

        assert loaded is not None
        assert loaded.task_goal == "Test persistence"
        assert len(loaded.recent_turns) == 1
        assert loaded.recent_turns[0]["user"] == "Hello"


class TestIsolation:
    """Test conversation isolation."""

    def test_conversation_isolation(self, temp_db):
        store = ContextStore(temp_db)
        ctx_a = store.create_conversation(task_goal="Task A")
        ctx_b = store.create_conversation(task_goal="Task B")

        ctx_a.recent_turns.append({"turn_id": "1", "user": "A message", "assistant": "A response", "backend": "local"})
        ctx_b.recent_turns.append({"turn_id": "1", "user": "B message", "assistant": "B response", "backend": "local"})

        store.update_conversation(ctx_a, turn_count=1)
        store.update_conversation(ctx_b, turn_count=1)

        loaded_a = store.get_conversation(ctx_a.conversation_id)
        loaded_b = store.get_conversation(ctx_b.conversation_id)

        assert loaded_a.task_goal == "Task A"
        assert loaded_b.task_goal == "Task B"
        assert loaded_a.recent_turns[0]["user"] == "A message"
        assert loaded_b.recent_turns[0]["user"] == "B message"
        assert loaded_a.conversation_id != loaded_b.conversation_id


class TestStreamingState:
    """Test streaming state semantics."""

    @pytest.mark.asyncio
    async def test_stream_commits_on_complete(self, client_with_context):
        client, local, cloud = client_with_context
        local.fail = False

        async with client.stream(
            "POST",
            "/v1/chat/completions",
            json={"stream": True, "messages": [{"role": "user", "content": "stream test"}]},
        ) as response:
            body = b"".join([chunk async for chunk in response.aiter_bytes()])

        assert response.status_code == 200
        assert b"[DONE]" in body
        conv_id = response.headers["X-Local2API-Conversation-ID"]

        # Verify context was persisted
        store: ContextStore = client._transport.app.state.context_store
        loaded = store.get_conversation(conv_id)
        assert loaded is not None
        assert len(loaded.recent_turns) == 1

    @pytest.mark.asyncio
    async def test_stream_does_not_commit_on_error(self, client_with_context):
        client, local, cloud = client_with_context
        local.fail = True

        async with client.stream(
            "POST",
            "/v1/chat/completions",
            json={"stream": True, "messages": [{"role": "user", "content": "stream test"}]},
        ) as response:
            body = b"".join([chunk async for chunk in response.aiter_bytes()])

        # Should get error event and [DONE]
        assert b"backend_unavailable" in body
        assert b"[DONE]" in body
        conv_id = response.headers["X-Local2API-Conversation-ID"]

        # Context should exist but no assistant turn committed
        store: ContextStore = client._transport.app.state.context_store
        loaded = store.get_conversation(conv_id)
        assert loaded is not None
        # User turn was recorded but no assistant response
        assert len(loaded.recent_turns) == 1
        # The assistant field should be empty for failed streams
        assert loaded.recent_turns[0]["assistant"] == ""


if __name__ == "__main__":
    pytest.main([__file__, "-v"])