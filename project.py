#!/usr/bin/env python3
import click
import os

from data import ConfigManager, ConfigLocations
from controller import Project
from utilities import humanize_timedelta

# "cli interface" helper functions

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

# Below are the command line interface functions, using the `click` library.
# See `click`'s documentation for details on how this works. Currently mostly
# mirrors the functions in `Project`.

def char_input(prompt, last_invalid=False):
    if last_invalid:
        prompt = 'Invalid input. {}'.format(prompt)
    click.echo(prompt, nl=False)
    result = click.getchar()
    click.echo()
    if result == '\x03':
        raise KeyboardInterrupt()
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
                'selected dir\n'
                'e: environment variable, set {} to a custom '
                'directory'.format(ConfigManager.ENVIRONMENT_OVERRIDE))
            return False

    result = validated_char_input('g, l, e, or h for help: ', 'gle', help_)
    if result in 'le':
        filepath = os.path.expanduser(input('File path (default to current): '))
    else:
        filepath = None
    if result == 'l' and filepath is not None:
        os.chdir(filepath)
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
    """This tool provides ways to keep track of work on projects with streaks

    This is intended for motivation in continually working on personal
    projects as opposed to being a general management tool. Its gearing
    towards streaks reflects this. For some people habit forming and
    tangible reminders are extremely helpful for preventing projects
    from falling by the wayside.

    After setup is finished, use start and stop to record precise time
    ranges, or finish to just mark entire days completed
    """
    try:
        config = ConfigManager()
    except (FileNotFoundError, ValueError):
        click.echo('Please run setup', err=True)
        if context.invoked_subcommand != 'setup':
            context.abort()
        config = None
    project = Project(config) if config is not None else None
    context.obj['project'] = project

@cli.command(short_help='mark today as finished')
@click.pass_context
def finish(context):
    """Mark today as being finished without an explicit amount of time

    Regardless of how much time the project is configured to require for a
    timeframe to be finished, marking it as finished will always be enough.
    This should be rarely used, start and stop are the preferred tracking
    method. However there are various reasons why they might be unavailable
    or simply forgotten, so finish acts as a failsafe
    """
    project = context.obj['project']
    finish = project.finish()
    if finish is None:
        click.echo('Already finished today')
    else:
        click.echo('Finished', finish.date)


@cli.command(short_help='set up new installation')
@click.pass_context
def setup(context):
    """Set up a new project config location

    Interactively queries the user for initial config and where to store
    critical startup files/data.
    """
    config = setup_noncommand()
    context.obj['project'] = Project(config)


@cli.group(invoke_without_command=True,
           short_help='show info about the current streak')
@click.pass_context
def streak(context):
    """Get information about the current streak (and all days)

    Prints out a github-like string of squares showing whether each of the
    days since project-start have been completed. Also prints out the length
    of the current streak and the total time spent today
    """
    project = context.obj['project']
    if context.invoked_subcommand is None:
        click.echo('Current streak: {}'.format(project.streak))
        print_streak_string(project.streaks_boolean())
        streak_total = project.current_streak_time
        today_total = project.total_time_today
        click.echo('Today: {}'.format(humanize_timedelta(today_total)))


@streak.command(short_help='total time spent in streak')
@click.pass_context
def total(context):
    """Subcommand of streak that prints the total time in the current streak"""
    project = context.obj['project']
    click.echo(humanize_timedelta(project.current_streak_time))


@streak.command('list', short_help='list all streaks and their times')
@click.pass_context
def list_streaks(context):
    """Lists every streak in the data and the total time spent for each"""
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


@cli.command(short_help='time info about individual days')
@click.option('--start', '-s', default=None, help='when to begin the range')
@click.option('--end', '-e', default=None, help='when to end the range')
@click.option('--streak', 'print_format', is_flag=True, flag_value='streak',
              default=True, help='default format flag: separate finished days into streaks')
@click.option('--combined', 'print_format', is_flag=True, flag_value='combined',
              help='format flag: print all days with any time')
@click.option('--empty', 'print_format', is_flag=True, flag_value='empty',
              help='format flag: print days since start including empty ones')
@click.pass_context
def times(context, start, end, print_format):
    """Print time information about individual days

    Allows specification of a time range to give info about. Has multiple
    different format options (or format flags). By default prints all days in
    all streaks, clearly separated into streaks.
    """
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


@cli.command(short_help='debug using ipdb')
@click.pass_context
def debug(context):
    """Debug using IPDB.

    The only non-`Project` CLI command
    """
    project = context.obj['project']
    import ipdb; ipdb.set_trace()


@cli.command(short_help='TODO: let you change project settings')
@click.pass_context
def config(context):
    pass


@cli.command(short_help='begin work on the project')
@click.pass_context
def start(context):
    """Begin work on the project

    Starts a new time range at the time called. This, along with stop,
    is the preferred method of time tracking since it is the most explicit.
    Prints out the time started. If work has already been started (and not
    stopped), does nothing, but informs the user that they have already
    started work and how long they've been working.
    """
    project = context.obj['project']
    start = project.start()
    if start is None:
        click.echo('Already started')
        click.echo('Total time: {}'.format(
            humanize_timedelta(project.current_range_time)))
    else:
        click.echo('Started at {}'.format(start))


@cli.command(short_help='stop work on the project')
@click.pass_context
def stop(context):
    """Stop work on the project

    Ends an already-started time range at the time called. If no time
    range was started, does nothing. Otherwise prints out the time
    stopped at.
    """
    project = context.obj['project']
    start = project.start_time
    end = project.stop()
    if end is None:
        click.echo('Already stopped')
    else:
        click.echo('Stopped at {}'.format(end.time))
        difference = end - start
        click.echo(humanize_timedelta(difference))

@cli.command(short_help='quick pause in work')
@click.pass_context
def pause(context):
    """Convenience command that stops work and resumes on any keypress

    Meant for quick breaks/leaving computer. Prints how long the pause
    was on unpause. If no timerange is running informs the user of this.
    """
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
