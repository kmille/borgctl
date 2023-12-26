from borgctl.tools import parse_borg_repository
import pytest
import os


class TestTools:

    @pytest.mark.parametrize(
        ("repo", "result"), [
            ("ssh://user1@backuphost:/opt/dir", ("user1", "backuphost", "/opt/dir")),
            ("user1@backuphost:/opt/dir", ("user1", "backuphost", "/opt/dir")),
            ("root@backup-1.my.domain:/media", ("root", "backup-1.my.domain", "media")),
            ("backup-1.my.domain:/media", (os.getlogin(), "backup-1.my.domain", "media")),
        ]
    )
    def test_parse_borg_repository_valid(self, repo, result):
        user, host, repo_dir = parse_borg_repository(repo)

    #@pytest.mark.parametrize(
    #    ("repo", "result"), [
    #        ("ssh://user1@backuphost:/opt/dir@", ("user1", "backuphost", "/opt/dir")),
    #    ]
    #)
    #def test_parse_borg_repository_invalid(self, repo, result):
    #    user, host, repo_dir = parse_borg_repository(repo)
    #    breakpoint()
