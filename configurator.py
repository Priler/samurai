from configparser import ConfigParser, SectionProxy

class Config:
    pass

class ConfigSection:
    def __init__(self, section: SectionProxy, items_type: str):
        for key in section:
            if items_type == "string":
                self.__setattr__(key, section[key])
            elif items_type == "int":
                try:
                    self.__setattr__(key, section.getint(key))
                except ValueError:
                    print(f'Could not convert option [{section.name}] -> "{key}" to int')
                    raise


# Global config object
config = Config()

def check_config_file(filename: str) -> bool:
    required_structure = {
        "bot": ["owner", "token", "language"],
        "groups": ["main", "reports", "new_users_nomedia"]
    }

    global config
    parser = ConfigParser()
    parser.read(filename)

    # Check required sections and options in them
    if len(parser.sections()) == 0:
        print("Config file missing or empty")
        return False
    for section in required_structure.keys():
        if section not in parser.sections():
            print(f'Missing section "{section}" in config file')
            return False
        for option in required_structure[section]:
            if option not in parser[section]:
                print(f'Missing option "{option}" in section "{section}" of config file')
                return False

    # Read again, now create Config
    objects_type = {"bot": "string", "groups": "int"}
    for section in parser.sections():
        try:
            config.__setattr__(section, ConfigSection(parser[section], items_type=objects_type[section]))
        except ValueError:
            return False

    return True