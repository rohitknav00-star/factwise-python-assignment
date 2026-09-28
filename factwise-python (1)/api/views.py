from project_board_impl import ProjectBoardAPI
from team_impl import TeamAPI
from user_impl import UserAPI

from .utils import api_view

user_api = UserAPI()
team_api = TeamAPI()
board_api = ProjectBoardAPI()

# ---------------------------------------------------------------------------
# Users
# ---------------------------------------------------------------------------

create_user = api_view(lambda body: user_api.create_user(body))
list_users = api_view(lambda body: user_api.list_users())
describe_user = api_view(lambda body: user_api.describe_user(body))
update_user = api_view(lambda body: user_api.update_user(body))
get_user_teams = api_view(lambda body: user_api.get_user_teams(body))

# ---------------------------------------------------------------------------
# Teams
# ---------------------------------------------------------------------------

create_team = api_view(lambda body: team_api.create_team(body))
list_teams = api_view(lambda body: team_api.list_teams())
describe_team = api_view(lambda body: team_api.describe_team(body))
update_team = api_view(lambda body: team_api.update_team(body))
add_users_to_team = api_view(lambda body: team_api.add_users_to_team(body))
remove_users_from_team = api_view(lambda body: team_api.remove_users_from_team(body))
list_team_users = api_view(lambda body: team_api.list_team_users(body))

# ---------------------------------------------------------------------------
# Project boards
# ---------------------------------------------------------------------------

create_board = api_view(lambda body: board_api.create_board(body))
close_board = api_view(lambda body: board_api.close_board(body))
add_task = api_view(lambda body: board_api.add_task(body))
update_task_status = api_view(lambda body: board_api.update_task_status(body))
list_boards = api_view(lambda body: board_api.list_boards(body))
export_board = api_view(lambda body: board_api.export_board(body))
