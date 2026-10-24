"""Monday vault sync with mocked HTTP. Never calls monday.com."""

from __future__ import annotations

import json
import os
import sys
import tempfile
import unittest
from datetime import timedelta, timezone
from pathlib import Path
from unittest.mock import Mock, patch

import requests

_repo_root = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_repo_root / "Core"))

from modules import Monday_Sync as monday
from modules import Vault_Store as vs


def _operation(query: str) -> str:
    for name in (
        "next_items_page",
        "create_item",
        "move_item_to_group",
        "change_multiple_column_values",
        "change_simple_column_value",
        "items_page",
    ):
        if name in (query or ""):
            return name
    return "?"


def _iso(moment) -> str:
    return moment.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


class FakeBoard:
    """Stateful stand-in for api.monday.com/v2."""

    def __init__(self):
        self.items = {}
        self.calls = []
        self.fail = ""
        self._seq = 1

    def __call__(self, url, json=None, headers=None, timeout=None, **_kwargs):
        self.calls.append({"url": url, "json": json, "headers": headers, "timeout": timeout})
        if self.fail == "connect":
            raise requests.ConnectionError("network down")
        response_status = 429 if self.fail == "429" else 200
        response = Mock(status_code=response_status)
        if response_status != 200:
            response.json.return_value = {"errors": [{"message": "rate limit"}]}
            return response
        payload = json or {}
        query = payload.get("query") or ""
        variables = payload.get("variables") or {}
        op = _operation(query)
        if op == "items_page":
            body = {"data": {"boards": [{"items_page": {"cursor": None, "items": list(self.items.values())}}]}}
        elif op == "create_item":
            item_id = str(self._seq)
            self._seq += 1
            item = _item_from_values(
                item_id,
                variables.get("name") or "",
                variables.get("group") or "",
                variables.get("values") or "{}",
                "2026-10-24T18:00:00Z",
            )
            self.items[item_id] = item
            body = {"data": {"create_item": {"id": item_id, "updated_at": item["updated_at"]}}}
        elif op == "move_item_to_group":
            item = self.items[str(variables.get("item"))]
            item["group"] = {"id": variables.get("group")}
            item["updated_at"] = "2026-10-24T18:05:00Z"
            body = {"data": {"move_item_to_group": {"id": item["id"], "updated_at": item["updated_at"]}}}
        elif op == "change_multiple_column_values":
            item = self.items[str(variables.get("item"))]
            _apply_values(item, variables.get("values") or "{}")
            item["updated_at"] = "2026-10-24T18:06:00Z"
            body = {
                "data": {
                    "change_multiple_column_values": {"id": item["id"], "updated_at": item["updated_at"]}
                }
            }
        elif op == "change_simple_column_value":
            item = self.items[str(variables.get("item"))]
            item["name"] = variables.get("value") or item["name"]
            item["updated_at"] = "2026-10-24T18:07:00Z"
            body = {"data": {"change_simple_column_value": {"id": item["id"], "updated_at": item["updated_at"]}}}
        else:
            body = {"data": {}}
        response.json.return_value = body
        return response

    def operations(self):
        return [_operation((call.get("json") or {}).get("query") or "") for call in self.calls]

    def creates(self):
        found = []
        for call in self.calls:
            payload = call.get("json") or {}
            if _operation(payload.get("query") or "") != "create_item":
                continue
            variables = payload.get("variables") or {}
            found.append({**variables, "values": json.loads(variables.get("values") or "{}")})
        return found


def _column(column_id: str, text: str, value) -> dict:
    return {"id": column_id, "text": text, "value": json.dumps(value)}


def _item_from_values(item_id: str, name: str, group_id: str, values_json: str, updated_at: str) -> dict:
    item = {
        "id": str(item_id),
        "name": name,
        "updated_at": updated_at,
        "group": {"id": group_id},
        "column_values": [],
    }
    _apply_values(item, values_json)
    item["name"] = name
    item["group"] = {"id": group_id}
    item["updated_at"] = updated_at
    return item


