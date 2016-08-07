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
import csv
import itertools as it
import json
import operator
import os
import os.path
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
        if (isinstance(first_date, type(self)) and
                isinstance(second_date, type(self))):
            first_date = first_date._first_date
            second_date = second_date._first_date
        self._is_range = second_date is not None
        self._first_date = arrow.get(first_date)
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

    def date(self):
        """The 'date' version of this DatePoint, i.e. without time info"""
        return DatePoint(arrow.get(self._first_date.date()))

    def time(self):
        return self._first_date.time()
    @property
    def total_time(self):
        """The time in seconds this represents

        If it's not a range, it's considered to represent an hour. This
        information being stored here is probably a bad idea and should
        be decoupled."""
        if self.is_range:
            return (self._second_date - self._first_date).total_seconds()
        return 3600

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
    def __init__(self, filepath):
        """Create a new manager for the given `filepath`

        Ensures the file exists/creates it if it doesn't
        """
        self.filepath = filepath
        if not os.path.exists(filepath):
            open(filepath, 'w').close()
        self._date_list = None
        self._file_modified = False

    def add_date(self, date):
        """Append a new DatePoint to the date list"""
        with open(self.filepath, 'a', newline='') as writef:
            writer = csv.writer(writef)
            writer.writerow([date.freeze()])
        self._file_modified = True

    @property
    def date_list(self):
        """Get the list of DatePoints this manager stores"""
        if self._date_list is None or self._file_modified:
            with open(self.filepath, 'r', newline='') as reader:
                reader = csv.reader(reader)
                self._date_list = [DatePoint.unfreeze(date[0]) for date in reader]
            self._file_modified = False
        return self._date_list

class ConfigManager:
    """Manager for the configuration of this project

    Abstraction for a persistent configuration. Saves the filepaths of the
    other necessary files as well. Currently the 'bootstrap' point, i.e. a path
    to this file is necessary to find or create the rest of the data. This will
    later be used to store more user-specific config as functionality is
    expanded.
    """
    def __init__(self, filepath):
        """Initialize a new manager from a `json` file, or make a new file"""
        self.filepath = filepath
        if not os.path.exists(filepath):
            with open(filepath, 'w') as config:
                json.dump({}, config)
        with open(filepath, 'r+') as f:
            self._data = json.load(f)

    @property
    def cache_path(self):
        """Return the filepath for the cache file"""
        return self._data['cache_path']

    @property
    def data_path(self):
        """Return the filepath for the data file"""
        return self._data['data_path']

    def _save_data(self):
        """Persist data that may have changed during runtime"""
        with open(self.filepath, 'w') as f:
            json.dump(self._data, f)

class CacheManager:
    """Manager for cached data, i.e. calculated attributes of the data

    Not used extensively in `Project`, however will become more relevant as
    more extensive statistics/information is made available.

    TODO: give this a reference to `DataManager` and have it do calculations
    itself.
    """
    def __init__(self, filepath):
        """Create a new cache manager of the filepath, or create a new file"""
        self.filepath = filepath
        if not os.path.exists(filepath):
            with open(filepath, 'w') as cache:
                json.dump({'last_date': None}, cache)
        with open(filepath, 'r+') as f:
            self._data = json.load(f)

    @property
    def last_date(self):
        """Get the last date in the date list"""
        return DatePoint.unfreeze(self._data['last_date'])

    @last_date.setter
    def last_date(self, value):
        """Set what the last date is"""
        if value is not None:
            value = value.freeze()
        self._data['last_date'] = value

    @property
    def start_time(self):
        """Get the start time of the current timerange (if it exists)"""
        start_time = self._data.get('start_time')
        if start_time is not None:
            return DatePoint.unfreeze(start_time)

    @start_time.setter
    def start_time(self, value):
        """Set the start time for a new timerange"""
        if value is not None:
            value = value.freeze()
        self._data['start_time'] = value

    def _save_data(self):
        """Persist data that may have changed during runtime"""
        with open(self.filepath, 'w') as f:
            json.dump(self._data, f)


class Project:
    """Provides the programmatic interface of the function

    This is not the 'user interface', or even the 'MVC controller'. Rather
    it's the 'API' of the application, the high level set of supported
    operations
    """
    def __init__(self, config_path, timeframe=Timeframe.day):
        """Create a `Project` given a config filepath

        Currently coupled to the managers in that it passes filenames to them.
        They should be decoupled later, perhaps by just being passed a
        `ConfigManager` that creates the others.
        """
        self.config = ConfigManager(config_path)
        self.cache = CacheManager(self.config.cache_path)
        self.data = DataManager(self.config.data_path)
        self.finished_threshold = 3600
        self.timeframe = timeframe

    def finish(self):
        """Record this day as finished >= one hour of personal project work"""
        today = DatePoint.now()
        last_date = self.data.date_list[-1]
        last_day_finished = self._data_is_finished(self._day_groups[-1])
        if (today.after(last_date) or
            today.same(last_date) and not last_day_finished):
            self.data.add_date(today)
            self.cache.last_date = today
            return today
    
    @property
    def _day_groups(self):
        return list(binary_groupby(self.data.date_list, lambda x, y: x.same(y)))

    def _data_is_finished(self, date_list):
        """Check if the time of the DatePoints exceeds completion threshold"""
        return sum(date.total_time for date in date_list) >= self.finished_threshold
    
    @property
    def _finished_streaks(self):
        """Get list of streaks of DatePoints for consecutive finished days"""
        date_points = (group[0].date() for group in self._day_groups
                       if self._data_is_finished(group))
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
        today = DatePoint.now()
        streaks = self._finished_streaks
        if not streaks or not any(streaks):
            return 0
        last_streak = streaks[-1]
        last_entry = last_streak[-1]
        if today.within_streak(last_entry):
            return len(streaks[-1])
        return 0

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
        if self.start_time is not None and now.same(self.start_time):
            self.data.add_date(DatePoint(self.start_time, now))
            self.start_time = None
            return now

    def close(self):
        """Persist data that may have changed during runtime"""
        self.config._save_data()
        self.cache._save_data()

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
    if today.date() > last_end:
        time_difference = (today.date() - last_end).days
        total_string += unfinished(time_difference - 1)
        total_string += '◻'
    print(total_string)

# Below are the command line interface functions, using the `click` library.
# See `click`'s documentation for details on how this works. Currently mostly
# mirrors the functions in `Project`.
# TODO: move to a separate CLI interface module or class

@click.group()
@click.pass_context
def cli(context, debug_time_period=None):
    pass

@cli.command()
@click.pass_context
def finish(context):
    project = context.obj['project']
    finish = project.finish()
    if finish is None:
        print('Already finished today')
    else:
        print('Finished', finish.date())

@cli.command()
@click.pass_context
def streak(context):
    project = context.obj['project']
    print(project.streak)
    print_streak_string(project._finished_streaks)

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
        print('Not started')
    else:
        print('Started at', project.start_time.time())

@cli.command()
@click.pass_context
def stop(context):
    project = context.obj['project']
    end = project.stop()
    if end is None:
        print('Not stopped')
    else:
        print('Stopped at', end.time())

if __name__ == "__main__":
    obj = {'project': Project('config.json')}
    atexit.register(obj['project'].close)
    cli(obj=obj)
    obj['project'].close()
