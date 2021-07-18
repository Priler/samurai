from configparser import ConfigParser
from easydict import EasyDict as edict
import logging

config = edict()

def make_config(filename):
    parser = ConfigParser()
    parser.read(filename)

    if not parser.sections():
        return False

    for section in parser.sections():
        config[section] = edict()

        for key, value in parser.items(section):
            config[section][key] = value

    return True