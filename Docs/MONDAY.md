# Monday on your phone

Bolt keeps your tasks, events, and pages in the Obsidian vault. That vault is the copy that matters. Monday is a second view of the same list, so you can open it on your phone, move a card, change a due date, or jot a new task.

The Monday board is already there: [Bolt board](https://billycarterivs-team-squad.monday.com/boards/18436882096).

Sync stays **off** until you add a token. If Monday is down, or it asks Bolt to slow down, Bolt logs that and keeps working. It will not delete a vault note because a Monday card is missing.

## Turn it on

1. Open [monday.com](https://monday.com) and sign in.
2. Click your avatar in the top right.
3. Click **Developers**.
4. Copy the API token.
5. In Bolt's `.env` file (copy `.env.example` if you do not have one yet), add:

```bash
MONDAY_API_TOKEN=paste-the-token-here
MONDAY_BOARD_ID=18436882096
MONDAY_SYNC_INTERVAL=300
```

`300` is how many seconds Bolt waits between phone checks. Five minutes is the default.

6. From the Bolt folder, run:

```bash
bolt monday sync
```

The first run sends the board tasks and calendar events (and pages Bolt knows about) to Monday. After that, saving a task in Bolt updates the matching Monday card on its own.

## Day to day

| What you do | What happens |
|---|---|
| Add or move a task in Bolt | The Monday card is created or moved. Inbox, This Week, Doing, and Done match the vault board. |
| Edit a card on your phone | The next sync moves the vault card, updates the due date or event time, or renames the note. |
| Add a card on your phone | Bolt makes a new task. It lands in `00 Inbox`, or in another area when Bolt already knows where that kind of note goes. |
| Add an event on your phone | Bolt puts it in `10 Bolt/Calendar`. |
| Delete a Monday card | Bolt leaves the vault note where it is and writes a note in the log. |

If the vault and the phone both changed, the later edit wins. If they changed at the same moment, the vault wins.

## Commands

```bash
bolt monday                 # is sync on?
bolt monday sync           # push and pull once
bolt monday sync --dry-run # show what would change, then change nothing
bolt monday watch          # keep checking until you press Ctrl+C
```

You do not have to leave `watch` running. While Bolt is live (`bolt launch`), it checks the phone on that same timer when the token is set. The 5 PM briefing also does one pass. On your Mac, `bolt mac-auto install cron` can add a repeating check, and it only offers that line after the token is in `.env`.

## Where the columns come from

Bolt fills these for you. You should not have to type paths on the phone.

- **Lane** is the Monday group: Inbox, This Week, Doing, Done.
- **Status** is Done for the Done lane, Working on it for Doing, and To do for the other lanes.
- **Area** follows the note's top folder (Inbox, Bolt, Creator HQ & Content, Product Testing, Career & Creator Plan, Personal).
- **Type** is Task, Event, or Page.
- **vault_note** is the path inside the vault. That is how Bolt matches a card to a note.

The token stays in `.env`. Do not commit that file.
