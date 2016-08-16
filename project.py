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
import itertools as it
import json
import operator
import os
import os.path
import sys
from shutil import rmtree
from functools import reduce

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
        return self._first_date.date()

    @property
    def time(self):
        return self._first_date.time()

    @property
    def arrow(self):
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
        return any(self.same(date, timeframe) for date in date_list)

    def __eq__(self, other):
        if self._is_range != other._is_range:
            return False
        return (self._first_date == other._first_date and
                self._second_date == other._second_date)

    def __sub__(self, other):
        return self._first_date - other._first_date

    def __gt__(self, other):
        return self._first_date > other._first_date

    def __str__(self):
        if self.is_range:
            return '{} to {}'.format(self._first_date, self._second_date)
        return str(self._first_date)

    def __repr__(self):
        return str(self)

class DayGroup(DatePoint):
    def __init__(self, date_list):
        assert(len(date_list) > 0)
        self.date_list = date_list
        self.day = date_list[0].date

    @classmethod
    def group_days(cls, datepoint_list):
        return [cls(dates) for dates in
                binary_groupby(datepoint_list, lambda x, y: x.same(y))]

    @property
    def total_time(self):
        return sum((date.total_time for date in self.date_list),
                   datetime.timedelta())

    def ordinal(self, timeframe=None, use_start=None):
        return self.day.ordinal(timeframe=Timeframe.day)

    @property
    def is_range(self):
        return False

    @property
    def _first_date(self):
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
        return {'data_file': 'data.csv'}

    @classmethod
    def setup(cls, overwrite, path, data_file, **kwargs):
        data_filepath = os.path.join(path, data_file)
        if overwrite or not os.path.isfile(data_filepath):
            with open(data_filepath, 'w') as f:
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
        pass

class CacheManager:
    """Manager for cached data, i.e. calculated attributes of the data

    Not used extensively in `Project`, however will become more relevant as
    more extensive statistics/information is made available.

    TODO: give this a reference to `DataManager` and have it do calculations
    itself.
    """
    def __init__(self, config, cache_filename, path):
        """Create a new cache manager of the filepath, or create a new file"""
        self.config = config
        self.cache_path = os.path.join(path, cache_filename)
        self._cache = None

    @property
    def cache(self):
        if self._cache is None:
            with open(self.cache_path, 'r') as f:
                self._cache = json.load(f)
        return self._cache

    @classmethod
    def default(cls):
        return {'cache_filename': 'cache.json'}

    @classmethod
    def setup(cls, path, overwrite, cache_filename, **kwargs):
        cache_filepath = os.path.join(path, cache_filename)
        if overwrite or not os.path.isfile(cache_filepath):
            with open(cache_filepath, 'w') as f:
                json.dump({'last_date': None, 'start_time': None}, f)

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
        """Persist data that may have changed during runtime"""
        if self._cache is not None:
            with open(self.cache_path, 'w') as f:
                json.dump(self._cache, f)

class ConfigLocations:
    config = 'config'
    local = 'local'
    env = 'env'

