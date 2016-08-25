#!/usr/bin/env python3
"""Track progress in personal projects and keep motivated with streaks

The idea of this program is 'one hour a day, every day' on personal projects.
One hour is a time period in which actual work can be accomplished, i.e. not
just getting into and out of flow state but really doing work in flow states.
It is also an amount of time that can almost always be fit in to any schedule.

A primary problem with personal projects is their tendency to remain
unfinished. While 'one hour' cannot totally alleviate this (you could always
just switch randomly to new projects), it does help stop the failure mode of
simply being very tired one day and feeling justified in giving yourself a
break. This often cascades into weeks or months of 'break'. Keeping tangible
indicators of *streaks*, not total time (or not primarily total time), prevents
the feeling of "I'll make up with lots of time on the weekends", which
invariably falls though the cracks. However keeping track of specific timings
is also useful, and so is supported as well.

WIP
"""
import atexit
import bisect
import csv
import datetime
import json
import os
import os.path
from shutil import rmtree

import arrow
import click


class Timeframe:
    """Enum for possible units of time"""
    year = 'year'
    month = 'month'
    week = 'week'
    day = 'day'
    hour = 'hour'
    minute = 'minute'
    second = 'second'


class DatePoint:
    """Wrapper around dates and date ranges"""

    RANGE_INDICATORS = ('0', '1')
    SEPERATOR_CHAR = ' '

    def __init__(self, first_date, second_date=None):
        """Create a new DatePoint from one or a pair of objects

        Possibilities: strings, Arrow dates, datetimes, DatePoint objects
        """
        self._is_range = second_date is not None
        if isinstance(first_date, DatePoint):
            self._first_date = first_date._first_date
            if first_date.is_range:
                self._is_range = True
                self._second_date = first_date._second_date
        else:
            self._first_date = arrow.get(first_date)

        if isinstance(second_date, DatePoint):
            self._second_date = second_date._first_date
        elif second_date is not None:
            self._second_date = arrow.get(second_date)

    @property
    def is_range(self):
        """Whether this is a range of dates or a single date"""
        return self._is_range

    def freeze(self):
        """Return serialized string or byte version of self"""
        header = self.RANGE_INDICATORS[self.is_range]
        body = str(self._first_date)
        if self.is_range:
            body += self.SEPERATOR_CHAR + str(self._second_date)
        return header + body

    @classmethod
    def unfreeze(cls, freezed):
        """Create a DatePoint object from a frozen serialization of one"""
        try:
            is_range = cls.RANGE_INDICATORS.index(freezed[0])
        except ValueError:
            return
        first_date = freezed[1:]
        second_date = None
        if is_range:
            first_date, second_date = first_date.split(cls.SEPERATOR_CHAR)
        return cls(first_date, second_date)

    @classmethod
    def now(cls):
        """Get the current point in time as a DatePoint"""
        return cls(arrow.now())

    def ordinal(self, timeframe=Timeframe.day, use_start=True):
        """Get an absolute version of the specified timeframe

        That is, if the timeframe is years then the year, but if it's months
        then the number of months since 0 C.E. rather than which month it is in
        the given year. Likewise if days is the timeframe, then the Gregorian
        total number of days, and if seconds then the current UNIX epoch.

        These cannot be translated into other formats. Rather they are meant
        for comparison, for telling exactly the difference in whatever unit
        there are between two DatePoints
        """
        date = self._first_date if use_start else self._second_date
        if timeframe == Timeframe.year:
            return date.year
        elif timeframe == Timeframe.month:
            return date.year * 12 + date.month
        elif timeframe == Timeframe.week:
            iso = date.isocalender()
            return iso[1]
        elif timeframe == Timeframe.day:
            return date.toordinal()
        elif timeframe == Timeframe.hour:
            return date.toordinal() * 24 + date.hour
        elif timeframe == Timeframe.minute:
            return date.timestamp // 60
        elif timeframe == Timeframe.second:
            return date.timestamp

    def same(self, other, timeframe=Timeframe.day):
        """If two DatePoints occurred in the same timeframe"""
        return self.ordinal(timeframe) == other.ordinal(timeframe)

    def consecutive(self, other, timeframe=Timeframe.day):
        """If two DatePoints occurred on consecutive timeframes"""
        return abs(self.ordinal(timeframe) - other.ordinal(timeframe)) == 1

    def within_streak(self, other, timeframe=Timeframe.day):
        """If two DatePoints have the same or consecutive timeframes"""
        return self.same(other, timeframe) or self.consecutive(other, timeframe)

    def after(self, other, timeframe=Timeframe.day):
        """If this DatePoint's timeframe is after the others"""
        return self.ordinal(timeframe) > other.ordinal(timeframe)

    def before(self, other, timeframe=Timeframe.day):
        """If this DatePoint's timeframe is before the others"""
        return self.ordinal(timeframe) < other.ordinal(timeframe)

    @property
    def date(self):
        """The 'date' version of this DatePoint, i.e. without time info"""
        return DatePoint(arrow.get(self._first_date.date()))

    @property
    def datetime_date(self):
        """The `datetime.date` of this DatePoint"""
        return self._first_date.date()

    @property
    def time(self):
        """The `datetime.time` of this DatePoint"""
        return self._first_date.time()

    @property
    def arrow(self):
        """The `arrow.Arrow` version of this DatePoint"""
        return self._first_date

    @property
    def total_time(self):
        """The timedelta this represents

        If it's not a range, it's considered to represent an hour. This
        information being stored here is probably a bad idea and should
        be decoupled."""
        if self.is_range:
            return self._second_date - self._first_date
        return datetime.timedelta(hours=1)

    def included(self, date_list, timeframe=Timeframe.day):
        """Return whether the timeframe of this date is included in the list"""
        return any(self.same(date, timeframe) for date in date_list)

    def split_range(self, timeframe=Timeframe.day):
        """Split a range that extends over multiple timefames"""
        assert self.is_range
        first = DatePoint(self._first_date, self._first_date.ceil(timeframe))
        second = DatePoint(self._second_date.floor(timeframe),
                           self._second_date)
        return (first, second)

    def __eq__(self, other):
        """Compare to other, equal if dates compare equal"""
        if self._is_range != other._is_range:
            return False
        return (self._first_date == other._first_date and
                self._second_date == other._second_date)

    def __sub__(self, other):
        """Get the difference between two dates as a `timedelta`"""
        return self._first_date - other._first_date

    def __gt__(self, other):
        """Check whether this date comes after another (no timeframe)"""
        return self._first_date > other._first_date

    def __str__(self):
        """Get this DatePoint formatted as a string"""
        if self.is_range:
            return '{} to {}'.format(self._first_date, self._second_date)
        return str(self._first_date)

    def __repr__(self):
        """Get a representation of this DatePoint"""
        return self.freeze()


