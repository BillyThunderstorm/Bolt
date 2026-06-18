import unittest
from unittest.mock import patch

from modules import Bolt_Chat as chat


class BoltChatLocalCommandTests(unittest.TestCase):
    def test_format_queue_status_is_twitch_sized(self):
        with patch(
            "modules.Post_Queue.get_summary",
            return_value={
                "ready": 2,
                "ready_total": 3,
                "posted": 4,
                "missing": 1,
                "below_floor": 0,
            },
        ):
            status = chat.format_queue_status()

        self.assertIn("2 alertable", status)
        self.assertIn("3 ready total", status)

    def test_local_memory_recall_uses_local_index(self):
        with patch(
            "modules.Memory_Index.retrieve_memory",
            return_value=[
                {
                    "title": "Clip performance",
                    "source": "data/performance_outcomes.jsonl",
                    "summary": "Marvel Rivals clips did well with honest titles.",
                }
            ],
        ):
            answer = chat.local_memory_recall("Marvel Rivals titles")

        self.assertIn("Clip performance", answer)
        self.assertIn("honest titles", answer)

    def test_local_memory_recall_handles_empty_query(self):
        self.assertIn("!recall", chat.local_memory_recall(""))


if __name__ == "__main__":
    unittest.main()
