# FactWise Team Project Planner

A small team/project/board planner exposed as a set of Django HTTP APIs, with
all data persisted to flat files on local disk (no database).

## What's implemented

* `user_impl.py` — `UserAPI(UserBase)`: create/list/describe/update a user,
  and list the teams a user belongs to.
* `team_impl.py` — `TeamAPI(TeamBase)`: create/list/describe/update a team,
  add/remove members (capped at 50), list a team's members.
* `project_board_impl.py` — `ProjectBoardAPI(ProjectBoardBase)`: create a
  board, add tasks to it, update task status, close a board, list a team's
  open boards, and export a board to a text file.
* `api/` — a thin Django app that turns each of the methods above into an
  HTTP endpoint. All three implementation classes work standalone too (see
  "Running without Django" below) — Django is purely the transport layer
  the problem statement asked for.

All three `*_base.py` files are untouched; `*_impl.py` modules implement
them.

## Persistence

* `db_store.py` is the only module that touches disk. Each logical
  collection (`users`, `teams`, `team_members`, `boards`, `tasks`) is one
  JSON file under `db/`, keyed by id.
* **Why JSON files instead of SQLite/Django ORM**: the brief explicitly
  asks for local file storage with the format left to the developer.
  Flat JSON keeps the store human-readable while testing/debugging, needs
  no schema/migrations, and is trivial to keep hidden behind the API (the
  `db/` folder is never referenced outside `db_store.py`).
* Writes are atomic (write to a temp file, `os.replace` into place) and
  guarded by an in-process lock per collection, so the threaded Django dev
  server can't corrupt a file mid-write. This is *not* multi-process safe;
  see "Known limitations".
* `db/` and `out/` (used by `export_board`) start empty and fill up at
  runtime; their contents are intentionally excluded from the submission
  zip and from git (see `.gitignore`).

## Design choices & assumptions

* **Error handling** — `exceptions.py` defines `ValidationError` (400),
  `NotFoundError` (404) and `ConflictError` (409), all under a common
  `ApplicationError`. The Django view layer (`api/utils.py`) catches these
  and returns the matching HTTP status with `{"error": "..."}`; anything
  unexpected becomes a 500 instead of leaking a traceback.
* **IDs** — every entity gets a server-generated `uuid4` hex id. Clients
  never choose ids.
* **Timestamps** — `creation_time`/`end_time` are always set by the
  server (UTC, ISO-8601), even where a docstring's example payload shows
  the client supplying one (`create_board`, `add_task`). Trusting a
  client-supplied timestamp would make ordering and audit trails
  unreliable, so those fields are accepted-but-ignored if sent.
* **`add_task`'s board id** — `ProjectBoardBase.add_task`'s example
  payload has no field identifying *which* board the task goes on (a
  task obviously belongs to exactly one board). The implementation reads
  `board_id` from the request (accepting `id` as a fallback) — this is
  the one place a field was added beyond the base docstring's example.
* **Team admin** — `create_team` requires `admin` to be an existing user
  id, and that user is automatically the team's first member. Removing
  the admin via `remove_users_from_team` is rejected — a team should
  always have a reachable admin; reassign the admin with `update_team`
  first if it needs to change.
* **`update_user`/`update_team`** — both silently ignore any submitted
  fields that aren't allowed to be edited; `update_user` explicitly
  rejects attempts to *change* the `name` value (raises `ValidationError`)
  since the base docstring says the user name cannot be updated. `admin`
  and `name` can be updated on a team (name uniqueness is re-checked).
* **`list_boards`** — the docstring says "list all open boards for a
  team", so this returns only `OPEN` boards, not closed ones.
* **`export_board`** — output is a `.txt` file per board in `out/`, named
  `board_<board_id>.txt`, grouping tasks by status and showing each
  assignee's display name.
* **Membership cap of 50** — enforced on the *resulting* member count
  after an `add_users_to_team` call, not per-call; a call that would push
  the team over 50 total members is rejected entirely (nothing is
  partially applied).

## Running

```bash
pip install -r requirements.txt
python manage.py runserver
```

The API is mounted under `/api/`, e.g.:

```
POST /api/users/create           {"name": "...", "display_name": "..."}
GET  /api/users/list
POST /api/users/describe         {"id": "..."}
POST /api/users/update           {"id": "...", "user": {"display_name": "..."}}
POST /api/users/get-teams        {"id": "..."}

POST /api/teams/create           {"name": "...", "description": "...", "admin": "..."}
GET  /api/teams/list
POST /api/teams/describe         {"id": "..."}
POST /api/teams/update           {"id": "...", "team": {...}}
POST /api/teams/add-users        {"id": "...", "users": ["..."]}
POST /api/teams/remove-users     {"id": "...", "users": ["..."]}
POST /api/teams/list-users       {"id": "..."}

POST /api/boards/create              {"name": "...", "description": "...", "team_id": "..."}
POST /api/boards/close               {"id": "..."}
POST /api/boards/add-task            {"title": "...", "description": "...", "user_id": "...", "board_id": "..."}
POST /api/boards/update-task-status  {"id": "...", "status": "OPEN|IN_PROGRESS|COMPLETE"}
POST /api/boards/list                {"id": "<team_id>"}
POST /api/boards/export              {"id": "<board_id>"}
```

### Running without Django

Because all of the actual logic lives in `UserAPI`, `TeamAPI` and
`ProjectBoardAPI` (plain Python classes over JSON strings, exactly matching
the base class signatures), they can be imported and exercised directly
without starting a server — useful for quick scripts or unit tests:

```python
import json
from user_impl import UserAPI

api = UserAPI()
print(api.create_user(json.dumps({"name": "alice", "display_name": "Alice"})))
```

## Project layout

```
factwise/            Django project (settings/urls/wsgi) - no ORM apps enabled
api/                  Django app: HTTP views + URL routing only
user_base.py          given base class (unchanged)
team_base.py          given base class (unchanged)
project_board_base.py given base class (unchanged)
user_impl.py          UserAPI implementation
team_impl.py          TeamAPI implementation
project_board_impl.py ProjectBoardAPI implementation
db_store.py           flat-file persistence layer
exceptions.py         ValidationError / NotFoundError / ConflictError
db/                   JSON data files (created at runtime, gitignored)
out/                  exported board .txt files (created at runtime, gitignored)
```

## Known limitations

* The file-lock in `db_store.py` is per-process; running multiple server
  processes (e.g. gunicorn with several workers) against the same `db/`
  folder could race. A single-process dev server (as used above) does not
  hit this.
* No authentication/authorization layer — any caller can act as any user.
  Out of scope per the problem statement, but worth flagging for a real
  deployment.
