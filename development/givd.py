import logging
from teaching_utils import ghrepos

logger = logging.getLogger(__name__)

if __name__ == '__main__':

    # logging.basicConfig(filename='myapp.log', level=logging.INFO)
    logging.basicConfig(level=logging.DEBUG)

    repos = ghrepos.get_repository_range('GiVD2023/p2-zbtoy-b', 1,9)

    for repo in repos:
        target_path = ghrepos.clone_repository(repo)

        print(target_path)
