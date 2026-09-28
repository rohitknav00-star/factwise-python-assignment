import json
import os

from db_store import BASE_DIR, Collection, new_id, now_iso
from exceptions import ConflictError, NotFoundError, ValidationError
from project_board_base import ProjectBoardBase

NAME_MAX_LEN = 64
DESCRIPTION_MAX_LEN = 128
TASK_TITLE_MAX_LEN = 64
TASK_DESCRIPTION_MAX_LEN = 128

BOARD_STATUS_OPEN = "OPEN"
BOARD_STATUS_CLOSED = "CLOSED"

TASK_STATUS_OPEN = "OPEN"
TASK_STATUS_IN_PROGRESS = "IN_PROGRESS"
TASK_STATUS_COMPLETE = "COMPLETE"
VALID_TASK_STATUSES = {TASK_STATUS_OPEN, TASK_STATUS_IN_PROGRESS, TASK_STATUS_COMPLETE}

OUT_DIR = os.path.join(BASE_DIR, "out")


class ProjectBoardAPI(ProjectBoardBase):
    """
    File-persisted implementation of the project board / task API.

    Storage:
      * ``boards`` - board_id -> board record
      * ``tasks``  - task_id  -> task record (each task carries its board_id)
    """

    def __init__(self):
        self.boards = Collection("boards")
        self.tasks = Collection("tasks")

    # -- internal helpers ---------------------------------------------------

    def _get_board_or_raise(self, board_id: str) -> dict:
        board = self.boards.get(board_id)
        if board is None:
            raise NotFoundError(f"Board '{board_id}' not found")
        return board

    def _get_team_or_raise(self, team_id: str) -> dict:
        from team_impl import TeamAPI

        team_api = TeamAPI()
        team = team_api.teams.get(team_id)
        if team is None:
            raise NotFoundError(f"Team '{team_id}' not found")
        return team

    def _get_user_or_raise(self, user_id: str) -> dict:
        from user_impl import UserAPI

        user_api = UserAPI()
        user = user_api.users.get(user_id)
        if user is None:
            raise NotFoundError(f"User '{user_id}' not found")
        return user

    def _board_name_exists_for_team(self, team_id: str, name: str) -> bool:
        for board in self.boards.values():
            if board["team_id"] == team_id and board["name"] == name:
                return True
        return False

    def _tasks_for_board(self, board_id: str) -> list:
        return [t for t in self.tasks.values() if t["board_id"] == board_id]

    def _task_title_exists_for_board(self, board_id: str, title: str) -> bool:
        for task in self._tasks_for_board(board_id):
            if task["title"] == title:
                return True
        return False

    # -- public API -----------------------------------------------------

    def create_board(self, request: str):
        data = json.loads(request)
        name = data.get("name")
        description = data.get("description", "")
        team_id = data.get("team_id")

        if not name or not isinstance(name, str):
            raise ValidationError("'name' is required and must be a string")
        if len(name) > NAME_MAX_LEN:
            raise ValidationError(f"'name' must be at most {NAME_MAX_LEN} characters")
        if description and len(description) > DESCRIPTION_MAX_LEN:
            raise ValidationError(
                f"'description' must be at most {DESCRIPTION_MAX_LEN} characters"
            )
        if not team_id:
            raise ValidationError("'team_id' is required")
        self._get_team_or_raise(team_id)

        if self._board_name_exists_for_team(team_id, name):
            raise ConflictError(f"board name '{name}' already exists for this team")

        board = {
            "id": new_id(),
            "name": name,
            "description": description,
            "team_id": team_id,
            "status": BOARD_STATUS_OPEN,
            "creation_time": now_iso(),
            "end_time": None,
        }
        self.boards.insert(board)
        return json.dumps({"id": board["id"]})

    def close_board(self, request: str) -> str:
        data = json.loads(request)
        board_id = data.get("id")
        if not board_id:
            raise ValidationError("'id' is required")
        board = self._get_board_or_raise(board_id)

        if board["status"] == BOARD_STATUS_CLOSED:
            raise ValidationError("board is already closed")

        tasks = self._tasks_for_board(board_id)
        if any(t["status"] != TASK_STATUS_COMPLETE for t in tasks):
            raise ValidationError(
                "cannot close a board unless all of its tasks are COMPLETE"
            )

        board["status"] = BOARD_STATUS_CLOSED
        board["end_time"] = now_iso()
        self.boards.update(board_id, board)
        return json.dumps({"id": board["id"]})

    def add_task(self, request: str) -> str:
        data = json.loads(request)
        title = data.get("title")
        description = data.get("description", "")
        user_id = data.get("user_id")
        board_id = data.get("board_id") or data.get("id")

        if not board_id:
            raise ValidationError("'board_id' is required")
        board = self._get_board_or_raise(board_id)

        if not title or not isinstance(title, str):
            raise ValidationError("'title' is required and must be a string")
        if len(title) > TASK_TITLE_MAX_LEN:
            raise ValidationError(f"'title' must be at most {TASK_TITLE_MAX_LEN} characters")
        if description and len(description) > TASK_DESCRIPTION_MAX_LEN:
            raise ValidationError(
                f"'description' must be at most {TASK_DESCRIPTION_MAX_LEN} characters"
            )
        if not user_id:
            raise ValidationError("'user_id' is required")
        self._get_user_or_raise(user_id)

        if board["status"] != BOARD_STATUS_OPEN:
            raise ValidationError("tasks can only be added to an OPEN board")

        if self._task_title_exists_for_board(board_id, title):
            raise ConflictError(f"task title '{title}' already exists for this board")

        task = {
            "id": new_id(),
            "title": title,
            "description": description,
            "user_id": user_id,
            "board_id": board_id,
            "status": TASK_STATUS_OPEN,
            "creation_time": now_iso(),
        }
        self.tasks.insert(task)
        return json.dumps({"id": task["id"]})

    def update_task_status(self, request: str):
        data = json.loads(request)
        task_id = data.get("id")
        status = data.get("status")

        if not task_id:
            raise ValidationError("'id' is required")
        task = self.tasks.get(task_id)
        if task is None:
            raise NotFoundError(f"Task '{task_id}' not found")

        if status not in VALID_TASK_STATUSES:
            raise ValidationError(
                f"'status' must be one of {sorted(VALID_TASK_STATUSES)}"
            )

        task["status"] = status
        self.tasks.update(task_id, task)
        return json.dumps({"id": task["id"]})

    def list_boards(self, request: str) -> str:
        data = json.loads(request)
        team_id = data.get("id")
        if not team_id:
            raise ValidationError("'id' is required")
        self._get_team_or_raise(team_id)

        boards = [
            b
            for b in self.boards.values()
            if b["team_id"] == team_id and b["status"] == BOARD_STATUS_OPEN
        ]
        result = [{"id": b["id"], "name": b["name"]} for b in boards]
        return json.dumps(result)

    def export_board(self, request: str) -> str:
        data = json.loads(request)
        board_id = data.get("id")
        if not board_id:
            raise ValidationError("'id' is required")
        board = self._get_board_or_raise(board_id)
        tasks = sorted(self._tasks_for_board(board_id), key=lambda t: t["creation_time"])

        from user_impl import UserAPI

        user_api = UserAPI()

        def display_name_for(user_id):
            user = user_api.users.get(user_id)
            return user["display_name"] if user else user_id

        lines = []
        title = f"Board: {board['name']}"
        lines.append(title)
        lines.append("=" * len(title))
        lines.append(f"Description : {board['description']}")
        lines.append(f"Status      : {board['status']}")
        lines.append(f"Created     : {board['creation_time']}")
        if board.get("end_time"):
            lines.append(f"Closed      : {board['end_time']}")
        lines.append("")
        lines.append(f"Tasks ({len(tasks)})")
        lines.append("-" * 40)

        if not tasks:
            lines.append("(no tasks)")
        else:
            by_status = {
                TASK_STATUS_OPEN: [],
                TASK_STATUS_IN_PROGRESS: [],
                TASK_STATUS_COMPLETE: [],
            }
            for task in tasks:
                by_status[task["status"]].append(task)

            for status in (TASK_STATUS_OPEN, TASK_STATUS_IN_PROGRESS, TASK_STATUS_COMPLETE):
                group = by_status[status]
                lines.append(f"\n[{status}] ({len(group)})")
                if not group:
                    lines.append("  -")
                    continue
                for task in group:
                    assignee = display_name_for(task["user_id"])
                    lines.append(f"  * {task['title']}  (assigned to: {assignee})")
                    if task["description"]:
                        lines.append(f"      {task['description']}")

        os.makedirs(OUT_DIR, exist_ok=True)
        file_name = f"board_{board['id']}.txt"
        file_path = os.path.join(OUT_DIR, file_name)
        with open(file_path, "w", encoding="utf-8") as f:
            f.write("\n".join(lines) + "\n")

        return json.dumps({"out_file": file_name})
