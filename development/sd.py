import logging
from teaching_utils import teaching_lib

logger = logging.getLogger(__name__)

if __name__ == '__main__':

    import json

    with open('C:\\Users\\xavie\\OneDrive\\Escriptori\\Uptitude_JSON.json', 'r', encoding='utf-8') as answ:
        data = json.load(answ)

    print(data)

    # logging.basicConfig(filename='myapp.log', level=logging.INFO)
    # logging.basicConfig(level=logging.DEBUG)
    logging.basicConfig(level=logging.INFO)

    repositories = teaching_lib.repository.CodeReposotorySet()
    repositories.load_repositories('SoftwareDistribuitUB-2024/practica2-b', 1, 20)

    # repositories.clone_all(force=False)

    # test_repo = repositories[0]

    # repo_1 = repositories.get_repository('SoftwareDistribuitUB-2024/practica2-b', 3)

    # repo_stats = repo_1.get_stats()
    repositories.print_stats()

    # test_results = repo_1.test('python', './backend')

    # print(repo_stats)
