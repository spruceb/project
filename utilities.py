from contextlib import contextmanager

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

@contextmanager
def current_directory(directory):
    original = os.getcwd()
    if directory is None:
        yield original
    else:
        directory = os.path.realpath(directory)
        os.chdir(directory)
        yield directory
        os.chdir(original)