def _apply_values(item: dict, values_json: str) -> None:
    values = json.loads(values_json) if isinstance(values_json, str) else values_json
    columns = {column["id"]: column for column in item.get("column_values") or []}
    status = values.get("status") or {}
    if "index" in status:
        label = {17: "To do", 0: "Working on it", 1: "Done"}.get(status["index"], "")
        columns["status"] = _column("status", label, status)
    if "area" in values:
        columns["area"] = _column("area", "", values["area"])
    if "type" in values:
        columns["type"] = _column("type", "", values["type"])
    if "vault_note" in values:
        columns["vault_note"] = _column("vault_note", str(values["vault_note"]), values["vault_note"])
    if "due" in values:
        due = (values["due"] or {}).get("date") or ""
        columns["due"] = _column("due", str(due or ""), values["due"])
    if "event_time" in values:
        columns["event_time"] = _column("event_time", "", values["event_time"])
    if "vault_link" in values:
        columns["vault_link"] = _column("vault_link", "", values["vault_link"])
    item["column_values"] = list(columns.values())


def _manual_item(
    item_id: str,
    name: str,
    group_id: str,
    updated_at: str,
    *,
    vault_note: str = "",
    status: str = "To do",
    status_index: int = 17,
    due: str = "",
    timeline=None,
    type_label: str = "Task",
    type_index: int = 3,
    area_label: str = "",
    area_index: int = 17,
) -> dict:
    return {
        "id": item_id,
        "name": name,
        "updated_at": updated_at,
        "group": {"id": group_id},
        "column_values": [
            _column("status", status, {"index": status_index}),
            _column("type", type_label, {"index": type_index}),
            _column("area", area_label, {"index": area_index}),
            _column("vault_note", vault_note, vault_note),
            _column("due", due, {"date": due} if due else {}),
            _column("event_time", "", timeline or {}),
        ],
    }


class MondayVaultCase(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name) / "Bolt Vault"
        self.root.mkdir()
        self.store = vs.VaultStore(self.root)
        self.store.ensure_scaffold()
        self._env = patch.dict(
            os.environ,
            {
                "MONDAY_API_TOKEN": "",
                "BOLT_VAULT_FILING_AI": "off",
                "BOLT_VAULT_PATH": str(self.root),
            },
        )
        self._env.start()
        os.environ.pop("MONDAY_SYNC", None)

    def tearDown(self):
        self._env.stop()
        self._tmp.cleanup()

    def token_on(self) -> None:
        os.environ["MONDAY_API_TOKEN"] = "test-token"


