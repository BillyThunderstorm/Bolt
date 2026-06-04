# Bolt Daily Briefing System v1

## What This System Does

Every morning:

1. Pull today's calendar
2. Pull important inbox items
3. Generate a Bolt Daily Briefing
4. Create/update reminder checklist
5. Notify Billy that briefing is ready

Every evening:

1. Review completed tasks
2. Capture wins and lessons
3. Save context for tomorrow

---

# Apple Shortcuts Architecture

## Morning Shortcut (6:00 AM)

Name: Bolt Morning Briefing

Actions:

1. Get Upcoming Events (Calendar)
2. Get Reminders Due Today
3. Get Contents of URL
   - Bolt briefing endpoint (future)
4. Save briefing to Apple Notes
5. Show Notification
6. Open Note

## Evening Shortcut (9:00 PM)

Name: Bolt Daily Wrap-Up

Actions:

1. Get Completed Reminders
2. Ask for Input
3. Save to Notes
4. Send summary to Bolt endpoint (future)

---

# Reminder Lists

## Today's Mission

- Finish highest-priority Bolt task
- Content creation task
- Creator business task
- Learning task

---

# Google Calendar

Recommended calendars:

- Bolt Development
- Content Creation
- Personal
- Streaming

Suggested blocks:

08:00-10:00 Bolt Development
10:00-12:00 Content Creation
13:00-15:00 Reviews / Testing
16:00-17:00 Learning
19:00-21:00 Stream

---

# Future Automation

When Bolt gains connector access:

- Gmail
- Google Calendar
- Reminders
- Notes

The briefing can be generated automatically using the uploaded template.
