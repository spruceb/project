import csv
import json
import os
import os.path
from datetime import timedelta
import pprint
import pathlib
import subprocess
import shutil

from date_point import DatePoint, Timeframe
from utilities import current_directory
from python_utilities import Enum

class Manager:
    """Base class for various resource managers"""

    @classmethod
    def default(cls):
        """The default serialized value for this class"""
        pass

    @classmethod
    def setup(cls):
        """The method that sets up system, environment variables, files,
        etc before first initialization"""
        pass

    def save(self):
        """Writes an instance to its persistence location in a standard ways

        May not be defined if another class is responsible for the persistence, i.e.
        writes the frozen instance to a file of its choosing"""
        pass

    @classmethod
    def to_dict(cls, **kwargs):
        """Given the keyword arguments, constructs the desired dictionary"""
        pass

    def freeze(self):
        """Returns the dictionary form of an instance"""
        pass

    @classmethod
    def unfreeze(cls, **kwargs):
        """Returns an instance from a configuration dictionary"""
        pass

    def configure(self, **kwargs):
        """Sets instance variables from a dict"""
        pass

    @classmethod
    def validate(cls, location):
        """Checks that the given location has had setup called in it"""
        pass



class FileManager(Manager):
    """General wrapper for file access and modification. Deals with backups"""

    def __init__(self, directory, backups=True):
        self.directory = os.path.realpath(directory)
        self.backups = backups

    @classmethod
    def setup(cls, backups=True, directory=None):
        if not backups:
            return
        with current_directory(directory) as directory:
            if shutil.which('git') is None:
                raise EnvironmentError('Git is not installed')
            is_repo = subprocess.run(['git', 'rev-parse', '--is-inside-work-dir'],
                                 stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            if is_repo.returncode != 0: # isn't repo
                init = subprocess.run(['git', 'init'], check=True)
                if init.returncode != 0:
                    raise EnvironmentError('Git init failed')
            # assumed to have a valid repo at this point


class DataManager:
    """Wraps the mechanism for persisting and querying work dates and times

    The main features of this program rely on storage of dates and times during
    which personal project work has take place. The actual mechanism for
    storing this data is abstracted from the rest of the program. Here it is
    a simple `csv` file, with 'frozen' DatePoints stored in it.
    """
    def __init__(self, config, path, data_file):
        self.data_filepath = os.path.join(path, data_file)
        self.config = config
        self._date_list = None
        self._file_modified = True

    @classmethod
    def default(cls):
        """Return the default init arguments to be passed in by Config"""
        return {'data_file': 'data.csv'}

    @classmethod
    def setup(cls, path, data_file, **kwargs):
        """Perform the necessary initial setup for the data

        Currently just makes the data file (a csv)
        """
        data_filepath = os.path.join(path, data_file)
        if not os.path.isfile(data_filepath):
            with open(data_filepath, 'w'):
                pass

    def add_date(self, date):
        """Append a new DatePoint to the date list"""
        with open(self.data_filepath, 'a', newline='') as writef:
            writer = csv.writer(writef)
            writer.writerow([date.freeze()])
        self._file_modified = True

    @property
    def date_list(self):
        """Get the list of DatePoints this manager stores"""
        if self._date_list is None or self._file_modified:
            with open(self.data_filepath, 'r', newline='') as reader:
                reader = csv.reader(reader)
                self._date_list = [DatePoint.unfreeze(date[0]) for date in reader]
            self._file_modified = False
        return self._date_list

    def save(self):
        """Persist any data that may have changed during runtime

        Since `add_data` is the only mutating method and it persists the data,
        this doesn't need to do anything (as of yet).
        """
        pass

class CacheManager:
    """Manager for cached data, i.e. calculated/temporary data

    Not used extensively in `Project`, however will become more relevant as
    more extensive statistics/information is made available.
    """
    def __init__(self, config, cache_filename, path):
        """Create a new cache manager from the filepath"""
        self.config = config
        self.cache_path = os.path.join(path, cache_filename)
        self._cache = None

    @property
    def cache(self):
        """Lazy loading of the cache data"""
        if self._cache is None:
            with open(self.cache_path, 'r') as cache_file:
                self._cache = json.load(cache_file)
        return self._cache

    @classmethod
    def default(cls):
        """Return the default init arguments to be passed in by Config"""
        return {'cache_filename': 'cache.json'}

    @classmethod
    def setup(cls, path, cache_filename, **kwargs):
        """Perform the necessary initial setup for the data

        Makes the cache file and initializes the used values to None
        """
        cache_filepath = os.path.join(path, cache_filename)
        if not os.path.isfile(cache_filepath):
            with open(cache_filepath, 'w') as cache_file:
                json.dump({'start_time': None}, cache_file)

    @property
    def start_time(self):
        """Get the start time of the current timerange (if it exists)"""
        start_time = self.cache.get('start_time')
        if start_time is not None:
            return DatePoint.unfreeze(start_time)

    @start_time.setter
    def start_time(self, value):
        """Set the start time for a new timerange"""
        if value is not None:
            value = value.freeze()
        self.cache['start_time'] = value

    def save(self):
        """Persist any data that may have changed during runtime"""
        if self._cache is not None:
            with open(self.cache_path, 'w') as cache_file:
                json.dump(self._cache, cache_file)

class ConfigLocations(Enum):
    """Enum for the different types of places config can be stored"""
    config = () # global config, i.e. in ~/.config
    local = () # local to a specific directory, so /some/path/.project
    env = () # a specific global location given by an environment variable


class ConfigManager:
    """Manager for the configuration of this project

    Abstraction for a persistent configuration. Saves the filepaths of the
    other necessary files as well. Currently the 'bootstrap' point, i.e. a path
    to this file is necessary to find or create the rest of the data. This will
    later be used to store more user-specific config as functionality is
    expanded.
    """

    # directory name to use when making a config dir inside the current dir
    LOCAL_DIRNAME = '.project'
    # environment variable to check for a user-specified config location
    ENVIRONMENT_OVERRIDE = 'PROJECT_TRACKER_HOME'
    # directory name for a "global" config in a single location
    GLOBAL_DIRNAME = 'project'
    # config directory to put the global config into (currently ~/.config)
    DEFAULT_GLOBAL_LOCATION = os.path.expanduser('~/.config')
    # full path for a global config folder
    GLOBAL_DIRPATH = os.path.join(DEFAULT_GLOBAL_LOCATION, GLOBAL_DIRNAME)
    # directory to keep the cache in
    CACHE_DIRNAME = 'cache'
    # directory to keep the data in
    DATA_DIRNAME = 'data'
    # filename for the actual config file
    CONFIG_FILENAME = 'project.config'

    def __init__(self, data_config, cache_config, timeframe=None,
                 finished_threshold=None):
        """Create a new config manager, checking all the default locations

        This uses the `_config_location` class method to try to find an
        existing config location. If no such location exists, or if the data
        there is unreadable, raises an error. Otherwise also initializes the
        data and cache with the init data they store into config (on setup
        or during normal running).
        """
        self.config_dirpath, self.location_type = self._config_location()
        self.config_filepath = self._config_filepath()
        if timeframe is None:
            timeframe = Timeframe.day
        self.timeframe = timeframe
        if finished_threshold is None:
            finished_threshold = timedelta(hours=1)
        self.finished_threshold = finished_threshold
        self._data_config = data_config
        self._cache_config = cache_config
        self.data = DataManager(self, **data_config)
        self.cache = CacheManager(self, **cache_config)

    @classmethod
    def to_dict(cls, data_config=None, cache_config=None, timeframe=None,
                threshold=None):
        config_dict = {}
        if data_config is not None:
            config_dict['data'] = data_config
        if cache_config is not None:
            config_dict['cache'] = cache_config
        if timeframe is not None:
            config_dict['timeframe'] = timeframe
        if threshold is not None:
            config_dict['finished_threshold'] = threshold
        return config_dict

    @classmethod
    def default(cls):
        return {
            'timeframe': Timeframe.day,
            'finished_threshold': 3600
        }

    def freeze(self):
        return self.to_dict(self._data_config,
                            self._cache_config,
                            self.timeframe,
                            self.finished_threshold.total_seconds())

    @classmethod
    def unfreeze(cls, frozen):
        """Initialize from a frozen dict"""
        timeframe = frozen.get('timeframe')
        finished_threshold = frozen.get('finished_threshold')
        if finished_threshold is not None:
            finished_threshold = timedelta(seconds=finished_threshold)
        # if there's no data or cache config an error has occurred
        data_config = frozen['data']
        cache_config = frozen['cache']
        return cls(data_config,
                   cache_config,
                   timeframe,
                   finished_threshold)

    @classmethod
    def from_file(cls):
        dirpath = cls._config_location()
        filepath = cls._config_filepath()
        try:
            with open(filepath, 'r') as config_file:
                result = json.load(config_file)
                if result is None:
                    raise ValueError('Invalid config')
                return result
        except json.decoder.JSONDecodeError:
            raise ValueError('Invalid config')

    @classmethod
    def find_config(cls):
        config = cls.from_file()
        return cls.unfreeze(config)

    @classmethod
    def save_dict(cls, config_dict):
        filepath = cls._config_filepath()
        with open(filepath, 'r') as config_file:
            contents_dict = json.load(config_file)
            if contents_dict != config_dict:
                print('WARNING: overwriting changed data!')
                print('Pre-overwrite file state:')
                pprint.pprint(contents_dict)
                print('Overwriting with:')
                pprint.pprint(config_dict)
        with open(filepath, 'w') as config_file:
            json.dump(config_dict, config_file)

    @classmethod
    def merge_config(cls, config_dict):
        with open(cls._config_filepath(), 'r') as config_file:
            old_config = json.load(config_file)
        old_config.update(config_dict)
        cls.save_dict(old_config)

    def save(self):
        self.save_dict(self.freeze())
        self.data.save()
        self.cache.save()

    @classmethod
    def configure(cls, data_config=None, cache_config=None,
                  timeframe=None, threshold=None):
        config_dict = cls.to_dict(data_config, cache_config, timeframe, threshold)
        if not os.path.isfile(cls._config_filepath()):
            with open(cls._config_filepath(), 'w') as config_file:
                json.dump(config_dict, config_file)
        else:
            cls.merge_config(config_dict)

    @classmethod
    def _find_local(cls):
        current_dir = os.path.expanduser(os.getcwd())
        local_dir = os.path.join(current_dir, cls.LOCAL_DIRNAME)
        if os.path.isdir(local_dir):
            return os.path.realpath(local_dir)
        else:
            while (not os.path.isdir(local_dir) and
                    current_dir != os.path.dirname(current_dir)):
                current_dir = os.path.dirname(current_dir)
                local_dir = os.path.join(current_dir, cls.LOCAL_DIRNAME)
            if os.path.isdir(local_dir):
                return (os.path.realpath(local_dir), ConfigLocations.local)

    @classmethod
    def _find_global(cls):
        if os.path.isdir(cls.GLOBAL_DIRPATH):
            return os.path.realpath(cls.GLOBAL_DIRPATH)

    @classmethod
    def _find_env(cls):
        path = os.environ.get(cls.ENVIRONMENT_OVERRIDE)
        if path is not None and os.path.isdir(path):
            return os.path.realpath(path)

    @classmethod
    def _config_location(cls):
        """Check and return possible config locations in preference order

        Tries to look at local, then environment-variable set, then default
        global config locations. If none are found raises an error.
        """
        local = cls._find_local()
        if local is not None:
            return local, ConfigLocations.local
        global_path = cls._find_global()
        if global_path is not None:
            return global_path, ConfigLocations.config
        env = cls._find_env()
        if env is not None:
            return env, ConfigLocations.env
        raise FileNotFoundError("Can't find config files")

    @classmethod
    def _config_dirpath(cls):
        return cls._config_location()[0]

    @classmethod
    def _config_location_type(cls):
        return cls._config_location()[1]

    @classmethod
    def _config_filepath(cls):
        return os.path.join(cls._config_dirpath(), cls.CONFIG_FILENAME)

    @classmethod
    def validate(cls, config_location):
        """Check that a config location was correctly set up

        Not currently in use, needs slightly more thought and implementations
        in Cache and Data.
        """
        if not os.path.isdir(config_location):
            return False
        config_path = os.path.join(config_location, cls.CONFIG_FILENAME)
        if not os.path.isfile(config_path):
            return False
        cache_dir = os.path.join(config_location, cls.CACHE_DIRNAME)
        if not os.path.isdir(cache_dir):
            return False
        if not CacheManager.validate(cache_dir):
            return False
        data_path = os.path.join(config_location, cls.DATA_DIRNAME)
        if not os.path.isdir(cache_dir):
            return False
        if not DataManager.validate(data_path):
            return False

    @classmethod
    def create_config_location(cls, config_location_type,
                               make_intermediate=True, dir_path=None):
        """Make the directory required for certain config locations"""
        makedir = os.makedirs if make_intermediate else os.mkdir
        if config_location_type == ConfigLocations.local:
            makedir(os.path.join(dir_path, cls.LOCAL_DIRNAME))
        elif config_location_type == ConfigLocations.env:
            if env_path is not None:
                makedir(env_path)
            else:
                raise ValueError('Must give env_path for env config type')
        elif config_location_type == ConfigLocations.config:
            makedir(cls.GLOBAL_DIRPATH)

    @classmethod
    def setup(cls, config_location_type=None, filepath=None):
        """Set up the file structures required to run from scratch

        Can be given a type of config location to set up. Does not
        currently overwrite existing files. Not overwriting may cause
        some issues, as proper validation is not yet done so this could
        leave incomplete structures untouched. However it prevents data
        loss until more complete validation is completed.

        This ensures a 'config location' based on the argument exists.
        Then inside it it creates a file structure consisting of a
        config file, a cache folder, and a data folder. Data and Cache
        setups are called on their respective folders. The default
        initialization arguments for Data and Cache are stored in the
        config file. These arguments are meant to potentially be
        modified by Data and Cache as needed and effectively act as a
        "data store" for them.
        """
        if config_location_type is None:
            config_location_type = ConfigLocations.config
        try:
            config_dir = cls._config_dirpath()
            if cls._config_location_type() != config_location_type:
                raise FileNotFoundError()
        except FileNotFoundError:
            cls.create_config_location(config_location_type, dir_path=filepath)
            config_dir = cls._config_dirpath()
        config_filepath = cls._config_filepath()
        if os.path.isfile(config_filepath):
            try:
                with open(config_filepath, 'r') as config_file:
                    config = json.load(config_file)
                    data_init = config['data']
                    cache_init = config['cache']
            except (json.decoder.JSONDecodeError, KeyError):
                print('Invalid config found. Not overwriting.')
                return
        else:
            data_init = DataManager.default()
            cache_init = CacheManager.default()
            data_path = os.path.join(config_dir, cls.DATA_DIRNAME)
            cache_path = os.path.join(config_dir, cls.CACHE_DIRNAME)
            if not os.path.isdir(cache_path):
                os.mkdir(cache_path)
            if not os.path.isdir(data_path):
                os.mkdir(data_path)
            cache_init['path'] = cache_path
            data_init['path'] = data_path

            cls.configure(data_init, cache_init)
        DataManager.setup(**data_init)
        CacheManager.setup(**cache_init)
