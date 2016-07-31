#!/usr/bin/env python3
import click
import json
import arrow
import csv
import itertools as it
import os
import os.path
import operator
from functools import reduce

class DataPoint:
    """Wrapper around dates or pairs of dates"""
    def __init__(self):
        pass

class DataManager:
    def __init__(self, filepath):
        self.filepath = filepath
        if not os.path.exists(filepath):
            open(filepath, 'w').close()
        self._date_list = None
        self._file_modified = False

    def add_date(self, date):
        with open(self.filepath, 'a', newline='') as writef:
            writer = csv.writer(writef)
            writer.writerow([str(date)])
        self._file_modified = True

    @property
    def date_list(self):
        if self._date_list is None or self._file_modified:
            with open(self.filepath, 'r', newline='') as reader:
                reader = csv.reader(reader)
                self._date_list = [[arrow.get(date) for date in datelist]
                                   for datelist in reader]
            self._file_modified = False
        return self._date_list

    def add_timerange(self, start, end):
        with open(self.filepath, 'a', newline='') as writef:
            writer = csv.writer(writef)
            writer.writerow([str(start), str(end)])
        self._file_modified = True

class ConfigManager:
    def __init__(self, filepath):
        self.filepath = filepath
        if not os.path.exists(filepath):
            with open(filepath, 'w') as config:
                json.dump({}, config)
        with open(filepath, 'r+') as f:
            self._data = json.load(f)

    @property
    def cache_path(self):
        return self._data['cache_path']

    @property
    def data_path(self):
        return self._data['data_path']

    def _save_data(self):
        with open(filepath, 'w') as f:
            json.dump(self._data, f)

class CacheManager:
    def __init__(self, filepath):
        self.filepath = filepath
        if not os.path.exists(filepath):
            with open(filepath, 'w') as cache:
                json.dump({'last_date': None}, cache)
        with open(filepath, 'r+') as f:
            self._data = json.load(f)

    @property
    def last_date(self):
        return arrow.get(self._data['last_date'])

    @last_date.setter
    def last_date(self, value):
        self._data['last_date'] = str(value)

    @property
    def start_time(self):
        start_time = self._data['start_time']
        if start_time is not None:
            return arrow.get(start_time)

    @start_time.setter
    def start_time(self, value):
        self._data['start_time'] = str(value)

    def _save_data(self):
        with open(self.filepath, 'w') as f:
            json.dump(self._data, f)


class Project:
    def __init__(self, config_path, time_interval='days'):
        self.config = ConfigManager(config_path)
        self.cache = CacheManager(self.config.cache_path)
        self.data = DataManager(self.config.data_path)
        self._streak = None

    def finish(self):
        today = arrow.now()
        self.data.add_date(today)
        last_date = self.cache.last_date
        if today > last_date:
            self.cache.last_date = today

    @property
    def _streak_groups(self):
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
        return self.cache.start_time

    @start_time.setter
    def start_time(self, value):
        self.cache.start_time = value

    def start(self, overwrite=False):
        now = arrow.now()
        if (self.start_time is None or not same_day(now, self.start_time)
                or overwrite):
            self.start_time = now

    def stop(self):
        now = arrow.now()
        if self.start_time is not None and same_day(self.start_time, now):
            self.data.add_timerange(self.start_time, now)
            self.start_time = None

    def close(self):
        self.config._save_data()
        self.cache._save_data()

def all_dates(*datetimes_and_dates):
    return map(lambda x: x.date() if hasattr(x, 'date') else x,
               datetimes_and_dates)
def same_day(*datetimes):
    return reduce(operator.eq, all_dates(*datetimes))

def consecutive(first, second):
    return abs(first.toordinal() - second.toordinal()) == 1


def color_string(string, color):
    return '\033[{}m{}\033[0m'.format(color, string)
    
def print_streak_string(streak_lists):
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
        total_string += color_string('◻' * time_difference, '31;1')
    print(total_string)
    
@click.group()
@click.pass_context
def cli(context, debug_time_period=None):
    project = Project('config.json')
    context.obj['project'] = project

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
    project = context.obj['project']
    import pdb; pdb.set_trace()

@cli.command()
@click.pass_context
def config(context):
    pass

def start():
    pass

def stop():
    pass

if __name__ == "__main__":
    obj = {}
    cli(obj=obj)    
    obj['project'].close()
