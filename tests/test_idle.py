from __future__ import annotations

import unittest

from switchdeck.idle import PeerState, should_prevent_sleep


class SleepDecisionTests(unittest.TestCase):
    def test_local_activity_prevents_sleep(self) -> None:
        self.assertTrue(should_prevent_sleep(5, 600, [], now=1000))

    def test_recent_active_peer_prevents_sleep(self) -> None:
        peers = [PeerState(active=True, received_at=998)]
        self.assertTrue(should_prevent_sleep(700, 600, peers, now=1000))

    def test_both_idle_allow_sleep(self) -> None:
        peers = [PeerState(active=False, received_at=998)]
        self.assertFalse(should_prevent_sleep(700, 600, peers, now=1000))

    def test_stale_peer_does_not_prevent_sleep(self) -> None:
        peers = [PeerState(active=True, received_at=900)]
        self.assertFalse(should_prevent_sleep(700, 600, peers, now=1000))


if __name__ == "__main__":
    unittest.main()