class PushUpsertTests(MondayVaultCase):
    def test_sync_creates_task_event_and_page_and_hook_moves_lane(self):
        task = self.store.add_note("Film the short", kind="task", status="doing")
        event = self.store.add_note(
            "Film night",
            kind="page",
            area="10 Bolt",
            folder_rel=vs.CALENDAR_REL,
            extra={
                "type": "event",
                "date": "2026-10-30",
                "allDay": False,
                "startTime": "19:00",
                "endTime": "20:00",
            },
        )
        page = self.store.add_note("Gear page", kind="page", area="30 Product Testing")
        board = FakeBoard()
        self.token_on()
        with patch("modules.Monday_Sync.requests.post", side_effect=board):
            result = monday.sync(store=self.store)
            self.store.update_frontmatter(task.rel, {"status": "done"}, summary="mark done")
        self.assertTrue(result["ok"], result)
        creates = {row["name"]: row for row in board.creates()}
        self.assertEqual(set(creates), {"Film the short", "Film night", "Gear page"})

        task_row = creates["Film the short"]
        self.assertEqual(task_row["group"], monday.BOARD["groups"]["Doing"])
        self.assertEqual(task_row["values"]["status"], {"index": 0})
        self.assertEqual(task_row["values"]["area"], {"index": 9})
        self.assertEqual(task_row["values"]["type"], {"index": 3})
        self.assertEqual(task_row["values"]["vault_note"], task.rel)
        self.assertIn("obsidian://open?vault=Bolt%20Vault&file=", task_row["values"]["vault_link"]["url"])
        self.assertIn("10%20Bolt%2FTasks%2F", task_row["values"]["vault_link"]["url"])

        event_row = creates["Film night"]
        self.assertEqual(event_row["values"]["type"], {"index": 11})
        self.assertEqual(
            event_row["values"]["event_time"],
            {"from": "2026-10-30 19:00:00", "to": "2026-10-30 20:00:00"},
        )
        self.assertEqual(event_row["values"]["vault_note"], event.rel)

        page_row = creates["Gear page"]
        self.assertEqual(page_row["values"]["type"], {"index": 8})
        self.assertEqual(page_row["values"]["area"], {"index": 1})
        self.assertEqual(page_row["values"]["vault_note"], page.rel)

        moves = [
            (call.get("json") or {}).get("variables") or {}
            for call in board.calls
            if _operation((call.get("json") or {}).get("query") or "") == "move_item_to_group"
        ]
        self.assertTrue(moves)
        self.assertEqual(moves[-1]["group"], monday.BOARD["groups"]["Done"])
        updates = [
            json.loads(((call.get("json") or {}).get("variables") or {}).get("values") or "{}")
            for call in board.calls
            if _operation((call.get("json") or {}).get("query") or "") == "change_multiple_column_values"
        ]
        self.assertTrue(any(row.get("status") == {"index": 1} and row.get("vault_note") == task.rel for row in updates))
        self.assertEqual(board.calls[0]["url"], monday.API_URL)
        self.assertEqual(board.calls[0]["headers"]["Authorization"], "test-token")

    def test_dry_run_does_not_write(self):
        note = self.store.add_note("Leave me", kind="task")
        before = (self.root / note.rel).read_text(encoding="utf-8")
        board = FakeBoard()
        self.token_on()
        with patch("modules.Monday_Sync.requests.post", side_effect=board):
            result = monday.sync(store=self.store, dry_run=True)
        self.assertTrue(result["dry_run"])
        self.assertEqual(result["pushed"][0]["action"], "would-create")
        self.assertEqual(board.operations(), ["items_page"])
        self.assertEqual((self.root / note.rel).read_text(encoding="utf-8"), before)
        self.assertFalse((self.root / ".bolt" / "monday_sync.json").exists())


class PullTests(MondayVaultCase):
    def test_pull_lane_move_updates_status_due_and_board(self):
        note = self.store.add_note("Film the short", kind="task", status="inbox")
        fresh = self.store.read_note(note.rel)
        monday.save_state(
            self.store,
            {
                "version": 1,
                "items": {
                    note.rel: {
                        "item_id": "42",
                        "fingerprint": monday.fingerprint(fresh),
                        "monday_updated_at": "2026-10-24T12:00:00Z",
                    }
                },
            },
        )
        board = FakeBoard()
        board.items["42"] = _manual_item(
            "42",
            "Film the short",
            monday.BOARD["groups"]["Doing"],
            "2026-10-24T18:00:00Z",
            vault_note=note.rel,
            status="Working on it",
            status_index=0,
            due="2026-10-30",
        )
        self.token_on()
        with patch("modules.Monday_Sync.requests.post", side_effect=board):
            result = monday.sync(store=self.store)
        self.assertTrue(result["ok"], result)
        self.assertEqual(result["pulled"][0]["lane"], "Doing")
        saved = self.store.read_note(note.rel)
        self.assertEqual(saved.frontmatter.get("status"), "doing")
        self.assertEqual(saved.frontmatter.get("due"), "2026-10-30")
        board_text = (self.root / vs.BOARD_REL).read_text(encoding="utf-8")
        doing = board_text.split("## Doing", 1)[1].split("## Done", 1)[0]
        inbox = board_text.split("## Inbox", 1)[1].split("## This Week", 1)[0]
        self.assertIn("[[Film the short]]", doing)
        self.assertNotIn("[[Film the short]]", inbox)
        self.assertNotIn("create_item", board.operations())

    def test_pull_event_time(self):
        note = self.store.add_note(
            "Film night",
            kind="page",
            area="10 Bolt",
            folder_rel=vs.CALENDAR_REL,
            extra={"type": "event", "date": "2026-10-30", "allDay": True},
        )
        fresh = self.store.read_note(note.rel)
        monday.save_state(
            self.store,
            {
                "version": 1,
                "items": {
                    note.rel: {
                        "item_id": "9",
                        "fingerprint": monday.fingerprint(fresh),
                        "monday_updated_at": "2026-10-24T12:00:00Z",
                    }
                },
            },
        )
        board = FakeBoard()
        board.items["9"] = _manual_item(
            "9",
            "Film night",
            monday.BOARD["groups"]["This Week"],
            "2026-10-24T19:00:00Z",
            vault_note=note.rel,
            status="To do",
            status_index=17,
            type_label="Event",
            type_index=11,
            timeline={"from": "2026-10-30 19:00:00", "to": "2026-10-30 20:00:00"},
        )
        self.token_on()
        with patch("modules.Monday_Sync.requests.post", side_effect=board):
            result = monday.sync(store=self.store)
        self.assertTrue(result["ok"], result)
        saved = self.store.read_note(note.rel)
        self.assertEqual(saved.frontmatter.get("date"), "2026-10-30")
        self.assertEqual(saved.frontmatter.get("startTime"), "19:00")
        self.assertEqual(saved.frontmatter.get("endTime"), "20:00")
        self.assertIs(saved.frontmatter.get("allDay"), False)
        self.assertEqual(saved.frontmatter.get("status"), "this-week")


