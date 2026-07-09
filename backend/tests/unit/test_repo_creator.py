from types import SimpleNamespace
from unittest import TestCase
from unittest.mock import patch

from app.core.config import settings
from app.core.exceptions import PushFailedError
from app.infrastructure.github.github_client import GithubRepoResponse
from app.infrastructure.github.profile_resolver import TargetProfile
from app.infrastructure.github.repo_creator import RepoCreator


class FakeGithubClient:
    def __init__(self, responses):
        self._responses = list(responses)
        self.created_names = []

    def create_repository_sync(
        self,
        owner,
        name,
        token,
        *,
        is_org,
        private=False,
        description="",
    ):
        self.created_names.append(name)
        return self._responses.pop(0)


class FakeProfileResolver:
    def resolve(self, owner=None, host=None):
        return TargetProfile(
            owner=owner or "Javaapex",
            is_org=False,
            host=host or "github.com",
        )


class RepoCreatorTests(TestCase):
    def setUp(self):
        self._original_token = settings.github_target_token
        settings.github_target_token = "target-token"

    def tearDown(self):
        settings.github_target_token = self._original_token

    def test_retries_with_unique_suffix_when_repo_name_already_exists(self):
        base_name = "registration-form-profile-Migrated20260708095604"
        suffixed_name = f"{base_name}-abcde"
        client = FakeGithubClient(
            [
                GithubRepoResponse(
                    status_code=422,
                    data={
                        "message": "Repository creation failed.",
                        "errors": [
                            {"message": "name already exists on this account"}
                        ],
                    },
                ),
                GithubRepoResponse(
                    status_code=201,
                    data={
                        "name": suffixed_name,
                        "html_url": f"https://github.com/Javaapex/{suffixed_name}",
                        "clone_url": f"https://github.com/Javaapex/{suffixed_name}.git",
                    },
                ),
            ]
        )
        creator = RepoCreator(
            github_client=client,
            profile_resolver=FakeProfileResolver(),
        )

        with patch(
            "app.infrastructure.github.repo_creator.uuid4",
            return_value=SimpleNamespace(hex="abcde12345"),
        ):
            created = creator.create(base_name)

        self.assertEqual(client.created_names, [base_name, suffixed_name])
        self.assertEqual(created.owner, "Javaapex")
        self.assertEqual(created.name, suffixed_name)
        self.assertEqual(
            created.html_url,
            f"https://github.com/Javaapex/{suffixed_name}",
        )
        self.assertEqual(
            created.clone_url,
            f"https://github.com/Javaapex/{suffixed_name}.git",
        )

    def test_non_collision_422_raises_with_nested_error_message(self):
        client = FakeGithubClient(
            [
                GithubRepoResponse(
                    status_code=422,
                    data={
                        "message": "Validation Failed",
                        "errors": [{"message": "name is invalid"}],
                    },
                )
            ]
        )
        creator = RepoCreator(
            github_client=client,
            profile_resolver=FakeProfileResolver(),
        )

        with self.assertRaises(PushFailedError) as caught:
            creator.create("invalid name")

        self.assertEqual(client.created_names, ["invalid name"])
        self.assertIn("Validation Failed", str(caught.exception))
        self.assertIn("name is invalid", str(caught.exception))
