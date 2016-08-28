import csv
import json
import os
import os.path
from shutil import rmtree

from date_point import DatePoint

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
    def setup(cls, overwrite, path, data_file, **kwargs):
        """Perform the necessary initial setup for the data

        Currently just makes the data file (a csv)
        """
        data_filepath = os.path.join(path, data_file)
        if overwrite or not os.path.isfile(data_filepath):
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

    def save_data(self):
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
    def setup(cls, path, overwrite, cache_filename, **kwargs):
        """Perform the necessary initial setup for the data

        Makes the cache file and initializes the used values to None
        """
        cache_filepath = os.path.join(path, cache_filename)
        if overwrite or not os.path.isfile(cache_filepath):
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

    def save_data(self):
        """Persist any data that may have changed during runtime"""
        if self._cache is not None:
            with open(self.cache_path, 'w') as cache_file:
                json.dump(self._cache, cache_file)

class ConfigLocations:
    """Enum for the different types of places config can be stored"""
    config = 'config' # global config, i.e. in ~/.config
    local = 'local' # local to a specific directory, so /some/path/.project
    env = 'env' # a specific global location given by an environment variable


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

    def __init__(self):
        """Create a new config manager, checking all the default locations

        This uses the `_config_location` class method to try to find an
        existing config location. If no such location exists, or if the data
        there is unreadable, raises an error. Otherwise also initializes the
        data and cache with the init data they store into config (on setup
        or during normal running).
        """
        self.config_path = self._config_location()
        self.config_filepath = os.path.join(self.config_path,
                                            self.CONFIG_FILENAME)
        try:
            with open(self.config_filepath, 'r') as config_file:
                config_string = config_file.read()
                self._backup = config_string
                self._config = json.loads(config_string)
        except json.decoder.JSONDecodeError:
            raise ValueError('Invalid data')
        self.data = DataManager(self, **self.config['data'])
        self.cache = CacheManager(self, **self.config['cache'])

    @property
    def config(self):
        """Get the config dict stored in the config file"""
        return self._config

    @classmethod
    def _config_location(cls):
        """Check and return possible config locations in preference order

        Tries to look at local, then environment-variable set, then default
        global config locations. If none are found raises an error.
        """
        override = os.environ.get(cls.ENVIRONMENT_OVERRIDE)
        if os.path.isdir(cls.LOCAL_DIRNAME):
            result = os.path.expanduser(cls.LOCAL_DIRNAME)
        elif override is not None and os.path.isdir(override):
            result = os.path.expanduser(override)
        elif os.path.isdir(cls.GLOBAL_DIRPATH):
            result = os.path.expanduser(cls.GLOBAL_DIRPATH)
        else:
            raise FileNotFoundError('Config not found')
        return os.path.abspath(result)

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
                               make_intermediate=True, env_path=None):
        """Make the directory required for certain config locations"""
        makedir = os.makedirs if make_intermediate else os.mkdir
        if config_location_type == ConfigLocations.local:
            makedir(cls.LOCAL_DIRNAME)
        elif config_location_type == ConfigLocations.env:
            if env_path is not None:
                makedir(env_path)
            else:
                raise ValueError('Must give env_path for env config type')
        elif config_location_type == ConfigLocations.config:
            makedir(cls.GLOBAL_DIRPATH)

    @classmethod
    def setup(cls, config_location_type=ConfigLocations.config,
              overwrite=True, env_path=None):
        """Set up the file structures required to run from scratch

        Can be given a type of config location to set up, and a flag
        for whether to overwrite existing data. Not overwriting may cause
        some issues, as proper validation is not yet done so this could leave
        incomplete structures untouched.

        This ensures a 'config location' based on the argument exists. Then
        inside it it creates a file structure consisting of a config file,
        a cache folder, and a data folder. Data and Cache setups are called
        on their respective folders. The default initialization arguments for
        Data and Cache are stored in the config file. These arguments are meant
        to potentially be modified by Data and Cache as needed and effectively
        act as a "data store" for them.
        """
        try:
            config_location = cls._config_location()
        except FileNotFoundError:
            cls.create_config_location(config_location_type, env_path)
            config_location = cls._config_location()
        config_filepath = os.path.join(config_location, cls.CONFIG_FILENAME)
        if not overwrite and os.path.isfile(config_filepath):
            with open(config_filepath, 'r') as config_file:
                config = json.load(config_file)
                data_init = config['data']
                cache_init = config['cache']
        else:
            config = {}
            data_init = DataManager.default()
            cache_init = CacheManager.default()
            data_path = os.path.join(config_location, cls.DATA_DIRNAME)
            cache_path = os.path.join(config_location, cls.CACHE_DIRNAME)
            if os.path.isdir(cache_path) and overwrite:
                rmtree(cache_path)
            if not os.path.isdir(cache_path):
                os.mkdir(cache_path)
            if os.path.isdir(data_path) and overwrite:
                rmtree(data_path)
            if not os.path.isdir(data_path):
                os.mkdir(data_path)
            cache_init['path'] = cache_path
            data_init['path'] = data_path
            config['data'] = data_init
            config['cache'] = cache_init
            with open(config_filepath, 'w') as config_file:
                json.dump(config, config_file)
        DataManager.setup(overwrite=overwrite, **data_init)
        CacheManager.setup(overwrite=overwrite, **cache_init)

    def save_data(self):
        """Persist data that may have changed during runtime

        Hooks are in place here for rudimentary 'backups', i.e. figuring
        out what to do if the data in the file has been modified since the
        class was initialized from it. However this is not currently in use.
        """
        if self._config is not None:
            with open(self.config_filepath, 'r') as config_file:
                contents = config_file.read()
            if contents != self._backup:
                pass # do nothing for now, be safer later
            with open(self.config_filepath, 'w') as config_file:
                json.dump(self._config, config_file)
        self.data.save_data()
        self.cache.save_data()
