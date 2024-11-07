# teaching_utils
Tools for teaching


# Quick start

The project use [polylith architecture](https://polylith.gitbook.io/polylith) managed with python [Poetry tool](). 
A good reference documentation on the basics of polylith architecture in Python is [Python tools for the Polytith Architecture](https://davidvujic.github.io/python-polylith-docs/).


## Install

The simplest way to use those tools is to work with the source code, and add a **development** file to play with the tools. Some examples are provided that correspond to
particular needs of different subjects. A **JetBrains PyCharm** configuration folder is provided to use with this repository.

### Clone the repository
Clone the git repository to a local folder
```bash
git clone https://github.com/xbaro/teaching_utils.git
```

### Install dependencies
Dependencies are managed by poetry. Ensure that you have poetry client installed on your system:
```bash
$ poetry --version
Poetry (vesion 1.8.3)
```
Instructions on how to install Poetry can be found [here.](https://python-poetry.org/docs/#installation)

Install all dependencies:

```bash
poetry install
```

If you plan to develop new code, you can include development dependencies:

```bash
poetry install --with dev
``` 

The project is configured to create a virtual environment **.venv** locally on the project folder.

## Configuration

Configuration options can be provided using a **.env** file. A sample configuration file **env_sample** is provided with
most of the configuration options. Check the configuration options section or the config component for more information.

Make a copy of the sample file:
```bash
cp env_sample .env
```

Modify required values on the **.env** file.

# Available modules
TODO: List all available modules in the library 

# Configuration options

This section describes the most common configuration options:

- EXPORT_PATH: Path where data is exported. By default, **_data** folder is used.
- GITHUB_TOKEN: GitHub application token to access GH repositories for massive download or statistics retrieval.
