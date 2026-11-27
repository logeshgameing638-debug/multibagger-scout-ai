# Project tasks (task-master style)

`tasks.json` is the live work queue for this repo, in the spirit of
[Task Master](https://github.com/eyaltoledano/claude-task-master), adapted so
no CLI, editor plugin or API key is needed - the project agents (Instinct)
maintain it directly.

## How a work session runs

1. Read `../SPEC.md` - the constitution and product spec are the rules of the
   project. Never violate a constitution rule without the owner's explicit
   approval on his WhatsApp channel.
2. Open `tasks.json`, take the highest-priority task that is `pending` or
   already `in-progress`, respecting `dependencies`.
3. Do the work. When it is verified live (owner's rule: done means checked on
   the live site), set the task `done`; when blocked, set `blocked` and write
   exactly what it waits on in `details`.
4. Update `last_updated` and commit the task-file change together with the
   work it describes.

## Rules

- Statuses: `pending`, `in-progress`, `blocked`, `deferred`, `done`.
- Priorities: `high`, `medium`, `low`. New asks from the owner get a task id
  before work starts, so nothing he asked for is lost.
- One task = one verifiable outcome. Split big asks; keep dependencies honest.
- The owner is zero-coding: these files exist so HE never has to run anything.
  Agents read and write them; he just asks for features on WhatsApp.

## Where this pattern also applies

The same SPEC.md + tasks/ pair can be created in the owner's other projects:
`my-algo-platform`, `my-personal-assistant`, and the stock screener website.
Create them the first time work lands on those repos.
