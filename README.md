# tapisservice - Tapis V3 Python Service SDK
[![PyPI version](https://img.shields.io/pypi/v/tapisservice.svg)](https://pypi.org/project/tapisservice/)
[![GitHub tag (latest by date)](https://img.shields.io/github/v/tag/tapis-project/tapipy-tapisservice?label=git%20tag&sort=semver)](https://github.com/tapis-project/tapipy-tapisservice/tags)
[![Flaskbase Docker Image](https://img.shields.io/docker/v/tapis/flaskbase?label=image&sort=semver)](https://hub.docker.com/r/tapis/flaskbase/tags)
[![docs](https://img.shields.io/badge/docs-grey)](https://tapis.readthedocs.io/en/latest/technical/pythondev.html#tapisservice-user-guide)
[![live-docs](https://img.shields.io/badge/live--docs-grey)](https://tapis-project.github.io/live-docs/)

Tapipy plugin granting Tapis service functionality using `import tapisservice`.

Tapis python services use tapisservice via pypi or by basing images off of `flaskbase` (`Dockerfile-flask`), an image made from this repo with latest tapipy, tapisservice, and some Flask oriented libraries.

`Dockerfile-fastapi` exists, but is not a pushed image. It is oriented towards Fastapi.

## Automated Builds with Make and Poetry
This repository includes a Makefile to automate tasks such as building the images and running tests.
It depends on Poetry; see the docs for installing on your platform: https://python-poetry.org/docs/

Note: On Ubunut 20 LTS (and maybe other platforms?) you might hit an issue trying to run the `poetry build` 
command with your version of virtualenv; see this issue: https://github.com/python-poetry/poetry/issues/2972

The workaround, as described in the issue, is to remove the version of virtualenv bundled with Ubuntu and install
it with pip:

```
 $ sudo apt remove --purge python3-virtualenv virtualenv
 $ sudo apt install python3-pip   # if necessary 
 $ pip3 install -U virtualenv
```

## Running the Tests

In order to run the tests, you will need to populate the `config-dev-develop.json` file within the `tests` with the service password for `abaco` in develop. If you do not know how to get that password, ask for help on the tacc-cloud slack team.

