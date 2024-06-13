import os
from os import environ
from dotenv import dotenv_values

class Config:

    def __init__(self):
        settings = {
            **dotenv_values(".env.shared"),  # load shared development variables
            **dotenv_values(".env.secret"),  # load sensitive variables
            **dotenv_values(".env"),  # load shared development variables
            **os.environ,  # override loaded values with environment variables
        }
        # setup non secret config variables here
        self.public = "public"
        [setattr(self, key, value) for key, value in settings.items()]

    def __getattr__(self, item):
        attr = environ.get(item.upper())
        setattr(self, item, attr) if attr is not None else ...  # this is not really necessary
        return attr

    GITHUB_TOKEN = 'invalid'
    EXPORT_PATH = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '_data'))


settings = Config()
