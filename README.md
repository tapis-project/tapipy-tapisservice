Tapipy plugin granting Tapis service functionality using `import tapisservice`.


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