class DayGroup(DatePoint):
    """A group of DatePoints in a single day

    A DayGroup inherits from DatePoint and in most ways can be treated
    like one. It differs in that it stores a list of DatePoints rather than
    one or two `arrow.Arrow` dates. It uses the `date` (i.e. the day) of the
    first component date for all DatePoint operations that require a
    `_first_date`.

    Used in various places in `Project` when the individual DatePoints in a day
    aren't as relevant as the aggregate day information.
    """
    def __init__(self, date_list):
        """Create a new DayGroup from a list of dates in the same day"""
        assert len(date_list) > 0
        self.date_list = date_list
        self.day = date_list[0].date

    @classmethod
    def group_days(cls, datepoint_list):
        """Group a list of DatePoints by the day they occurred on

        This will return a list of lists. Each of those lists could be
        validly used to construct a DayGroup.
        """
        return [cls(dates) for dates in
                binary_groupby(datepoint_list, lambda x, y: x.same(y))]

    @property
    def total_time(self):
        """Get the total time from all component DatePoints"""
        return sum((date.total_time for date in self.date_list),
                   datetime.timedelta())

    def ordinal(self, timeframe=None, use_start=None):
        """Gets the 'prototypical' day's ordinal value

        This will not work/compare correctly with DatePoint methods using
        different timeframes. This entire class is currently tied to days.
        """
        return self.day.ordinal(timeframe=Timeframe.day)

    @property
    def is_range(self):
        """DayGroups are not ranges for the purpose of DatePoint methods"""
        return False

    @property
    def _first_date(self):
        """Return prototypical day for DatePoint compatibility"""
        return self.day._first_date


def binary_groupby(iterator, key):
    """Return the iterator split based on a boolean 'streak' function"""
    iterator = iter(iterator)
    last_item = next(iterator)
    result_list = [last_item]
    for item in iterator:
        if key(last_item, item):
            result_list.append(item)
        else:
            if result_list:
                yield result_list
            result_list = [item]
        last_item = item
    if result_list:
        yield result_list
# TODO: below classes can clearly be abstracted down the line


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


