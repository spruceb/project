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
        with open(self.filepath, 'a', newline='' as writef):
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
        for date in self.data.date_list:
            if not current_streak:
                current_streak.append(date)
                continue
            else:
                if consecutive(date, current_streak[-1]):
                    current_streak.append(date)
                else:
                    streaks.append(current_streak)
                    current_streak = []
        return streaks        
        
    @property
    def streak(self):        
        today = arrow.now()
        streaks = self._streak_groups
        if not streaks or not any(streaks):
            return 0
        last_streak = streaks[-1]
        last_entry = last_streak[-1]
        if consecutive(today, last_entry) or today.date() == last_entry.date():
            

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
    
        
def same_day(*datetimes):
    return reduce(operator.eq, map(lambda x: x.date(), datetimes))

def consecutive(first, second):
    return abs(first.toordinal() - second.toordinal()) == 1
    
    
@click.group()
@click.option('--debug-time-period', default=None)
@click.pass_context
def cli(context, debug_time_period):
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
    cli(obj)
    obj['project'].close()
