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
