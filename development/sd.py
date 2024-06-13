import logging
from teaching_utils import teaching_lib

logger = logging.getLogger(__name__)

if __name__ == '__main__':

    # logging.basicConfig(filename='myapp.log', level=logging.INFO)
    logging.basicConfig(level=logging.DEBUG)
    #logging.basicConfig(level=logging.INFO)

    repositories = teaching_lib.repository.CodeReposotorySet()
    #repositories.load_repositories('SoftwareDistribuitUB-2024/practica2-b', 1,20)

    # repositories.clone_all(force=False)

    #test_repo = repositories[0]

    repo_1 = repositories.get_repository('SoftwareDistribuitUB-2024/practica2-b', 1)

    repo_stats = repo_1.get_stats()

    print(repo_stats)
