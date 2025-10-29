import pytest

from modules.database.models import DatabaseManager
from modules.projects.service import ProjectService


@pytest.fixture
def project_service(tmp_path_factory):
    db_path = tmp_path_factory.mktemp("db") / "projects.db"
    db = DatabaseManager(db_name=str(db_path))
    service = ProjectService(db)
    owner_id = db.create_user("Owner", "User", "owner@example.com", "password123")
    invitee_id = db.create_user("Guest", "User", "guest@example.com", "password123")
    project = service.create_project_without_pdfs("Shared", "Test project", owner_id)
    db.create_or_update_project_share(project["project_id"], owner_id, invitee_id)
    return service, db, project["project_id"], owner_id, invitee_id


def test_shared_project_listing_and_acceptance(project_service):
    service, db, project_id, owner_id, invitee_id = project_service

    shared = service.get_shared_projects(invitee_id)
    assert shared
    assert shared[0]["status"] == "pending"

    result = service.accept_project_share(project_id, invitee_id)
    assert result["status"] == "accepted"
    assert service.validate_project_access(project_id, invitee_id)

    updated_share = db.get_project_share(project_id, invitee_id)
    assert updated_share.status == "accepted"

    rejection = service.reject_project_share(project_id, invitee_id)
    assert rejection["status"] == "rejected"
