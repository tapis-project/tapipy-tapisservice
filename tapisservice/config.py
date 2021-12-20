"""
Validates service configuration based on jsonschema for any Tapis flask API. The base schema for all services is
configschema.json, in this repo, but services can update or override the schema definition with

"""
import json
import jsonschema
import os
import re

from tapisservice.errors import BaseTapisError

HERE = os.path.dirname(os.path.abspath(__file__))

# load the base api schema -
schema = json.load(open(os.path.join(HERE, 'configschema.json'), 'r'))

# try to load an api-specific schema
service_configschema_path = os.environ.get('TAPIS_CONFIGSCHEMA_PATH', '/home/tapis/configschema.json')
try:
    api_schema = json.load(open(service_configschema_path, 'r'))
except Exception as e:
    # at this point, logging is not set up yet, so we just print the message to the screen and hope for the best:
    msg = f'ERROR, improperly configured service. Could not load configschema.json found; ' \
          f'looked in {service_configschema_path}. Aborting. Exception: {e}'
    print(msg)
    raise BaseTapisError(msg)

# ----- Combine the service config schema with the base config schema -----
# In what follows, we take a manual approach, but instead we could also have the service schema use the allOf
# feature to pull in the base schema; cf., https://github.com/json-schema-org/json-schema-spec/issues/348
# The downside with that would be that it is up to each service to include the base schema properly.

# 1) we override properties defined in the base schema with properties defined in the service schema
api_properties = api_schema.get('properties')
if api_properties and type(api_properties) == dict:
    schema['properties'].update(api_properties)

# 2) we extend the required properties with those specified as required by the API -
api_required = api_schema.get('required')
if api_required and type(api_required) == list:
    schema['required'].extend(api_required)


# extend the default jsonschema validator to supply/modify the instance with default values supplied in the
# schema definition. very surprising that this is not the default behavior;
# see: https://python-jsonschema.readthedocs.io/en/stable/faq/
def extend_with_default(validator_class):
    validate_properties = validator_class.VALIDATORS["properties"]

    def set_defaults(validator, properties, instance, schema):
        for property, subschema in properties.items():
            default_set = False
            # add support for environment variables for type string variables
            if subschema["type"] == "string":
                # environment variables override any default set in the jsonschema
                if os.environ.get(property):
                    default_set = True
                    instance.setdefault(property, os.environ.get(property))
            # check for a default supplied in the jsonschem doc
            if "default" in subschema and not default_set:
                instance.setdefault(property, subschema["default"])

        for error in validate_properties(
                validator, properties, instance, schema,
        ):
            yield error

    return jsonschema.validators.extend(
        validator_class, {"properties": set_defaults},
    )


DefaultValidatingDraft7Validator = extend_with_default(jsonschema.Draft7Validator)


def match_and_replace_env_variables(txt_to_match: str) -> str:
    """
    A function to look through a str for any instances of '$env{ * }. If an instance is located
    the interior of the braces is compared to existing environment variables. If the variable exists
    it is then subbed into the text allow users to substitute environment variables directly into
    their configs.
    """
    environ_regex_pattern = re.compile(r'\$env\{(.*?)\}')
    pattern_matches = environ_regex_pattern.findall(txt_to_match)
    for matched_var in pattern_matches:
        if os.environ.get(matched_var):
            txt_to_match = txt_to_match.replace(f"$env{{{matched_var}}}", os.environ.get(matched_var))
    return txt_to_match


# now that we have the required API config schema, we need to validate it against the actual configs supplied
# to the service.

class Config(dict):
    """
    A class containing an API service's config, as a Python dictionary, with getattr and setattr defined to make
    attribute access work like a "normal" object. One should import the singleton Conf directly from this module.

    Example usage:
    ~~~~~~~~~~~~~~
    from config import conf   <-- all service configs loaded and validated against the
    conf.some_key <-- AttributeError raised if some_key (optional) config not defined
    """

    def __getattr__(self, key):
        # returning an AttributeError is important for making deepcopy work. cf.,
        # http://stackoverflow.com/questions/25977996/supporting-the-deep-copy-operation-on-a-custom-class
        try:
            return self[key]
        except KeyError as e:
            raise AttributeError(e)

    def __setattr__(self, key, value):
        self[key] = value

    @classmethod
    def get_config_from_file(self):
        """
        Reads service config from a JSON file
        :return:
        """
        path = os.environ.get('TAPIS_CONFIG_PATH', '/home/tapis/config.json')
        if os.path.exists(path):
            try:
                with open(path, 'r') as config_raw:
                    config_txt = config_raw.read()
                    config_with_env = match_and_replace_env_variables(config_txt)
                return json.loads(config_with_env)
            except Exception as e:
                msg = f'Could not load configs from JSON file at: {path}. exception: {e}'
                print(msg)
                raise BaseTapisError(msg)

    @classmethod
    def load_config(cls):
        """
        Load the config from various places, including a JSON file and environment variables.
        :return:
        """
        file_config = cls.get_config_from_file()
        # validate config against schema definition
        try:
            # jsonschema.validate(instance=file_config, schema=schema)
            DefaultValidatingDraft7Validator(schema).validate(file_config)
        except jsonschema.SchemaError as e:
            msg = f'Invalid service config: exception: {e}'
            print(msg)
            raise BaseTapisError(msg)
        return file_config


conf = Config(Config.load_config())