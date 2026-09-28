import json

from db_store import Collection, new_id, now_iso
from exceptions import NotFoundError, ValidationError
from team_base import TeamBase

NAME_MAX_LEN = 64
DESCRIPTION_MAX_LEN = 128
MAX_TEAM_MEMBERS = 50


class TeamAPI(TeamBase):
    """
    File-persisted implementation of the team management API.

    Storage:
      * ``teams``        - team_id -> team record (name/description/admin/...)
      * ``team_members``  - team_id -> {"members": [user_id, ...]}, kept as
        its own collection so team membership can grow independently of
        the team's own attributes.
    """

    def __init__(self):
        self.teams = Collection("teams")
        self.memberships = Collection("team_members")

    # -- internal helpers ---------------------------------------------------

    def _get_team_or_raise(self, team_id: str) -> dict:
        team = self.teams.get(team_id)
        if team is None:
            raise NotFoundError(f"Team '{team_id}' not found")
        return team

    def _name_exists(self, name: str, exclude_id: str = None) -> bool:
        for team in self.teams.values():
            if team["name"] == name and team["id"] != exclude_id:
                return True
        return False

    def _get_user_or_raise(self, user_id: str) -> dict:
        # Local import to avoid a circular import with user_impl at module
        # load time (user_impl also imports team_impl lazily).
        from user_impl import UserAPI

        user_api = UserAPI()
        user = user_api.users.get(user_id)
        if user is None:
            raise NotFoundError(f"User '{user_id}' not found")
        return user

    def _members_for(self, team_id: str) -> list:
        membership = self.memberships.get(team_id)
        return list(membership["members"]) if membership else []

    def _save_members(self, team_id: str, members: list) -> None:
        record = {"id": team_id, "members": members}
        existing = self.memberships.get(team_id)
        if existing is None:
            self.memberships.insert(record)
        else:
            self.memberships.update(team_id, record)

    # -- helper used by user_impl.get_user_teams -----------------------------

    def teams_for_user(self, user_id: str) -> list:
        team_ids = [
            m["id"] for m in self.memberships.values() if user_id in m.get("members", [])
        ]
        return [self.teams.get(tid) for tid in team_ids if self.teams.get(tid)]

    # -- public API -----------------------------------------------------

    def create_team(self, request: str) -> str:
        data = json.loads(request)
        name = data.get("name")
        description = data.get("description", "")
        admin = data.get("admin")

        if not name or not isinstance(name, str):
            raise ValidationError("'name' is required and must be a string")
        if len(name) > NAME_MAX_LEN:
            raise ValidationError(f"'name' must be at most {NAME_MAX_LEN} characters")
        if description and len(description) > DESCRIPTION_MAX_LEN:
            raise ValidationError(
                f"'description' must be at most {DESCRIPTION_MAX_LEN} characters"
            )
        if not admin:
            raise ValidationError("'admin' is required")
        self._get_user_or_raise(admin)
        if self._name_exists(name):
            raise ValidationError(f"team name '{name}' already exists")

        team = {
            "id": new_id(),
            "name": name,
            "description": description,
            "admin": admin,
            "creation_time": now_iso(),
        }
        self.teams.insert(team)
        # The admin is implicitly a member of their own team.
        self._save_members(team["id"], [admin])
        return json.dumps({"id": team["id"]})

    def list_teams(self) -> str:
        teams = sorted(self.teams.values(), key=lambda t: t["creation_time"])
        result = [
            {
                "name": t["name"],
                "description": t["description"],
                "creation_time": t["creation_time"],
                "admin": t["admin"],
            }
            for t in teams
        ]
        return json.dumps(result)

    def describe_team(self, request: str) -> str:
        data = json.loads(request)
        team_id = data.get("id")
        if not team_id:
            raise ValidationError("'id' is required")
        team = self._get_team_or_raise(team_id)
        result = {
            "name": team["name"],
            "description": team["description"],
            "creation_time": team["creation_time"],
            "admin": team["admin"],
        }
        return json.dumps(result)

    def update_team(self, request: str) -> str:
        data = json.loads(request)
        team_id = data.get("id")
        if not team_id:
            raise ValidationError("'id' is required")
        team = self._get_team_or_raise(team_id)

        updates = data.get("team") or {}
        new_name = updates.get("name")
        new_description = updates.get("description")
        new_admin = updates.get("admin")

        if new_name is not None:
            if not isinstance(new_name, str) or not new_name:
                raise ValidationError("'name' must be a non-empty string")
            if len(new_name) > NAME_MAX_LEN:
                raise ValidationError(f"'name' must be at most {NAME_MAX_LEN} characters")
            if self._name_exists(new_name, exclude_id=team_id):
                raise ValidationError(f"team name '{new_name}' already exists")
            team["name"] = new_name

        if new_description is not None:
            if len(new_description) > DESCRIPTION_MAX_LEN:
                raise ValidationError(
                    f"'description' must be at most {DESCRIPTION_MAX_LEN} characters"
                )
            team["description"] = new_description

        if new_admin is not None:
            self._get_user_or_raise(new_admin)
            team["admin"] = new_admin

        self.teams.update(team_id, team)
        return json.dumps({"id": team["id"]})

    def add_users_to_team(self, request: str):
        data = json.loads(request)
        team_id = data.get("id")
        user_ids = data.get("users") or []

        if not team_id:
            raise ValidationError("'id' is required")
        self._get_team_or_raise(team_id)
        if not isinstance(user_ids, list) or not user_ids:
            raise ValidationError("'users' must be a non-empty list")

        current_members = self._members_for(team_id)
        for user_id in user_ids:
            self._get_user_or_raise(user_id)

        merged = list(current_members)
        for user_id in user_ids:
            if user_id not in merged:
                merged.append(user_id)

        if len(merged) > MAX_TEAM_MEMBERS:
            raise ValidationError(
                f"a team cannot have more than {MAX_TEAM_MEMBERS} users"
            )

        self._save_members(team_id, merged)
        return json.dumps({"id": team_id})

    def remove_users_from_team(self, request: str):
        data = json.loads(request)
        team_id = data.get("id")
        user_ids = data.get("users") or []

        if not team_id:
            raise ValidationError("'id' is required")
        team = self._get_team_or_raise(team_id)
        if not isinstance(user_ids, list) or not user_ids:
            raise ValidationError("'users' must be a non-empty list")
        if len(user_ids) > 50:
            raise ValidationError("cannot remove more than 50 users at once")

        current_members = self._members_for(team_id)
        remaining = [uid for uid in current_members if uid not in user_ids]

        if team["admin"] in user_ids:
            raise ValidationError("cannot remove the team admin from the team")

        self._save_members(team_id, remaining)
        return json.dumps({"id": team_id})

    def list_team_users(self, request: str):
        data = json.loads(request)
        team_id = data.get("id")
        if not team_id:
            raise ValidationError("'id' is required")
        self._get_team_or_raise(team_id)

        from user_impl import UserAPI

        user_api = UserAPI()
        members = self._members_for(team_id)
        result = []
        for user_id in members:
            user = user_api.users.get(user_id)
            if user:
                result.append(
                    {
                        "id": user["id"],
                        "name": user["name"],
                        "display_name": user["display_name"],
                    }
                )
        return json.dumps(result)