class Project:
    """Provides the programmatic interface of the function

    This is not the 'user interface', or even the 'MVC controller'. Rather
    it's the 'API' of the application, the high level set of supported
    operations
    """
    def __init__(self, config, timeframe=Timeframe.day):
        """Create a `Project`"""
        self.config = config
        self.cache = self.config.cache
        self.data = self.config.data
        self.finished_threshold = datetime.timedelta(hours=1)
        self.timeframe = timeframe
        self._last_range = None
        atexit.register(self.close)

    def finish(self):
        """Record this day as finished >= one hour of personal project work"""
        today = DatePoint.now()
        if self.data.date_list:
            last_date = self.data.date_list[-1]
            last_day_finished = self._is_finished(self.day_groups[-1])
            if (today.after(last_date) or
                    today.same(last_date) and not last_day_finished):
                self.data.add_date(today)
                return today
        else:
            self.data.add_date(today)
            return today

    @property
    def day_groups(self):
        """Return the DatePoints grouped into DayGroups"""
        return DayGroup.group_days(self.data.date_list)

    def _is_finished(self, day_group):
        """Check if the time of the DatePoints exceeds completion threshold"""
        return day_group.total_time >= self.finished_threshold

    @property
    def finished_streaks(self):
        """Get list of streaks of DayGroups for consecutive finished days"""
        date_points = (group for group in self.day_groups
                       if self._is_finished(group))
        return list(binary_groupby(date_points, lambda x, y: x.within_streak(y)))

    @property
    def streak(self):
        """Get the length of the last streak ending today or yesterday

        This streak is the 'current streak', i.e. the streak that still has the
        potential to be continued. If there is no such streak then this is 0.
        This will check if enough time was logged in the day, so if there are
        only timeranges that total 40min, it will not be counted as a completed
        day.
        """
        if self.current_streak is None:
            return 0
        return len(self.current_streak)

    @property
    def current_streak(self):
        """Get the current streak if there is one

        If either today or yesterday `_is_finished`, return the streak
        that contains it. Otherwise there is no current streak.
        """
        today = DatePoint.now()
        streaks = self.finished_streaks
        if not streaks or not any(streaks):
            return None
        last_streak = streaks[-1]
        last_entry = last_streak[-1]
        if today.within_streak(last_entry):
            return last_streak
        return None

    @property
    def current_range_time(self):
        """Return the timedelta for the current/most recent 'started' time"""
        if self.start_time is not None:
            return DatePoint.now() - self.start_time
        else:
            return datetime.timedelta()

    @property
    def current_streak_time(self):
        """Get the total time in the current streak"""
        if self.current_streak is None:
            return datetime.timedelta()
        return self.total_time_in(self.current_streak)

    def total_time_on(self, date):
        """Get the total time on a given date"""
        datepoint = DatePoint(date)
        matches = (day for day in self.day_groups if day.same(datepoint))
        try:
            match = next(matches)
        except StopIteration:
            match = None
        if match is None:
            return datetime.timedelta()
        return match.total_time

    @property
    def total_time_today(self):
        """Get the total time spent on the current day"""
        today = DatePoint.now()
        result = self.total_time_on(today)
        return result + self.current_range_time

    @property
    def start_time(self):
        """Get the start time for the current timeframe"""
        return self.cache.start_time

    @start_time.setter
    def start_time(self, value):
        """Set the start time for a new timeframe"""
        self.cache.start_time = value

    def start(self, overwrite=False):
        """Start a new timeframe"""
        now = DatePoint.now()
        if (self.start_time is None or
                not now.same(self.start_time) or overwrite):
            self.start_time = now
            return now

    def stop(self):
        """End the current timeframe"""
        now = DatePoint.now()
        if self.start_time is not None:
            this_range = DatePoint(self.start_time, now)
            if now.same(self.start_time):
                self.data.add_date(this_range)
                self._last_range = this_range
            else:
                first, second = this_range.split_range()
                self.data.add_date(first)
                self.data.add_date(second)
                self._last_range = second
            self.start_time = None
            return now

    def fill_boundries(func):
        """Decorator that defaults a start to the first day and end to now

        Used for several methods that have start and end as keyword arguments
        that default to None, and all have the same desired default behavior.
        """
        def wrapped(*args, **kwargs):
            if kwargs.get('start') is None:
                kwargs['start'] = args[0].day_groups[0].day
            if kwargs.get('end') is None:
                kwargs['end'] = DatePoint.now()
            return func(*args, **kwargs)
        return wrapped

    @fill_boundries
    def day_range(self, start=None, end=None):
        """Get the range of days with data between start and end

        Defaults as in fill_boundries
        """
        days = self.day_groups
        start_index = bisect.bisect_left(days, start)
        end_index = bisect.bisect(days, end)
        return days[start_index:end_index]

    @fill_boundries
    def filled_range(self, start=None, end=None):
        """Get the range of days between start and end"""
        return list(arrow.Arrow.range(
            Timeframe.day, start.arrow, end.arrow))

    @fill_boundries
    def streaks_range(self, start=None, end=None, strict=False):
        """Get the range of streaks between start and endf

        The strict flag specifies whether the range is meant to include
        streaks that contain start and end, or only streaks strictly
        after start and before end.
        """
        streaks = self.finished_streaks

        def startf(streak):
            if strict:
                return all(start.before(d) for d in streak)
            return any(start.before(d) or start.same(d) for d in streak)

        def endf(streak):
            if strict:
                return all(end.after(d) for d in streak)
            return any(end.after(d) or end.same(d) for d in streak)

        try:
            start_streak = next(i for i, x in enumerate(streaks) if startf(x))
            end_streak = [i for i, x in enumerate(streaks) if endf(x)][-1]
            return streaks[start_streak:end_streak + 1]
        except StopIteration:
            return []

    @fill_boundries
    def streaks_boolean(self, start=None, end=None):
        """Return a boolean for whether each day in the range was finished"""
        result = [self.total_time_on(day) >= self.finished_threshold
                  for day in self.filled_range(start=start, end=end)]
        # end is today and today is not finished
        if DatePoint.now().same(end) and not result[-1]:
            # today could still be finished
            result[-1] = None
        return result

    def total_time_in(self, date_list):
        """Get the total time in a list of dates

        Checks the data rather than any total time that may be reported by
        these data objects, and so will work with non-DatePoints.
        """
        return sum((self.total_time_on(date) for date in date_list),
                   datetime.timedelta())

    def close(self):
        """Persist data that may have changed during runtime"""
        self.config.save_data()

