# Dashboard

The Dashboard page (first in the rail, above Chat) has three tabs, Personal, Career
and Business, plus a Character page that turns what you finish into an RPG
character. Everything is stored per state directory in `dashboard.db`; the
Work Hub, Jobs and Notes stay the owners of their own data.

## Tabs

| Tab | Shows |
| --- | --- |
| Personal | Habits (daily or n times a week, streaks, 21-day heatmap), personal quests, learning log, project health, scheduled jobs (failing ones first), recent notes |
| Career | Jobs pipeline totals, career quests, skills gained, the funnel, this week's activity |
| Business | Sales connection, revenue/MRR/sales/customers, goals with streaks, road to $10k, milestones, 6-month revenue, recent sales, business quests |
| Character | The warlock in a pixel frame; the level card (level, XP bar, STR/INT/CHA/VIT/DEX as bars, an evolution carousel with locked forms chained, streak and XP badges); achievements (24, with badge art where it exists), chronicle (XP log), party (agent profiles, two to a row), realms. Quests live on the Personal, Career and Business tabs. |
| Shop | Gold balance, earned today / this week, spent this month; the rewards shelf (add your own, buy with gold); the purse with what you are saving for and all-time figures; gold flow over 14 days; a ledger of every gold in (XP, achievements) and out (rewards). |
| Settings | Sales platform connection, project realms (which area each project's XP counts towards) |

The four summary tiles at the top of Personal, Career and Business are
buttons: each scrolls to the card it summarises and makes it pulse (Habits
today to Habits, MRR to Road to $10k, and so on).

## Skills gained

Career has a Skills gained card for skills you picked up from courses,
bootcamps, certifications, projects or work. Each skill is added once (any
case) and earns Career XP by its type: certification 100, bootcamp 80, online
course 40, project 30, on the job 30, self-taught 20. Removing a skill takes
its XP back. Skills unlock the Skilled, Certified and Polymath (10 skills)
achievements.

The same list shows in Jobs > Resume Studio. When a resume is tailored, the
skills are given to the model as verified: one the posting asks for may be
added to the resume's existing skills section, and nothing else is. The
tailored resume's notes list the skills that were added, worked out from the
text itself rather than from what the model reports.

## Quests

A quest is a Work Hub item you chose to focus on; there are no dates. Pick
them with **Choose quests** (Character page) or **Add** (each tab), or with
**Add to quests** in a Work Hub item's details. A quest always shows the
item's live Work Hub status, so finishing it in the Work Hub, or a chat
finishing it with the `work_hub` tool, ticks it off. A finished quest earns
50% bonus XP. A quest chosen on Personal, Career or Business shows there and
earns its XP there; one chosen on the Character page follows its project's
realm. The picker lists open Work Hub items and can be narrowed to General or
one project folder (read fresh each time, so new or deleted folders show).

## XP, levels and gold

| Source | XP | Realm / stat |
| --- | --- | --- |
| Work Hub item done | 20 (none/low), 30 (medium), 50 (high); x1.5 as a quest | the project's realm (Project realms) |
| Habit ticked | 10 per day | Personal, counts as VIT |
| Learning logged | course 40, book 30, certification 100, skill 20, other 15 | the chosen realm |
| Jobs | resume tailored 15, applied 30, interview 80, offer 250 | Career |
| Sale (live, not test mode) | 25 each | Business |
| Business milestone | 100 | Business |

Each award is written once to a ledger under a stable key, so reopening or
deleting an item later does not take XP back (unticking a habit or removing a
learning entry does). Level n needs 100 + 25(n-1) XP. Tiers: Apprentice (1),
Adept (5), Sorcerer (10), Archmage (20), Legendary (35). Gold is half of all
XP plus 50 per achievement, spent on rewards you define in the Shop (below Character in the side panel).
Reaching a new level shows a level-up card once per level on each browser,
naming the new form when the level crosses a tier.

## Sales platforms

Lemon Squeezy (API key) or Gumroad (access token). The key is checked with the
platform before it is saved to the active profile's env file
(`SALES_LEMONSQUEEZY_API_KEY` / `SALES_GUMROAD_ACCESS_TOKEN`) and is never
sent back to the browser. Sales are copied in at most every 2 minutes when the
page is read; when the platform is down the last copy stays and the reason is
shown. Customers are kept as fingerprints only. While a platform is connected
the server also polls it every 2 minutes in the background, so milestones,
goals and XP move as sales come in even with the page closed. Test-mode sales are shown but
never unlock milestones or earn XP. MRR counts subscriptions that renewed in
the last ~35 days. Sales can also be entered by hand. Goals (up to 12) can be labelled with a
Work Hub project; the list follows the Work Hub's project folders.

## Effects

Thinking orbs, border beams, bot avatars and liquid metal come from the
vendored Libraries.dev bundle (`static/vendor/libraries-dev/`), loaded only
when the Dashboard is shown. Reduced motion pauses them.

## Start page

A fresh launch opens the Dashboard. A reload keeps the page you were on
(Chat included), and a chat link (`/session/<id>`) or a launch shortcut
(`?action=...`) opens Chat. `HERMES_WEBUI_START_PAGE=chat` makes Chat the
start page instead. Dashboard, Chat and Settings are always shown in the rail.