class ConfigManager:
    """Manager for the configuration of this project

    Abstraction for a persistent configuration. Saves the filepaths of the
    other necessary files as well. Currently the 'bootstrap' point, i.e. a path
    to this file is necessary to find or create the rest of the data. This will
    later be used to store more user-specific config as functionality is
    expanded.
    """

    LOCAL_DIRNAME = '.project'
    ENVIRONMENT_OVERRIDE = 'PROJECT_TRACKER_HOME'
    GLOBAL_DIRNAME = 'project'
    DEFAULT_GLOBAL_LOCATION = os.path.join(os.environ['HOME'], '.config')
    GLOBAL_DIRPATH = os.path.join(DEFAULT_GLOBAL_LOCATION, GLOBAL_DIRNAME)
    CACHE_DIRNAME = 'cache'
    DATA_DIRNAME = 'data'
    CONFIG_FILENAME = 'project.config'

    def __init__(self):
        self.config_path = self._config_location()
        self.config_filepath = os.path.join(self.config_path,
                                            self.CONFIG_FILENAME)
        try:
            with open(self.config_filepath, 'r') as f:
                config_string = f.read()
                self._backup = config_string
                self._config = json.loads(config_string)
        except json.decoder.JSONDecodeError:
            raise ValueError('Invalid data')
        self.data = DataManager(self, **self.config['data'])
        self.cache = CacheManager(self, **self.config['cache'])

    @property
    def config(self):
        return self._config

    @classmethod
    def _config_location(cls):
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
        # if overwrite is false should check if things exist first
        try:
            config_location = cls._config_location()
        except FileNotFoundError:
            cls.create_config_location(config_location_type, env_path)
            config_location = cls._config_location()
        config_filepath = os.path.join(config_location, cls.CONFIG_FILENAME)
        if not overwrite and os.path.isfile(config_filepath):
            with open(config_filepath, 'r') as f:
                config = json.load(f)
                data_init = config['data']
                cache_init = config['cache']
        else:
            with open(config_filepath, 'w') as f:
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
                json.dump(config, f)
        DataManager.setup(overwrite=overwrite, **data_init)
        CacheManager.setup(overwrite=overwrite, **cache_init)

    def save_data(self):
        """Persist data that may have changed during runtime"""
        if self._config is not None:
            with open(self.config_filepath, 'r') as f:
                contents = f.read()
            if contents != self._backup:
                pass # do nothing for now, be safer later
            with open(self.config_filepath, 'w') as f:
                json.dump(self._config, f)
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
            last_day_finished = self._data_is_finished(self.day_groups[-1])
            if (today.after(last_date) or
                    today.same(last_date) and not last_day_finished):
                self.data.add_date(today)
                return today
        else:
            self.data.add_date(today)
            return today

    @property
    def day_groups(self):
        return DayGroup.group_days(self.data.date_list)

    def _is_finished(self, day_group):
        """Check if the time of the DatePoints exceeds completion threshold"""
        return day_group.total_time >= self.finished_threshold

    @property
    def finished_streaks(self):
        """Get list of streaks of DatePoints for consecutive finished days"""
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
        if self.start_time is not None:
            return DatePoint.now() - self.start_time
        elif self._last_range is not None:
            return self._last_range.total_time
        else:
            return datetime.timedelta()

    @property
    def current_streak_time(self):
        if self.current_streak is None:
            return datetime.timedelta()
        return self.total_time_in(self.current_streak)

    def total_time_on(self, date):
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
        if (self.start_time is None or not now.same(self.start_time)
                or overwrite):
            self.start_time = now
            return now

    def stop(self):
        """End the current timeframe"""
        now = DatePoint.now()
        if self.start_time is not None:
            if now.same(self.start_time):
                last_range = DatePoint(self.start_time, now)
                self.data.add_date(last_range)
                self._last_range = last_range
                self.start_time = None
                return now
            else:
                pass

    def fill_boundries(func):
        def wrapped(*args, **kwargs):
            if kwargs.get('start') is None:
                kwargs['start'] = args[0].day_groups[0].day
            if kwargs.get('end') is None:
                kwargs['end'] = DatePoint.now()
            return func(*args, **kwargs)
        return wrapped

    @fill_boundries
    def day_range(self, start=None, end=None):
        days = self.day_groups
        start_index = bisect.bisect_left(days, start)
        end_index = bisect.bisect(days, end)
        return days[start_index:end_index]

    @fill_boundries
    def filled_range(self, start=None, end=None):
        return list(arrow.Arrow.range(
            Timeframe.day, start.arrow, end.arrow))

    @fill_boundries
    def streaks_range(self, start=None, end=None, strict=False):
        # strict means to start with streak that occurs entirely after start
        # and end with streak entirely before end
        # otherwise uses first streak containing start and same for end
        streaks = self.finished_streaks
        def startf(streak):
            if strict:
                return all(start.before(d) for d in streak)
            return any(start.same(d) for d in streak)
        def endf(streak):
            if strict:
                return all(end.after(d) for d in streak)
            return any(end.same(d) for d in streak)
        try:
            start_streak = next(filter(lambda x: startf(x[1]),
                                       list(enumerate(streaks))))
            end_streak = next(filter(lambda x: endf(x[1]),
                                     list(enumerate(streaks))))
            return streaks[start_streak[0]:end_streak[0] + 1]
        except StopIteration:
            return []

    def total_time_in(self, date_list):
        return sum((self.total_time_on(date) for date in date_list),
                   datetime.timedelta())

    def close(self):
        """Persist data that may have changed during runtime"""
        self.config.save_data()

