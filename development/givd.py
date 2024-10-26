import logging
from teaching_utils import teaching_lib

logger = logging.getLogger(__name__)

if __name__ == '__main__':

    # logging.basicConfig(filename='myapp.log', level=logging.INFO)
    logging.basicConfig(level=logging.INFO)
    # logging.basicConfig(level=logging.DEBUG)

    repositories = teaching_lib.repository.CodeReposotorySet()
    repositories.load_repositories('GiVD2023/p2-zbtoy-b', 1,9)

    #repositories.clone_all(force=False)

    #repositories.export_files('./_data/export_shaders/', 'resources/GPUshaders', 'glsl')

    repositories.print_stats()