class PhoneCreateTests(MondayVaultCase):
    def test_new_items_from_phone_land_in_inbox_or_smart_filing(self):
        board = FakeBoard()
        board.items["1"] = _manual_item(
            "1",
            "Call mom",
            monday.BOARD["groups"]["Inbox"],
            "2026-10-24T18:00:00Z",
            area_label="Inbox",
            area_index=17,
        )
        board.items["2"] = _manual_item(
            "2",
            "Product test the stand",
            monday.BOARD["groups"]["This Week"],
            "2026-10-24T18:00:00Z",
            status="To do",
            status_index=17,
            area_label="",
        )
        self.token_on()
        with patch("modules.Monday_Sync.requests.post", side_effect=board):
            result = monday.sync(store=self.store)
        self.assertTrue(result["ok"], result)
        created = {row["title"]: row for row in result["created"]}
        self.assertIn("Call mom", created)
        self.assertIn("Product test the stand", created)
        mom = self.store.read_note(created["Call mom"]["rel"])
        self.assertTrue(mom.rel.startswith("00 Inbox/"))
        self.assertEqual(mom.kind, "task")
        self.assertEqual(mom.frontmatter.get("status"), "inbox")
        product = self.store.read_note(created["Product test the stand"]["rel"])
        self.assertTrue(product.rel.startswith("30 Product Testing/"))
        self.assertEqual(product.frontmatter.get("status"), "this-week")
        linked = [
            json.loads(((call.get("json") or {}).get("variables") or {}).get("values") or "{}")
            for call in board.calls
            if _operation((call.get("json") or {}).get("query") or "") == "change_multiple_column_values"
        ]
        paths = {row.get("vault_note") for row in linked}
        self.assertIn(mom.rel, paths)
        self.assertIn(product.rel, paths)
        self.assertNotIn("create_item", board.operations())


class ConflictTests(MondayVaultCase):
    def _pair(self, monday_name: str, monday_time: str):
        note = self.store.add_note("From vault", kind="task", status="inbox")
        fresh = self.store.read_note(note.rel)
        monday.save_state(
            self.store,
            {
                "version": 1,
                "items": {
                    note.rel: {
                        "item_id": "7",
                        "fingerprint": "stale",
                        "monday_updated_at": "2020-01-01T00:00:00Z",
                    }
                },
            },
        )
        moment = monday.vault_clock(fresh.path)
        board = FakeBoard()
        stamp = _iso(moment) if monday_time == "tie" else _iso(moment + timedelta(hours=1))
        board.items["7"] = _manual_item(
            "7",
            monday_name,
            monday.BOARD["groups"]["Inbox"],
            stamp,
            vault_note=note.rel,
        )
        return note, board

    def test_vault_wins_a_tie(self):
        note, board = self._pair("From phone", "tie")
        self.token_on()
        with patch("modules.Monday_Sync.requests.post", side_effect=board):
            result = monday.sync(store=self.store)
        self.assertTrue(result["ok"], result)
        self.assertFalse(result["pulled"])
        self.assertEqual(self.store.read_note(note.rel).title, "From vault")
        renames = [
            ((call.get("json") or {}).get("variables") or {}).get("value")
            for call in board.calls
            if _operation((call.get("json") or {}).get("query") or "") == "change_simple_column_value"
        ]
        self.assertIn("From vault", renames)

    def test_newer_phone_edit_wins(self):
        note, board = self._pair("From phone", "newer")
        self.token_on()
        with patch("modules.Monday_Sync.requests.post", side_effect=board):
            result = monday.sync(store=self.store)
        self.assertTrue(result["ok"], result)
        self.assertEqual(result["pulled"][0]["title"], "From phone")
        saved = self.store.read_note(note.rel)
        self.assertEqual(saved.title, "From phone")
        self.assertIn("# From phone", saved.body)
        self.assertNotIn("change_simple_column_value", board.operations())


