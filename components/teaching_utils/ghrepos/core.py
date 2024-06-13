import os
import logging
import requests
from github import Github, GithubException
from github import Auth
from github.Repository import Repository
from ..config import settings

logger = logging.getLogger(__name__)


def gh_client() -> Github:
    # using an access token
    auth = Auth.Token(settings.GITHUB_TOKEN)

    # Public Web Github
    return Github(auth=auth)


def get_repository(name: str) -> Repository:

    # Get a new client instance
    client = gh_client()

    repo = None
    try:
        repo = client.get_repo(name)
    except GithubException:
        pass
    # To close connections after use
    client.close()

    return repo


def get_repository_range(base: str, range_min: int = 1, range_max: int = 25) -> list[Repository]:

    # Get a new client instance
    client = gh_client()

    # Then play with your Github objects:
    repos = []
    for num in range(range_min, range_max+1):
        repo = None
        try:
            repo = client.get_repo(f'{base}{num:02d}')
        except GithubException:
            try:
                repo = client.get_repo(f'{base}{num}')
            except GithubException:
                pass
        if repo is not None:
            repos.append(repo)
    # To close connections after use
    client.close()

    return repos


def clone_repository(repo: Repository | str) -> str | None:
    repo_obj = None
    if isinstance(repo, Repository):
        repo_obj = repo
    else:
        repo_obj = get_repository(repo)

    logger.info('Cloning repository %s', repo_obj.name)

    repo_local_path = None
    if repo_obj is not None:
        repo_local_path = os.path.join(settings.EXPORT_PATH, repo_obj.name)
        contents = repo_obj.get_contents("")
        while contents:
            file_content = contents.pop(0)
            if file_content.type == "dir":
                contents.extend(repo_obj.get_contents(file_content.path))
            else:
                logger.debug('Repository: %s => Cloning file %s', repo_obj.name, file_content.path)
                full_path = os.path.join(repo_local_path, file_content.path)
                file_content_decoded = None
                try:
                    os.makedirs(os.path.dirname(full_path), exist_ok=True)
                    file_content_decoded = file_content.decoded_content
                except AssertionError as e:
                    resp = requests.get(repo_obj.get_contents(file_content.path).download_url)
                    if resp.status_code == 200:
                        if resp.encoding is not None:
                            file_content_decoded = resp.content.decode(resp.encoding)
                        else:
                            file_content_decoded = resp.content
                if file_content_decoded is not None:
                    if isinstance(file_content_decoded, str):
                        file_content_decoded = file_content_decoded.encode()
                    with open(full_path, 'wb') as f:
                        f.write(file_content_decoded)
                else:
                    logger.error('Failed to clone repository file: %s', file_content.path)

    return repo_local_path
