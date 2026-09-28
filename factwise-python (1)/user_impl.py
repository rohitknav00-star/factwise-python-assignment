import json

from db_store import Collection, new_id, now_iso
from exceptions import NotFoundError, ValidationError
from user_base import UserBase

NAME_MAX_LEN = 64
DISPLAY_NAME_MAX_LEN_CREATE = 64
DISPLAY_NAME_MAX_LEN_UPDATE = 128


class UserAPI(UserBase):
    """
    File-persisted implementation of the user management API.

    Storage: a single ``users`` collection keyed by generated user id.
    Team membership itself lives in ``team_impl`` (a team owns the list of
    its members); ``get_user_teams`` simply looks that collection up.
    """

    def __init__(self):
        self.users = Collection("users")

    # -- internal helpers ---------------------------------------------------

    def _get_user_or_raise(self, user_id: str) -> dict:
        user = self.users.get(user_id)
        if user is None:
            raise NotFoundError(f"User '{user_id}' not found")
        return user

    def _name_exists(self, name: str, exclude_id: str = None) -> bool:
        for user in self.users.values():
            if user["name"] == name and user["id"] != exclude_id:
                return True
        return False

    # -- public API -----------------------------------------------------

    def create_user(self, request: str) -> str:
        data = json.loads(request)
        name = data.get("name")
        display_name = data.get("display_name")

        if not name or not isinstance(name, str):
            raise ValidationError("'name' is required and must be a string")
        if not display_name or not isinstance(display_name, str):
            raise ValidationError("'display_name' is required and must be a string")
        if len(name) > NAME_MAX_LEN:
            raise ValidationError(f"'name' must be at most {NAME_MAX_LEN} characters")
        if len(display_name) > DISPLAY_NAME_MAX_LEN_CREATE:
            raise ValidationError(
                f"'display_name' must be at most {DISPLAY_NAME_MAX_LEN_CREATE} characters"
            )
        if self._name_exists(name):
            raise ValidationError(f"user name '{name}' already exists")

        user = {
            "id": new_id(),
            "name": name,
            "display_name": display_name,
            "creation_time": now_iso(),
        }
        self.users.insert(user)
        return json.dumps({"id": user["id"]})

    def list_users(self) -> str:
        users = sorted(self.users.values(), key=lambda u: u["creation_time"])
        result = [
            {
                "name": u["name"],
                "display_name": u["display_name"],
                "creation_time": u["creation_time"],
            }
            for u in users
        ]
        return json.dumps(result)

    def describe_user(self, request: str) -> str:
        data = json.loads(request)
        user_id = data.get("id")
        if not user_id:
            raise ValidationError("'id' is required")
        user = self._get_user_or_raise(user_id)
        result = {
            "name": user["name"],
            "description": user.get("display_name", ""),
            "creation_time": user["creation_time"],
        }
        return json.dumps(result)

    def update_user(self, request: str) -> str:
        data = json.loads(request)
        user_id = data.get("id")
        if not user_id:
            raise ValidationError("'id' is required")
        user = self._get_user_or_raise(user_id)

        updates = data.get("user") or {}
        new_name = updates.get("name")
        new_display_name = updates.get("display_name")

        if new_name is not None and new_name != user["name"]:
            raise ValidationError("user name cannot be updated")
        if new_display_name is not None:
            if not isinstance(new_display_name, str):
                raise ValidationError("'display_name' must be a string")
            if len(new_display_name) > DISPLAY_NAME_MAX_LEN_UPDATE:
                raise ValidationError(
                    f"'display_name' must be at most {DISPLAY_NAME_MAX_LEN_UPDATE} characters"
                )
            user["display_name"] = new_display_name

        if new_name is not None and len(new_name) > NAME_MAX_LEN:
            raise ValidationError(f"'name' must be at most {NAME_MAX_LEN} characters")

        self.users.update(user_id, user)
        return json.dumps({"id": user["id"]})

    def get_user_teams(self, request: str) -> str:
        data = json.loads(request)
        user_id = data.get("id")
        if not user_id:
            raise ValidationError("'id' is required")
        self._get_user_or_raise(user_id)

        # Local import avoids a hard circular dependency between the two
        # implementation modules at import time.
        from team_impl import TeamAPI

        team_api = TeamAPI()
        teams = team_api.teams_for_user(user_id)
        result = [
            {
                "name": t["name"],
                "description": t["description"],
                "creation_time": t["creation_time"],
            }
            for t in teams
        ]
        return json.dumps(result)