class OfflineTests(MondayVaultCase):
    def test_connection_error_and_rate_limit_leave_the_vault_alone(self):
        note = self.store.add_note("Stay put", kind="task")
        before = (self.root / note.rel).read_text(encoding="utf-8")
        self.token_on()
        for failure in ("connect", "429"):
            board = FakeBoard()
            board.fail = failure
            with patch("modules.Monday_Sync.requests.post", side_effect=board):
                result = monday.sync(store=self.store)
            self.assertFalse(result["ok"])
            self.assertIn("Monday unavailable:", result["error"])
            if failure == "429":
                self.assertIn("429", result["error"])
            self.assertEqual((self.root / note.rel).read_text(encoding="utf-8"), before)

    def test_hook_does_not_crash_when_monday_is_down(self):
        board = FakeBoard()
        board.fail = "connect"
        self.token_on()
        with patch("modules.Monday_Sync.requests.post", side_effect=board):
            note = self.store.add_note("Saved anyway", kind="task")
        self.assertTrue((self.root / note.rel).is_file())
        self.assertTrue(board.calls)

    def test_off_without_a_token(self):
        self.store.add_note("Local only", kind="task")
        with patch("modules.Monday_Sync.requests.post") as post:
            result = monday.sync(store=self.store)
        self.assertTrue(result["disabled"])
        self.assertEqual(post.call_count, 0)
        self.assertIn("MONDAY_API_TOKEN", result["message"])


class LaneRuleTests(unittest.TestCase):
    def test_group_and_status_map_onto_vault_lanes(self):
        groups = monday.BOARD["groups"]
        self.assertEqual(monday.lane_from_monday(groups["Doing"], "To do"), "Doing")
        self.assertEqual(monday.lane_from_monday(groups["This Week"], "Working on it"), "This Week")
        self.assertEqual(monday.lane_from_monday(groups["Inbox"], "Working on it"), "Doing")
        self.assertEqual(monday.lane_from_monday(groups["Inbox"], "Done"), "Done")
        self.assertEqual(monday.lane_from_monday(groups["Done"], "To do"), "Done")


class DisappearedCardTests(MondayVaultCase):
    def test_missing_monday_card_does_not_delete_the_note(self):
        note = self.store.add_note("Keep me", kind="task")
        fresh = self.store.read_note(note.rel)
        before = (self.root / note.rel).read_text(encoding="utf-8")
        monday.save_state(
            self.store,
            {
                "version": 1,
                "items": {
                    note.rel: {
                        "item_id": "99",
                        "fingerprint": monday.fingerprint(fresh),
                        "monday_updated_at": "2026-10-24T12:00:00Z",
                    }
                },
            },
        )
        board = FakeBoard()
        self.token_on()
        with patch("modules.Monday_Sync.requests.post", side_effect=board):
            result = monday.sync(store=self.store)
        self.assertTrue(result["ok"], result)
        self.assertEqual(result["kept"][0]["rel"], note.rel)
        self.assertEqual((self.root / note.rel).read_text(encoding="utf-8"), before)
        self.assertNotIn("create_item", board.operations())


if __name__ == "__main__":
    unittest.main()
