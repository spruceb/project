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

Work in progress.

WIP NOTES: 
Currently in a halfway state of supporting both dates (i.e. days)
and time ranges (i.e. pairs of a start and end datetime). Time ranges work for
the purposes of calculating streaks, but there is no way for the user to add
them yet, and no way to query total time or the like. Additionally, currently
pairs and dates are both stored and processed as `arrow.Arrow` objects in a 
list (so a range is stored as a list of two such objects). Then the first
`arrow` in the range is considered for streak purposes. These should be unified
into `DataPoints`, or something similar, in the future, to clean up functions
dealing with both.

There's a clear opportunity for abstraction in the `Manager` classes.
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

class DataPoint:
    """Wrapper around dates or pairs of dates. TODO: fill in and use"""
    def __init__(self):
        pass

class DataManager:
    """Wraps the mechanism for persisting and querying work dates and times
    
    The main features of this program rely on storage of dates and times during
    which personal project work has take place. The actual mechanism for
    storing this data is abstracted from the rest of the program. Here it is
    a simple `csv` file, with the `str` outputs of `arrow.Arrow` objects stored
    in it for easy retrieval.
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
        """Append a new date to the date list"""
        with open(self.filepath, 'a', newline='') as writef:
            writer = csv.writer(writef)
            writer.writerow([str(date)])
        self._file_modified = True

    @property
    def date_list(self):
        """Get the list of `arrow.Arrow` dates this manager stores"""
        if self._date_list is None or self._file_modified:
            with open(self.filepath, 'r', newline='') as reader:
                reader = csv.reader(reader)
                self._date_list = [[arrow.get(date) for date in datelist]
                                   for datelist in reader]
            self._file_modified = False
        return self._date_list

    def add_timerange(self, start, end):
        """Add a new timerange (start and end time) to the date list"""
        with open(self.filepath, 'a', newline='') as writef:
            writer = csv.writer(writef)
            writer.writerow([str(start), str(end)])
        self._file_modified = True

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
        return arrow.get(self._data['last_date'])

    @last_date.setter
    def last_date(self, value):
        """Set what the last date is"""
        self._data['last_date'] = str(value)

    @property
    def start_time(self):
        """Get the start time of the current timerange (if it exists)"""
        start_time = self._data.get('start_time')
        if start_time is not None:
            return arrow.get(start_time)

    @start_time.setter
    def start_time(self, value):
        """Set the start time for a new timerange"""
        self._data['start_time'] = str(value)

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
    def __init__(self, config_path, time_interval='days'):
        """Create a `Project` given a config filepath
        
        Currently coupled to the managers in that it passes filenames to them.
        They should be decoupled later, perhaps by just being passed a
        `ConfigManager` that creates the others.
        """
        self.config = ConfigManager(config_path)
        self.cache = CacheManager(self.config.cache_path)
        self.data = DataManager(self.config.data_path)

    def finish(self):
        """Record this day as finished >= one hour of personal project work"""
        today = arrow.now()
        self.data.add_date(today)
        last_date = self.cache.last_date
        if today > last_date:
            self.cache.last_date = today

    @property
    def _streak_groups(self):
        """Get the dates grouped into streaks based on day

        So if the datelist contains three dates on the same day, another the
        day after, and then another five days later, this will return the first
        four in one list and the last date in a final, separate list
        
        Example:
        [6-27T12:24, 6-27T16:45, 6-28, 7-1, 7-2] -> 
            [[6-27T12:24, 6-27T16:45, 6-28], [7-1, 7-2]]
        """
        streaks = []
        current_streak = []
        for dates in self.data.date_list:
            date = None
            if len(dates) == 1:
                date = dates[0]
            if not current_streak:
                current_streak.append(dates if date is None else date)
                continue
            else:
                if (consecutive(dates[0], current_streak[-1]) or
                        same_day(dates[0], current_streak[-1])):
                    current_streak.append(dates if date is None else date)
                else:
                    streaks.append(current_streak)
                    current_streak = [date]
        if current_streak:
            streaks.append(current_streak)
        return streaks

    @property
    def _day_streaks(self):
        """Get streak lists consisting only of distinct days

        `_streak_groups` will include time ranges and dates that occurred on
        the same day. This will return streak lists of dates (not datetimes)
        without duplicate days. 

        Example:
        [6-27T12:24, 6-27T16:45, 6-28, 7-1, 7-2] -> [[6-27, 6-28], [7-1, 7-2]]
        """
        streaks = self._streak_groups
        day_streaks = []
        for streak in streaks:
            current_streak = []
            for item in streak:
                date = item
                if not isinstance(item, arrow.Arrow):
                    date = item[0]
                if not current_streak or consecutive(date, current_streak[-1]):
                    current_streak.append(date.date())
            day_streaks.append(current_streak)
        return day_streaks                           

    @property
    def streak(self):
        """Get the length of the last streak ending today or yesterday

        This streak is the 'current streak', i.e. the streak that still has the
        potential to be continued. If there is no such streak then this is 0.
        This does not take into account how much time may have been spent, just
        that the dates occur. Thus insufficiently small timeframes may be
        counted as completed days. This will be fixed as further support for
        timeframes is added.
        """
        today = arrow.now()
        streaks = self._day_streaks
        if not streaks or not any(streaks):
            return 0
        last_streak = streaks[-1]
        last_entry = last_streak[-1]
        if consecutive(today, last_entry) or same_day(today, last_entry):
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
        now = arrow.now()
        if (self.start_time is None or not same_day(now, self.start_time)
                or overwrite):
            self.start_time = now

    def stop(self):
        """End the current timeframe"""
        now = arrow.now()
        if self.start_time is not None and same_day(self.start_time, now):
            self.data.add_timerange(self.start_time, now)
            self.start_time = None
        return now

    def close(self):
        """Persist data that may have changed during runtime"""
        print('called')
        self.config._save_data()
        self.cache._save_data()

def all_dates(*datetimes_and_dates):
    """Given a list of mixed datetimes and date objects, get them as dates"""
    return map(lambda x: x.date() if hasattr(x, 'date') else x,
               datetimes_and_dates)

def same_day(*datetimes):
    """Checks whether a list of datetimes all occurred on the same day"""
    return reduce(operator.eq, all_dates(*datetimes))

def consecutive(first, second):
    """Check whether two datetimes occurred on consecutive days"""
    return abs(first.toordinal() - second.toordinal()) == 1

def color_string(string, color):
    """Get a terminal-escaped string for a certain color"""
    return '\033[{}m{}\033[0m'.format(color, string)
    
def print_streak_string(streak_lists):
    """Print the streaks with red and green squares representing day states"""
    total_string = ''
    last_end = None
    for streak in streak_lists:
        if last_end is not None:
            time_difference = (streak[0] - last_end).days
            total_string += color_string('◻' * time_difference, '31;1')            
        total_string += color_string('◼' * len(streak), '0;32')
        # total_string += ' '
        last_end = streak[-1]
    today = arrow.now()
    if today.date() > last_end:
        time_difference = (today.date() - last_end).days
        total_string += color_string('◻' * (time_difference - 1), '31;1')
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
    project.finish()

@cli.command()
@click.pass_context
def streak(context):
    project = context.obj['project']
    print(project.streak)
    print_streak_string(project._day_streaks)

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
    project.start()
    print(project.start_time.time())

@cli.command()
@click.pass_context
def stop(context):
    project = context.obj['project']
    end = project.stop()
    print(end.time())
    

if __name__ == "__main__":
    obj = {'project': Project('config.json')}
    atexit.register(obj['project'].close)
    cli(obj=obj)    
    obj['project'].close()