# Below are "cli interface" helper functions

def color_string(string, color):
    """Get a terminal-escaped string for a certain color"""
    return '\033[{}m{}\033[0m'.format(color, string)

def finished_square(n=1):
    return click.style('◼' * n, fg='green')

def unfinished_square(n=1):
    return click.style('◻' * n, fg='red')

def unknown_square(n=1):
    return click.style('◻' * n, fg='white')

def print_streak_string(day_streak_booleans):
    """Print the streaks with red and green squares representing day states"""
    for item in day_streak_booleans:
        if item is None:
            click.echo(unknown_square(), nl=False)
        elif item:
            click.echo(finished_square(), nl=False)
        else:
            click.echo(unfinished_square(), nl=False)
    click.echo()

def humanize_timedelta(timedelta):
    """Print out nice-reading strings for time periods"""
    if timedelta.total_seconds() == 0:
        return 'nothing'
    result = []
    units = {'hour': int(timedelta.total_seconds() // 3600),
             'minute': int(timedelta.total_seconds() % 3600) // 60,
             'second': int(timedelta.total_seconds() % 60)}
    keys = ['hour', 'minute', 'second']
    if units['hour'] >= 1:
        del units['second']
        del keys[-1]
    for unit in keys:
        num = units[unit]
        if num:
            result.append('{} {}{}'.format(num, unit, 's' if num != 1 else ''))
    return ', '.join(result)

# Below are the command line interface functions, using the `click` library.
# See `click`'s documentation for details on how this works. Currently mostly
# mirrors the functions in `Project`.
# TODO: move to a separate CLI interface module or class

def char_input(prompt, last_invalid=False):
    if last_invalid:
        prompt = 'Invalid input. {}'.format(prompt)
    click.echo(prompt, nl=False)
    result = click.getchar()
    click.echo()
    return result

def validated_char_input(prompt, valid_chars, invalid_callback=None):
    result = char_input(prompt)
    while result not in valid_chars:
        last_invalid = True
        if invalid_callback is not None:
            last_invalid = invalid_callback(result)
        result = char_input(prompt, last_invalid)
    return result

def setup_noncommand():
    """Interactive setup for project config"""
    click.echo('Where do you want the config to be stored?')

    def help_(char):
        if char == 'h':
            click.echo(
                'g: global config, i.e. make a new directory in your '
                '~/.config.\n'
                'l: local config, make a .project directory in the '
                'current dir\n'
                'e: environment variable, set {} to a custom '
                'directory'.format(ConfigManager.ENVIRONMENT_OVERRIDE))
            return False

    result = validated_char_input('g, l, e, or h for help: ', 'gle', help_)
    if result == 'e':
        filepath = os.path.expanduser(input('Filepath: '))
    else:
        filepath = None
    result = {'g': ConfigLocations.config,
              'l': ConfigLocations.local,
              'e': ConfigLocations.env}[result]
    overwrite = validated_char_input('Overwrite existing data? (y/n) ', 'yn')
    overwrite = overwrite == 'y'
    ConfigManager.setup(result, overwrite, filepath)
    return ConfigManager()


@click.group()
@click.pass_context
def cli(context, debug_time_period=None):
    try:
        config = ConfigManager()
    except (FileNotFoundError, ValueError):
        click.echo('Please run setup', err=True)
        if context.invoked_subcommand != 'setup':
            context.abort()
        config = None
    project = Project(config) if config is not None else None
    context.obj['project'] = project


@cli.command()
@click.pass_context
def finish(context):
    project = context.obj['project']
    finish = project.finish()
    if finish is None:
        click.echo('Already finished today')
    else:
        click.echo('Finished', finish.date)


@cli.command()
@click.pass_context
def setup(context):
    config = setup_noncommand()
    context.obj['project'] = Project(config)


@cli.group(invoke_without_command=True)
@click.option('--list', 'list_', is_flag=True, default=False)
@click.pass_context
def streak(context, list_):
    project = context.obj['project']
    if context.invoked_subcommand is None:
        click.echo('Current streak: {}'.format(project.streak))
        print_streak_string(project.streaks_boolean())
        streak_total = project.current_streak_time
        today_total = project.total_time_today
        click.echo('Total: {}'.format(humanize_timedelta(streak_total)))
        click.echo('Today: {}'.format(humanize_timedelta(today_total)))


@streak.command()
@click.pass_context
def total(context):
    project = context.obj['project']
    click.echo(humanize_timedelta(project.current_streak_time))


@streak.command('list')
@click.pass_context
def list_streaks(context):
    project = context.obj['project']
    streaks = project.finished_streaks
    for i, streak in enumerate(streaks):
        start = streak[0].datetime_date
        end = streak[-1].datetime_date
        if start != end:
            streak_string = '{} to {}'.format(start, end)
        else:
            streak_string = '{}'.format(start)
        time_string = humanize_timedelta(project.total_time_in(streak))
        click.echo('{}: {}, {}'.format(i + 1, streak_string, time_string))


@cli.command()
@click.option('--start', '-s', default=None)
@click.option('--end', '-e', default=None)
@click.option('--streak', 'print_format', is_flag=True, flag_value='streak',
              default=True)
@click.option('--combined', 'print_format', is_flag=True, flag_value='combined')
@click.option('--empty', 'print_format', is_flag=True, flag_value='empty')
@click.pass_context
def times(context, start, end, print_format):
    project = context.obj['project']
    results = []
    if print_format == 'streak':
        streak_range = project.streaks_range(start=start, end=end)
        results.append('-' * 40)
        for streak in streak_range:
            for day in streak:
                day_string = '{}: {}'.format(
                    day.datetime_date, humanize_timedelta(day.total_time))
                results.append(day_string)
            results.append('-' * 40)
    elif print_format == 'empty':
        for day in project.filled_range(start=start, end=end):
            day_string = '{}: {}'.format(
                day.date(), humanize_timedelta(project.total_time_on(day)))
            results.append(day_string)
    elif print_format == 'combined':
        for day in project.day_range(start=start, end=end):
            results.append('{}: {}'.format(
                day.datetime_date, humanize_timedelta(day.total_time)))
    click.echo_via_pager('\n'.join(results))


@cli.command()
@click.pass_context
def debug(context):
    """Debug using PDB.

    The only non-`Project` CLI command
    """
    project = context.obj['project']
    import ipdb; ipdb.set_trace()


@cli.command()
@click.pass_context
def config(context):
    pass


@cli.command()
@click.pass_context
def start(context):
    project = context.obj['project']
    start = project.start()
    if start is None:
        click.echo('Already started')
        click.echo('Total time: {}'.format(
            humanize_timedelta(project.current_range_time)))
    else:
        click.echo('Started at')


@cli.command()
@click.pass_context
def stop(context):
    project = context.obj['project']
    start = project.start_time
    end = project.stop()
    if end is None:
        click.echo('Already stopped')
    else:
        click.echo('Stopped at {}'.format(end.time))
        difference = end - start
        click.echo(humanize_timedelta(difference))

@cli.command()
@click.pass_context
def pause(context):
    project = context.obj['project']
    if project.start_time is None:
        click.echo("Can't pause, not started")
        return
    end = project.stop()
    click.echo('Paused')
    click.pause()
    start = project.start()
    click.echo('Restarted')
    click.echo('Paused for {}'.format(humanize_timedelta(start - end)))

if __name__ == "__main__":
    obj = {}
    cli(obj=obj)
