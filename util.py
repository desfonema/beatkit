import uuid

try:
    import prctl
except:
    pass


def set_thread_name(name):
    try:
        prctl.set_name(name)
    except:
        pass


def log(data):
    f = open('debug.log', 'a')
    f.write(str(data) + "\n")
    f.close()


def gen_uid():
    return str(uuid.uuid4())[:8]


def ntime(time):
    return int(time * 1000000) / 1000000.