# Below are "cli interface" helper functions

def color_string(string, color):
    """Get a terminal-escaped string for a certain color"""
    return '\033[{}m{}\033[0m'.format(color, string)

def print_streak_string(day_streak_lists):
    """Print the streaks with red and green squares representing day states"""
    total_string = ''
    last_end = None
    def finished(n):
        return color_string('◼' * n, '0;32')
    def unfinished(n):
        return color_string('◻' * n, '31;1')

    for streak in day_streak_lists:
        if last_end is not None:
            time_difference = (streak[0] - last_end).days
            total_string += unfinished(time_difference)
        total_string += finished(len(streak))
        # total_string += ' '
        last_end = streak[-1]
    today = DatePoint.now()
    if today.after(last_end):
        time_difference = (today.date - last_end).days
        total_string += unfinished(time_difference - 1)
        total_string += '◻'
    print(total_string)

def humanize_timedelta(timedelta):
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

def setup_noncommand():
    print('Where do you want the config to be stored?')
    result = input('g, l, e, or h for help: ')
    while result not in 'gle':
        if result == 'h':
            print("g: global config, i.e. make a new directory in your ~/.config.\n"
                  "l: local config, make a .project directory in the current dir\n"
                  "e: environment variable, set {} to a custom directory".format(
                      ConfigManager.ENVIRONMENT_OVERRIDE))
            result = input('g, l, e, or h for help: ')
        else:
            result = input('Invalid input. g, l, e, or h for help: ')
    if result == 'e':
        filepath = os.path.expanduser(input('Filepath: '))
    else:
        filepath = None
    result = {'g': ConfigLocations.config,
              'l': ConfigLocations.local,
              'e': ConfigLocations.env}[result]
    overwrite = input('Overwrite existing data? (y/n) ')
    while overwrite not in 'yn':
        overwrite = input('Invalid input. Overwrite existing data? (y/n) ')
    overwrite = overwrite == 'y'
    ConfigManager.setup(result, overwrite, filepath)
    return ConfigManager()

@click.group()
@click.pass_context
def cli(context, debug_time_period=None):
    try:
        config = ConfigManager()
    except (FileNotFoundError, ValueError):
        print("Please run setup")
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
        print('Already finished today')
    else:
        print('Finished', finish.date)

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
        print('Current streak: {}'.format(project.streak))
        print_streak_string(project.finished_streaks)
        streak_total = project.current_streak_time
        today_total = project.total_time_today
        print('Total: {}'.format(humanize_timedelta(streak_total)))
        print('Today: {}'.format(humanize_timedelta(today_total)))

@streak.command()
@click.pass_context
def total(context):
    project = context.obj['project']
    print(humanize_timedelta(project.current_streak_time))

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
        print('{}: {}, {}'.format(i + 1, streak_string, time_string))

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
    print()
    if print_format == 'streak':
        streak_range = project.streaks_range(start=start, end=end)
        print('-' * 40)
        for streak in streak_range:
            print_days(streak)
            print('-' * 40)
    elif print_format == 'empty':
        for day in project.filled_range(start=start, end=end):
            print('{}: {}'.format(day.date(),
                                  humanize_timedelta(
                                      project.total_time_on(day))))
    elif print_format == 'combined':
        print_days(project.day_range(start=start, end=end))
    print()

def print_days(days):
    for day in days:
        print('{}: {}'.format(day.datetime_date,
                              humanize_timedelta(day.total_time)))

@cli.command()
@click.pass_context
def debug(context):
    """Debug using PDB.

    The only non-`Project` CLI command
    """
    project = context.obj['project']
    import pdb; pdb.set_trace()

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
        print('Already started')
    else:
        print('Started at', start.time)

@cli.command()
@click.pass_context
def stop(context):
    project = context.obj['project']
    start = project.start_time
    end = project.stop()
    if end is None:
        print('Not stopped')
    else:
        print('Stopped at', end.time)
        difference = end - start
        print(humanize_timedelta(difference))

if __name__ == "__main__":
    obj = {}
    cli(obj=obj)
