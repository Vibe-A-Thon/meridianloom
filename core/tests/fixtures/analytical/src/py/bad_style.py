"""Convention-violating fixture: bad names and a banned import."""

import subprocess


def BadFunction():
    subprocess.run(["echo", "hi"])
    return 1


class my_class:
    pass
