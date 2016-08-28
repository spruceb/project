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
