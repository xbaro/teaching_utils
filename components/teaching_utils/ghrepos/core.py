import os
import logging
import requests
from github import Github, GithubException
from github import Auth
from github.Repository import Repository
from github.ContentFile import ContentFile
from teaching_utils.config import settings

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


def get_repository_idx(base: str, index: int):

    # Get a new client instance
    client = gh_client()

    try:
        repo = client.get_repo(f'{base}{index:02d}')
    except GithubException:
        try:
            repo = client.get_repo(f'{base}{index}')
        except GithubException:
            repo = None

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


def _save_file(repo: Repository, file_content: ContentFile, target_path):
    file_content_decoded = None
    try:
        os.makedirs(os.path.dirname(target_path), exist_ok=True)
        file_content_decoded = file_content.decoded_content
    except AssertionError:
        resp = requests.get(repo.get_contents(file_content.path).download_url)
        if resp.status_code == 200:
            if resp.encoding is not None:
                file_content_decoded = resp.content.decode(resp.encoding)
            else:
                file_content_decoded = resp.content
    if file_content_decoded is not None:
        if isinstance(file_content_decoded, str):
            file_content_decoded = file_content_decoded.encode()
        with open(target_path, 'wb') as f:
            f.write(file_content_decoded)


def clone_repository(repo: Repository | str, export_path: str = None, force: bool = False) -> str | None:  # noqa: C901
    # TODO: Reduce complexity
    repo_obj = None
    if isinstance(repo, Repository):
        repo_obj = repo
    else:
        repo_obj = get_repository(repo)

    logger.info('Cloning repository %s', repo_obj.name)

    repo_local_path = None
    if repo_obj is not None:
        if export_path is None:
            export_path = settings.EXPORT_PATH
        repo_local_path = os.path.join(export_path, repo_obj.name)
        if os.path.exists(repo_local_path):
            logger.info('Target path %s already exists', repo_local_path)
            if force:
                logger.info('Target path %s DELETED', repo_local_path)
                os.removedirs(repo_local_path)
        contents = repo_obj.get_contents("")
        while contents:
            file_content = contents.pop(0)
            if file_content.type == "dir":
                contents.extend(repo_obj.get_contents(file_content.path))
            else:
                logger.debug('Repository: %s => Cloning file %s', repo_obj.name, file_content.path)
                full_path = os.path.join(repo_local_path, file_content.path)
                if os.path.exists(full_path):
                    logger.debug('Repository: %s => File SKIPPED %s', repo_obj.name, file_content.path)
                    continue
                file_content_decoded = None
                try:
                    os.makedirs(os.path.dirname(full_path), exist_ok=True)
                    file_content_decoded = file_content.decoded_content
                except AssertionError:
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


def get_repository_stats(repo: Repository):  # noqa: C901
    # TODO: Reduce complexity
    # Get a new client instance
    client = gh_client()

    branches_data = repo.get_branches()

    branches_stats = {
        'total': branches_data.totalCount,
        'data': list(branches_data),
        'commits': {}
    }

    contributors = {
        'data': {},
        'total': 0,
        'contributors': []
    }

    commits_data = {
        'total': 0,
        'data': {}
    }

    for branch in branches_data:
        branch_commits = repo.get_commits(branch.name)
        for bc in branch_commits:
            author = bc.author
            if author is None:
                for user in repo.get_contributors():
                    if user.login == bc.commit.author.name or user.email == bc.commit.author.email:
                        author = user
                        break
            if author is None:
                continue

            if author.id not in contributors['data']:
                contributors['data'][author.id] = {
                    'info': author,
                    'commits': {},
                    'branches': {}
                }
            if branch.name not in contributors['data'][author.id]['branches']:
                contributors['data'][author.id]['branches'][branch.name] = branch
            contributors['data'][author.id]['commits'][bc.sha] = bc
            if branch.name not in branches_stats['commits']:
                branches_stats['commits'][branch.name] = {}
            branches_stats['commits'][branch.name][bc.sha] = bc
            commits_data['total'] += 1
            commits_data['data'][bc.sha] = {
                'data': bc,
                'branch': branch.name,
                'author': author
            }

    contributors['total'] = len(contributors['data'])
    for contributor_id in contributors['data']:
        contributor = contributors['data'][contributor_id]
        c_stats = {
            'id': contributor_id,
            'name': contributor['info'].name,
            'login': contributor['info'].login,
            'num_branches': len(contributor['branches']),
            'num_commits': len(contributor['commits']),
            'total_additions': 0,
            'total_deletions': 0
        }

        for cc in contributor['commits']:
            commit_data = contributor['commits'][cc]
            c_stats['total_additions'] += commit_data.stats.additions
            c_stats['total_deletions'] += commit_data.stats.deletions
        contributors['contributors'].append(c_stats)

    runs = {
        'data': {},
        'total': 0,
        'last': None,
        'workflows': {}
    }

    logs = None
    for wr in repo.get_workflow_runs():
        logs_req = requests.get(wr.logs_url, headers=wr.raw_headers)
        if logs_req.status_code == 200:
            logs = logs_req.content

    stats = {
        'branches': branches_stats,
        'commits': commits_data,
        'contributors': contributors,
        'runs': runs,
        'logs': logs
    }

    # To close connections after use
    client.close()

    return stats


def export_files(repo: Repository, export_prefix: str, path_filter: str = None, extension_filter: str = None):
    if path_filter is not None:
        files = repo.get_contents(path_filter)
    else:
        files = repo.get_contents()

    for file in files:
        if extension_filter is not None and file.name.endswith(extension_filter):
            target_path = os.path.abspath(os.path.join(export_prefix, f'{repo.name}__{file.name}'))
            _save_file(repo, file, target_path)
            print(file.name)
