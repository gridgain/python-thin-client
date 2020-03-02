# pygridgain
GridGain Community Edition thin (binary protocol) client, written in Python 3.

## Prerequisites

- Python 3.4 or above (3.6 is tested),
- Access to GridGain node, local or remote. The current thin client
  version was tested on GridGain CE 8.7 (binary client protocol versions
  1.2.0 to 1.4.0).

## Installation

### From repository
This is a recommended way for users. If you only want to use the `pygridgain`
module in your project, do:
```
$ pip install pygridgain
```

### From sources
This way is more suitable for developers or if you install client from zip archive.
1. Download and/or unzip GridGain Python client sources to `gridgain_client_path`
2. Go to `gridgain_client_path` folder
3. Execute `pip install -e .`

```bash
$ cd <gridgain_client_path>
$ pip install -e .
```

This will install the repository version of `pygridgain` into your environment
in so-called “develop” or “editable” mode. You may read more about
[editable installs](https://pip.pypa.io/en/stable/reference/pip_install/#editable-installs)
in the `pip` manual.

Then run through the contents of `requirements` folder to install
the additional requirements into your working Python environment using
```
$ pip install -r requirements/<your task>.txt
```

You may also want to consult the `setuptools` manual about using `setup.py`.

### Updating from older version

To upgrade an existing package, use the following command:
```
pip install --upgrade pygridgain
```

To install the latest version of a package:

```
pip install pygridgain
```

To install a specific version:

```
pip install pygridgain==1.1.0
```

## Documentation
[The package documentation](https://pygridgain.readthedocs.io) is available
at *RTD* for your convenience.

If you want to build the documentation from source, do the developer
installation as described above, then run the following commands:
```
$ cd pygridgain
$ pip install -r requirements/docs.txt
$ cd docs
$ make html
```

Then open `pygridgain/docs/generated/html/index.html`
in your browser.

## Examples
Some examples of using pygridgain are provided in
`pygridgain/examples` folder. They are extensively
commented in the
“[Examples of usage](https://pygridgain.readthedocs.io/en/latest/examples.html)”
section of the documentation.

This code implies that it is run in the environment with `pygridgain` package
installed, and GridGain node is running on localhost:10800.

## Testing
Run
```
$ python setup.py pytest
```