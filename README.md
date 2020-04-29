# libarc1: Minimal interface to ArC1

## Scope

Libarc1 provides a minimal way to interact with ArC1. Sometimes you need a
custom testing procedure that operates independently of the full ArC1
interface. Libarc1 enables you to build your own testing frameworks by
leveraging the capabilities of the instrument without employing the graphical
user interface. That being said libarc1 only provices a shell around the
read/write operations as well as most of the modules. Complex processing or
visualisation are beyond the scope of this library and are left to user to
develop as they see fit. Please note that libarc1 is not meant to be used in
conjuction with the ArC ONE control software but instead it's here to help you
develop application-specific tools based on the ArC1 platform.

## Requirements

You need at least Python 3.6 to use this library. Other than that libarc1 only
depends on numpy and pyserial. If you're installing with `pip` these will be
taken care for you.

## Installation

As libarc1 is still in early stages of development it's not available in PyPI
and you should use it directly from the repository. If you have `pip` ≥ 19.0
you can point `pip` directly to the source repository

```bash
pip install git+https://github.com/arc-instruments/libarc1
```

Otherwise see the [Development](#development) section below on how to install
`poetry`. Using `poetry build` you will get a wheel file in the `dist`
folder that's installable with `pip` as usual.

## Usage

In the simplest form one can write

```python
from libarc1 import ArC1, ArC1Conf

# initialise the ArC1 board. Port is platform specific; shown here for Linux.
# libarc1 will take care of initialising the board with sane defaults
arc1 = ArC1('/dev/ttyACM0')

# alternatively a configuration can be provided as well
# conf = ArC1Conf()
# set read voltage to 0.2 V
# conf.Vread = 0.2
# arc1 = ArC1('/dev/ttyACM0', config=conf)

# read a single device at W=2, B=7
resistance = arc1.read_one(2, 7)

# pulse a device with a 100 us pulse @ 2.5 V and read its state
resistance = arc1.pulseread_one(2, 7, 2.5, 100e-6)

# select a device (W=5, B=12) by closing a specified crosspoint
arc1.select(5, 12)

# pulse the device without reading it
arc1.pulse_active(2.5, 100e-6)

# read all devices
for datum in arc1.read_all():
    # will print current word-/bitline, resistance and amplitude
    print(datum)

```

Higher level functionality is provided in the form of *modules* which provide a
self-contained test routine. In fact the `read_all()` method is also
implemented as a higer level module. Modules generally run in a separate thread
(as they are I/O constrained anyway) and they populate an internal buffer. The
user-facing API has been kept simple to abstract all this away from the user.

```python
from libarc1 import ArC1, ArC1Conf
from libarc1.modules.curvetracer import CurveTracer

# let's get the CurveTracer's default configuration
conf = CurveTracer.default_config
# and change the number of cycles to 5
conf["cycles"] = 5

# will run the module on these crosspoints
devs = [(5, 7), (9, 12)]

# Run it!
# Please note: You don't need to instantiate CurveTracer. Just the class
# is enough as libarc1 will take care of instatiating the module with the
# appropriate configuration and running it in a separate thread
for datum in arc1.run_module(CurveTracer, devs, conf):
    # will return word-/bitline, voltage, resistance, current and cycle nr.
    print(x)

```

## Development

If you want to develop on libarc1 start by cloning the repository. The build
system requires `poetry` which can by installed using `pip`. Then `poetry
install` will fetch the dependencies and install them in an appropriate virtual
environment. See [the documentation](https://python-poetry.org/docs/) for more
info.
