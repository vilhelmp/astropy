# Licensed under a 3-clause BSD style license - see LICENSE.rst
"""
``fitscheck`` is a command line script based on astropy.io.fits for verifying
and updating the CHECKSUM and DATASUM keywords of .fits files.  ``fitscheck``
can also detect and often fix other FITS standards violations.  ``fitscheck``
facilitates re-writing the non-standard checksums originally generated by
astropy.io.fits with standard checksums which will interoperate with CFITSIO.

``fitscheck`` will refuse to write new checksums if the checksum keywords are
missing or their values are bad.  Use ``--force`` to write new checksums
regardless of whether or not they currently exist or pass.  Use
``--ignore-missing`` to tolerate missing checksum keywords without comment.

Example uses of fitscheck:

1. Add checksums::

    $ fitscheck --write *.fits

2. Write new checksums, even if existing checksums are bad or missing::

    $ fitscheck --write --force *.fits

3. Verify standard checksums and FITS compliance without changing the files::

    $ fitscheck --compliance *.fits

4. Only check and fix compliance problems,  ignoring checksums::

    $ fitscheck --checksum none --compliance --write *.fits

5. Verify standard interoperable checksums::

    $ fitscheck *.fits

6. Delete checksum keywords::

    $ fitscheck --checksum remove --write *.fits

"""


import argparse
import logging
import sys

from astropy.tests.helper import catch_warnings
from astropy.io import fits


log = logging.getLogger('fitscheck')

_DESCRIPTION = """
e.g. fitscheck example.fits

Verifies and optionally re-writes the CHECKSUM and DATASUM keywords
for a .fits file.
Optionally detects and fixes FITS standard compliance problems.
"""


def handle_options(args):
    if not len(args):
        args = ['-h']

    parser = argparse.ArgumentParser(
        description=_DESCRIPTION,
        formatter_class=argparse.RawDescriptionHelpFormatter)

    parser.add_argument(
        'fits_files', metavar='file', nargs='+',
        help='.fits files to process.')

    parser.add_argument(
        '-k', '--checksum', dest='checksum_kind',
        choices=['standard', 'remove', 'none'],
        help='Choose FITS checksum mode or none.  Defaults standard.',
        default='standard')

    parser.add_argument(
        '-w', '--write', dest='write_file',
        help='Write out file checksums and/or FITS compliance fixes.',
        default=False, action='store_true')

    parser.add_argument(
        '-f', '--force', dest='force',
        help='Do file update even if original checksum was bad.',
        default=False, action='store_true')

    parser.add_argument(
        '-c', '--compliance', dest='compliance',
        help='Do FITS compliance checking; fix if possible.',
        default=False, action='store_true')

    parser.add_argument(
        '-i', '--ignore-missing', dest='ignore_missing',
        help='Ignore missing checksums.',
        default=False, action='store_true')

    parser.add_argument(
        '-v', '--verbose', dest='verbose', help='Generate extra output.',
        default=False, action='store_true')

    global OPTIONS
    OPTIONS = parser.parse_args(args)

    if OPTIONS.checksum_kind == 'none':
        OPTIONS.checksum_kind = False
    elif OPTIONS.checksum_kind == 'remove':
        OPTIONS.write_file = True
        OPTIONS.force = True

    return OPTIONS.fits_files


def setup_logging():
    if OPTIONS.verbose:
        log.setLevel(logging.INFO)
    else:
        log.setLevel(logging.WARNING)

    handler = logging.StreamHandler()
    handler.setFormatter(logging.Formatter('%(message)s'))
    log.addHandler(handler)


def verify_checksums(filename):
    """
    Prints a message if any HDU in `filename` has a bad checksum or datasum.
    """
    # TODO: Attempt to replace catch_warnings with builtin Python
    # warnings.catch_warnings failed, possibly due to
    # https://github.com/pytest-dev/pytest/issues/5502 . Revisit in the future.
    with catch_warnings() as wlist:
        with fits.open(filename, checksum=OPTIONS.checksum_kind) as hdulist:
            for i, hdu in enumerate(hdulist):
                # looping on HDUs is needed to read them and verify the
                # checksums
                if not OPTIONS.ignore_missing:
                    if not hdu._checksum:
                        log.warning('MISSING {!r} .. Checksum not found '
                                    'in HDU #{}'.format(filename, i))
                        return 1
                    if not hdu._datasum:
                        log.warning('MISSING {!r} .. Datasum not found '
                                    'in HDU #{}'.format(filename, i))
                        return 1

    for w in wlist:
        if str(w.message).startswith(('Checksum verification failed',
                                      'Datasum verification failed')):
            log.warning('BAD %r %s', filename, str(w.message))
            return 1

    log.info(f'OK {filename!r}')
    return 0


def verify_compliance(filename):
    """Check for FITS standard compliance."""

    with fits.open(filename) as hdulist:
        try:
            hdulist.verify('exception')
        except fits.VerifyError as exc:
            log.warning('NONCOMPLIANT %r .. %s',
                        filename, str(exc).replace('\n', ' '))
            return 1
    return 0


def update(filename):
    """
    Sets the ``CHECKSUM`` and ``DATASUM`` keywords for each HDU of `filename`.

    Also updates fixes standards violations if possible and requested.
    """

    output_verify = 'silentfix' if OPTIONS.compliance else 'ignore'
    with fits.open(filename, do_not_scale_image_data=True,
                   checksum=OPTIONS.checksum_kind, mode='update') as hdulist:
        hdulist.flush(output_verify=output_verify)


def process_file(filename):
    """
    Handle a single .fits file,  returning the count of checksum and compliance
    errors.
    """

    try:
        checksum_errors = verify_checksums(filename)
        if OPTIONS.compliance:
            compliance_errors = verify_compliance(filename)
        else:
            compliance_errors = 0
        if OPTIONS.write_file and checksum_errors == 0 or OPTIONS.force:
            update(filename)
        return checksum_errors + compliance_errors
    except Exception as e:
        log.error(f'EXCEPTION {filename!r} .. {e}')
        return 1


def main(args=None):
    """
    Processes command line parameters into options and files,  then checks
    or update FITS DATASUM and CHECKSUM keywords for the specified files.
    """

    errors = 0
    fits_files = handle_options(args or sys.argv[1:])
    setup_logging()
    for filename in fits_files:
        errors += process_file(filename)
    if errors:
        log.warning(f'{errors} errors')
    return int(bool(errors))
