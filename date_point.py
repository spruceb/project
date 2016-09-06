import datetime
import arrow

from utilities import binary_groupby

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

    def floor(self, timeframe):
        return self._first_date.floor(timeframe)

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
        first, second = self._first_date, self._first_date.ceil(timeframe)
        while second < self._second_date:
            yield DatePoint(first, second)
            first = second + datetime.timedelta(microseconds=1)
            second = first.ceil(timeframe)
        yield DatePoint(first, self._second_date)

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

class TimeframeGroup(DatePoint):
    """A group of DatePoints in a single timeframe

    A TimeframeGroup inherits from DatePoint and in most ways can be treated
    like one. It differs in that it stores a list of DatePoints rather than
    one or two `arrow.Arrow` dates. It uses the timeframe floor of the
    first component date for all DatePoint operations that require a
    `_first_date`.

    Used in various places in `Project` when the individual DatePoints in a
    timeframe aren't as relevant as the aggregate information.
    """
    def __init__(self, date_list, timeframe=Timeframe.day):
        """Create a new group from a list of dates in the same timeframe"""
        assert len(date_list) > 0
        self.date_list = date_list
        self.timeframe = timeframe
        self.group_date = DatePoint(date_list[0].floor(timeframe))

    @classmethod
    def group_timeframes(cls, datepoint_list, timeframe=Timeframe.day):
        """Group a list of DatePoints by the timeframe they occurred on

        This will return a list of lists. Each of those lists could be
        validly used to construct a TimeframeGroup.
        """
        return [cls(dates) for dates in
                binary_groupby(datepoint_list,
                               lambda x, y: x.same(y, timeframe))]

    @property
    def total_time(self):
        """Get the total time from all component DatePoints"""
        return sum((date.total_time for date in self.date_list),
                   datetime.timedelta())

    def ordinal(self, timeframe=Timeframe.day, use_start=None):
        """Gets the 'prototypical' timeframe's ordinal value"""
        return self.group_date.ordinal(timeframe)

    @property
    def is_range(self):
        """TimeframeGroups are not ranges for the purpose of DatePoint methods"""
        return False

    @property
    def _first_date(self):
        """Return prototypical day for DatePoint compatibility"""
        return self.group_date._first_date
