try:
    import prctl
except:
    pass


def set_thread_name(name):
    try:
        prctl.set_name(name)
    except:
        pass
