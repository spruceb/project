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
from datetime import timedelta
import arrow

from date_point import Timeframe, DatePoint, TimeframeGroup
from utilities import binary_groupby

class Project:
    """Provides the programmatic interface of the function

    This is not the 'user interface', or the 'MVC controller'. Rather
    it's the 'API' of the application, the high level set of supported
    operations
    """
    def __init__(self, config):
        """Create a `Project`"""
        self.config = config
        self.cache = self.config.cache
        self.data = self.config.data
        self.finished_threshold = timedelta(hours=1)
        self.timeframe = Timeframe.day
        self._last_range = None
        atexit.register(self.close)

    def finish(self):
        """Record this timeframe as finished >= the threshold of project work"""
        current = DatePoint.now()
        if self.data.date_list:
            last_date = self.data.date_list[-1]
            last_frame_finished = self._is_finished(self.timeframe_groups[-1])
            if (current.after(last_date, self.timeframe) or
                    current.same(last_date, self.timeframe) and
                    not last_frame_finished):
                self.data.add_date(current)
                return current
        else:
            self.data.add_date(current)
            return current

    @property
    def timeframe_groups(self):
        """Return the DatePoints grouped into TimeframeGroups"""
        return TimeframeGroup.group_timeframes(self.data.date_list,
                                               self.timeframe)

    def _is_finished(self, timeframe_group):
        """Check if the time of the DatePoints exceeds completion threshold"""
        return timeframe_group.total_time >= self.finished_threshold

    @property
    def finished_streaks(self):
        """Get list of streaks of TimeframeGroups for consecutive finished timeframes"""
        date_points = (group for group in self.timeframe_groups
                       if self._is_finished(group))
        return list(binary_groupby(
            date_points, lambda x, y: x.within_streak(y, self.timeframe)))

    @property
    def streak(self):
        """Get the length of the last streak ending in this or the last frame

        This streak is the 'current streak', i.e. the streak that still has the
        potential to be continued. If there is no such streak then this is 0.
        This will check if enough time was logged in the timeframe, so if there
        are only timeranges that total 40min, it will not be counted as a
        completed frame.
        """
        if self.current_streak is None:
            return 0
        return len(self.current_streak)

    @property
    def current_streak(self):
        """Get the current streak if there is one

        If either this or the last timeframe `_is_finished`, return the streak
        that contains it. Otherwise there is no current streak.
        """
        current = DatePoint.now()
        streaks = self.finished_streaks
        if not streaks or not any(streaks):
            return None
        last_streak = streaks[-1]
        last_entry = last_streak[-1]
        if current.within_streak(last_entry, self.timeframe):
            return last_streak
        return None

    @property
    def current_range_time(self):
        """Return the timedelta for the current/most recent 'started' time"""
        if self.start_time is not None:
            return DatePoint.now() - self.start_time
        else:
            return timedelta()

    @property
    def current_streak_time(self):
        """Get the total time in the current streak"""
        if self.current_streak is None:
            return timedelta()
        return self.total_time_in(self.current_streak)

    def total_time_on(self, date):
        """Get the total time on a given date"""
        datepoint = DatePoint(date)
        matches = (frame for frame in self.timeframe_groups
                   if frame.same(datepoint, self.timeframe))
        try:
            match = next(matches)
        except StopIteration:
            match = None
        if match is None:
            return timedelta()
        return match.total_time

    @property
    def total_time_current(self):
        """Get the total time spent on the current timeframe"""
        current = DatePoint.now()
        result = self.total_time_on(current)
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
                not now.same(self.start_time, self.timeframe) or overwrite):
            self.start_time = now
            return now

    def stop(self):
        """End the current timeframe"""
        now = DatePoint.now()
        if self.start_time is not None:
            this_range = DatePoint(self.start_time, now)
            if now.same(self.start_time, self.timeframe):
                self.data.add_date(this_range)
                self._last_range = this_range
            else:
                for datepoint in this_range.split_range(self.timeframe):
                    self.data.add_date(datepoint)
                    self._last_range = datepoint
            self.start_time = None
            return now

    def fill_boundries(func):
        """Decorator that defaults a start to the first frame and end to now

        Used for several methods that have start and end as keyword arguments
        that default to None, and all have the same desired default behavior.
        """
        def wrapped(*args, **kwargs):
            if kwargs.get('start') is None and args[0].timeframe_groups:
                kwargs['start'] = args[0].timeframe_groups[0].group_date
            if kwargs.get('end') is None:
                kwargs['end'] = DatePoint.now()
            return func(*args, **kwargs)
        return wrapped

    @fill_boundries
    def timeframe_range(self, start=None, end=None):
        """Get the range of frames with data between start and end

        Defaults as in fill_boundries
        """
        frames = self.timeframe_groups
        start_index = bisect.bisect_left(frames, start)
        end_index = bisect.bisect(frames, end)
        return frames[start_index:end_index]

    @fill_boundries
    def filled_range(self, start=None, end=None):
        """Get the range of timeframes between start and end"""
        if start is None or end is None:
            return []
        return list(arrow.Arrow.range(
            self.timeframe, start.arrow, end.arrow))

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
                return all(start.before(d, self.timeframe) for d in streak)
            return any(start.before(d, self.timeframe)
                       or start.same(d, self.timeframe) for d in streak)

        def endf(streak):
            if strict:
                return all(end.after(d, self.timeframe) for d in streak)
            return any(end.after(d, self.timeframe)
                       or end.same(d, self.timeframe) for d in streak)
        try:
            start_streak = next(i for i, x in enumerate(streaks) if startf(x))
            end_streak = [i for i, x in enumerate(streaks) if endf(x)][-1]
            return streaks[start_streak:end_streak + 1]
        except StopIteration:
            return []

    @fill_boundries
    def streaks_boolean(self, start=None, end=None):
        """Return a boolean for whether each frame in the range was finished"""
        result = [self.total_time_on(frame) >= self.finished_threshold
                  for frame in self.filled_range(start=start, end=end)]
        # end is today and today is not finished
        if DatePoint.now().same(end, self.timeframe) and result and not result[-1]:
            # today could still be finished
            result[-1] = None
        return result

    def total_time_in(self, date_list):
        """Get the total time in a list of dates

        Checks the data rather than any total time that may be reported by
        these data objects, and so will work with non-DatePoints.
        """
        return sum(
            (self.total_time_on(date) for date in date_list), timedelta())

    def close(self):
        """Persist data that may have changed during runtime"""
        self.config.save_data()
