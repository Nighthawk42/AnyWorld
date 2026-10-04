"""Contracts and behavior for player commands and pinned memory."""

import asyncio

from core.schemas import ClientPayload
from logic.engine import GameEngine
from logic.llm_manager import LLMContextManager
from logic.models import GameState, Player
from support import FakeResolver, FakeSender
from test_priority_one_llm import FakeClient


def test_remember_fact_adds_to_fixed_context():
    """Pinned facts are placed into fixed LLM messages and cleared on new genesis."""
    client = FakeClient()
    manager = LLMContextManager(client)
    manager.set_genesis("You are in a dark forest.")

    assert len(manager.pinned_facts) == 0
    assert not any("Authoritative Pinned Facts" in m["content"] for m in manager._fixed_messages())

    manager.add_pinned_fact("The party found an obsidian key in the tree hollow.")
    assert len(manager.pinned_facts) == 1

    fixed = manager._fixed_messages("round")
    pinned_messages = [m for m in fixed if "Authoritative Pinned Facts" in m["content"]]
    assert len(pinned_messages) == 1
    assert "obsidian key" in pinned_messages[0]["content"]

    # Deduplication
    manager.add_pinned_fact("The party found an obsidian key in the tree hollow.")
    assert len(manager.pinned_facts) == 1

    # Reset on genesis
    manager.set_genesis("A new adventure begins.")
    assert len(manager.pinned_facts) == 0


def test_engine_remember_requires_auth_and_broadcasts_system_msg():
    """Remember event checks connected player auth and broadcasts system message."""

    async def run():
        sender = FakeSender()
        resolver = FakeResolver()
        engine = GameEngine(sender, resolver)

        # Unauthenticated client fails
        await engine.process_payload(
            "unauth-client",
            ClientPayload(event_type="remember", data={"fact": "A secret passage."}),
        )
        error_msg = sender.events_of_type("error")[-1].payload["msg"]
        assert "Authenticate before recording memory" in error_msg

        # Connect a player
        player = Player(client_id="p1", name="Gandalf", is_host=True)
        engine.players["p1"] = player
        engine.state = GameState.ACTIVE_TURN

        await engine.process_payload(
            "p1",
            ClientPayload(event_type="remember", data={"fact": "The sword glows blue near orcs."}),
        )

        assert resolver.pinned_facts == ["The sword glows blue near orcs."]
        system_events = sender.events_of_type("system_msg")
        assert len(system_events) == 1
        assert "The sword glows blue near orcs." in system_events[0].payload["msg"]
        assert "Gandalf" in system_events[0].payload["msg"]

    asyncio.run(run())


def test_engine_remember_fails_when_game_ended():
    """Cannot pin memory when the game has already ended."""

    async def run():
        sender = FakeSender()
        resolver = FakeResolver()
        engine = GameEngine(sender, resolver)
        player = Player(client_id="p1", name="Frodo", is_host=True)
        engine.players["p1"] = player
        engine.state = GameState.ENDED

        await engine.process_payload(
            "p1",
            ClientPayload(event_type="remember", data={"fact": "Mount Doom is destroyed."}),
        )
        error_msg = sender.events_of_type("error")[-1].payload["msg"]
        assert "Cannot pin memories after the game has ended" in error_msg

    asyncio.run(run())
