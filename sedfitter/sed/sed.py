from __future__ import print_function, division

import os

import numpy as np
from astropy import log
from astropy.io import fits
from astropy.table import Table
from scipy.interpolate import interp1d
from astropy import units as u

from ..utils.validator import validate_array

UNIT_MAPPING = {}
UNIT_MAPPING['MICRONS'] = u.micron
UNIT_MAPPING['HZ'] = u.Hz
UNIT_MAPPING['MJY'] = u.mJy
UNIT_MAPPING['ergs/cm^2/s'] = u.erg / u.cm ** 2 / u.s


def parse_unit_safe(unit_string):
    if unit_string in UNIT_MAPPING:
        return UNIT_MAPPING[unit_string]
    else:
        return u.Unit(unit_string, parse_strict=False)


def assert_allclose_quantity(q1, q2):
    if q1 is None and q2 is None:
        return True
    if q1 is None or q2 is None:
        raise AssertionError()
    else:
        np.testing.assert_allclose(q1.value, q2.to(q1.unit).value)


def convert_flux(nu, flux, target_unit):
    """
    Convert flux to a target unit
    """

    curr_unit = flux.unit

    if curr_unit.is_equivalent(u.erg / u.s):
        flux = flux / sed.distance ** 2
    elif curr_unit.is_equivalent(u.Jy):
        flux = flux * nu
    elif not curr_unit.is_equivalent(u.erg / u.cm ** 2 / u.s):
        raise Exception("Don't know how to convert {0} to ergs/cm^2/s" % (flux.unit))

    # Convert to requested unit

    if target_unit.is_equivalent(u.erg / u.s):
        flux = flux * sed.distance ** 2
    elif target_unit.is_equivalent(u.Jy):
        flux = flux / nu
    elif not target_unit.is_equivalent(u.erg / u.cm ** 2 / u.s):
        raise Exception("Don't know how to convert %s to %s" % (curr_unit, unit_flux))

    return flux.to(target_unit)


class SED(object):

    def __init__(self):

        # Metadata
        self.name = None
        self.distance = None

        # Spectral info
        self.wav = None
        self.nu = None

        # Apertures
        self.apertures = None

        # Fluxes
        self.stellar_flux = None
        self.flux = None
        self.error = None

        # Polarizations
        self.linpol = None
        self.linpol_error = None
        self.circpol = None
        self.circpol_error = None

    def __eq__(self, other):

        try:

            assert self.name == other.name

            assert_allclose_quantity(self.distance, other.distance)

            assert_allclose_quantity(self.wav, other.wav)
            assert_allclose_quantity(self.nu, other.nu)
            assert_allclose_quantity(self.stellar_flux, other.stellar_flux)

            assert_allclose_quantity(self.apertures, other.apertures)

            assert_allclose_quantity(self.flux, other.flux)
            assert_allclose_quantity(self.error, other.error)

            assert_allclose_quantity(self.linpol, other.linpol)
            assert_allclose_quantity(self.linpol_error, other.linpol_error)
            assert_allclose_quantity(self.circpol, other.circpol)
            assert_allclose_quantity(self.circpol_error, other.circpol_error)

        except AssertionError:
            raise
            return False
        else:
            return True

    def copy(self):
        from copy import deepcopy
        return deepcopy(self)

    def scale_to_distance(self, distance):
        """
        Returns the SED scaled to distance `distance`

        Parameters
        ----------
        distance : float
            The distance in cm

        Returns
        -------
        sed : SED
            The SED, scaled to the new distance
        """
        sed = self.copy()
        sed.distance = distance * u.cm
        sed.flux = sed.flux * (self.distance.to(u.cm) / sed.distance) ** 2
        sed.error = sed.error * (self.distance.to(u.cm) / sed.distance) ** 2
        return sed

    def scale_to_av(self, av, law):
        sed = self.copy()
        sed.flux = sed.flux * 10. ** (av * law(sed.wav))
        sed.error = sed.error * 10. ** (av * law(sed.wav))
        return sed

    @property
    def wav(self):
        """
        The wavelengths at which the SED is defined
        """
        if self._wav is None and self._nu is not None:
            return self._nu.to(u.micron, equivalencies=u.spectral())
        else:
            return self._wav

    @wav.setter
    def wav(self, value):
        if value is None:
            self._wav = None
        else:
            self._wav = validate_array('wav', value, domain='positive', ndim=1,
                                       shape=None if self.nu is None else (len(self.nu),),
                                       physical_type='length')

    @property
    def nu(self):
        """
        The frequencies at which the SED is defined
        """
        if self._nu is None and self._wav is not None:
            return self._wav.to(u.Hz, equivalencies=u.spectral())
        else:
            return self._nu

    @nu.setter
    def nu(self, value):
        if value is None:
            self._nu = None
        else:
            self._nu = validate_array('nu', value, domain='positive', ndim=1,
                                      shape=None if self.wav is None else (len(self.wav),),
                                      physical_type='frequency')

    @property
    def apertures(self):
        """
        The apertures at which the SED is defined
        """
        return self._apertures

    @apertures.setter
    def apertures(self, value):
        if value is None:
            self._apertures = None
        else:
            self._apertures = validate_array('apertures', value, domain='positive',
                                             ndim=1, physical_type='length')

    @property
    def flux(self):
        """
        The SED fluxes
        """
        return self._flux

    @flux.setter
    def flux(self, value):
        if value is None:
            self._flux = value
        else:
            self._flux = validate_array('flux', value, ndim=2,
                                        shape=(self.n_ap, self.n_wav),
                                        physical_type=('power', 'flux', 'spectral flux density'))

    @property
    def error(self):
        """
        The convolved flux errors
        """
        return self._error

    @error.setter
    def error(self, value):
        if value is None:
            self._error = value
        else:
            self._error = validate_array('error', value, ndim=2,
                                         shape=(self.n_ap, self.n_wav),
                                         physical_type=('power', 'flux', 'spectral flux density'))

    @property
    def stellar_flux(self):
        """
        The fluxes from the central object
        """
        return self._stellar_flux

    @stellar_flux.setter
    def stellar_flux(self, value):
        if value is None:
            self._stellar_flux = value
        else:
            self._stellar_flux = validate_array('stellar_flux', value, ndim=1,
                                                shape=(self.n_wav,),
                                                physical_type=('power', 'flux', 'spectral flux density'))

    @property
    def linpol(self):
        """
        The linear polarization values
        """
        return self._linpol

    @linpol.setter
    def linpol(self, value):
        if value is None:
            self._linpol = value
        else:
            self._linpol = validate_array('linpol', value, ndim=2,
                                          shape=(self.n_ap, self.n_wav),
                                          physical_type=('dimensionless'))

    @property
    def linpol_error(self):
        """
        The linear polarization error values
        """
        return self._linpol_error

    @linpol_error.setter
    def linpol_error(self, value):
        if value is None:
            self._linpol_error = value
        else:
            self._linpol_error = validate_array('linpol_error', value, ndim=2,
                                                shape=(self.n_ap, self.n_wav),
                                                physical_type=('dimensionless'))

    @property
    def circpol(self):
        """
        The circular polarization values
        """
        return self._circpol

    @circpol.setter
    def circpol(self, value):
        if value is None:
            self._circpol = value
        else:
            self._circpol = validate_array('circpol', value, ndim=2,
                                          shape=(self.n_ap, self.n_wav),
                                          physical_type=('dimensionless'))

    @property
    def circpol_error(self):
        """
        The circular polarization error values
        """
        return self._circpol_error

    @circpol_error.setter
    def circpol_error(self, value):
        if value is None:
            self._circpol_error = value
        else:
            self._circpol_error = validate_array('circpol_error', value, ndim=2,
                                                shape=(self.n_ap, self.n_wav),
                                                physical_type=('dimensionless'))

    @property
    def n_ap(self):
        if self.apertures is None:
            return 1
        else:
            return len(self.apertures)

    @property
    def n_wav(self):
        if self.wav is None:
            return None
        else:
            return len(self.wav)

    @classmethod
    def read(cls, filename, unit_wav=u.micron, unit_freq=u.Hz,
             unit_flux=u.erg / u.cm ** 2 / u.s, order='nu'):
        """
        Read an SED from a FITS file.

        Parameters
        ----------
        filename: str
            The name of the file to read the SED from.
        unit_wav: `~astropy.units.Unit`, optional
            The units to convert the wavelengths to.
        unit_freq: `~astropy.units.Unit`, optional
            The units to convert the frequency to.
        unit_flux: `~astropy.units.Unit`, optional
            The units to convert the flux to.
        order: str, optional
            Whether to sort the SED by increasing wavelength (`wav`) or
            frequency ('nu').
        """

        # Instantiate SED class
        sed = cls()

        # Assume that the filename may be missing the .gz extension
        if not os.path.exists(filename) and os.path.exists(filename + '.gz'):
            filename += ".gz"

        # Open FILE file
        hdulist = fits.open(filename, memmap=False)

        # Extract model name
        sed.name = hdulist[0].header['MODEL']

        # Check if distance is specified in header, otherwise assume 1kpc
        if 'DISTANCE' in hdulist[0].header:
            sed.distance = hdulist[0].header['DISTANCE'] * u.cm
        else:
            log.debug("No distance found in SED file, assuming 1kpc")
            sed.distance = 1. * u.kpc

        # Extract SED values
        wav = hdulist[1].data.field('WAVELENGTH') * parse_unit_safe(hdulist[1].columns[0].unit)
        nu = hdulist[1].data.field('FREQUENCY') * parse_unit_safe(hdulist[1].columns[1].unit)
        ap = hdulist[2].data.field('APERTURE') * parse_unit_safe(hdulist[2].columns[0].unit)
        flux = hdulist[3].data.field('TOTAL_FLUX') * parse_unit_safe(hdulist[3].columns[0].unit)
        error = hdulist[3].data.field('TOTAL_FLUX_ERR') * parse_unit_safe(hdulist[3].columns[1].unit)

        # Set SED attributes
        sed.apertures = ap

        # Convert wavelength and frequencies to requested units
        sed.wav = wav.to(unit_wav)
        sed.nu = nu.to(unit_freq)

        # Set fluxes
        sed.flux = convert_flux(nu, flux, unit_flux)
        sed.error = convert_flux(nu, error, unit_flux)

        # Set stellar flux (if present)
        if 'STELLAR_FLUX' in hdulist[1].data.dtype.names:
            stellar_flux = hdulist[1].data.field('STELLAR_FLUX') * parse_unit_safe(hdulist[1].columns[2].unit)
            sed.stellar_flux = convert_flux(nu, stellar_flux, unit_flux)
        else:
            stellar_flux = None

        # Set polarization (if present)
        if len(hdulist) > 4:
            if 'LINPOL' in hdulist[4].data.dtype.names:
                sed.linpol = hdulist[4].data.field('LINPOL') * u.percent
            if 'LINPOL_ERROR' in hdulist[4].data.dtype.names:
                sed.linpol_error = hdulist[4].data.field('LINPOL_ERROR') * u.percent
            if 'CIRCPOL' in hdulist[4].data.dtype.names:
                sed.circpol = hdulist[4].data.field('CIRCPOL') * u.percent
            if 'CIRCPOL_ERROR' in hdulist[4].data.dtype.names:
                sed.circpol_error = hdulist[4].data.field('CIRCPOL_ERROR') * u.percent

        # Sort SED

        if order not in ('nu', 'wav'):
            raise ValueError('order should be nu or wav')

        if (order == 'nu' and sed.nu[0] > sed.nu[-1]) or \
           (order == 'wav' and sed.wav[0] > sed.wav[-1]):
            sed.wav = sed.wav[::-1]
            sed.nu = sed.nu[::-1]
            sed.flux = sed.flux[..., ::-1]
            sed.error = sed.error[..., ::-1]

        return sed

    def write(self, filename, overwrite=False):
        """
        Write an SED to a FITS file.

        Parameters
        ----------
        filename: str
            The name of the file to write the SED to.
        """

        # Create first HDU with meta-data
        hdu0 = fits.PrimaryHDU()

        if self.name is None:
            raise ValueError("Model name is not set")
        else:
            hdu0.header['MODEL'] = self.name

        if self.distance is None:
            raise ValueError("Model distance is not set")
        else:
            hdu0.header['DISTANCE'] = self.distance.to(u.cm).value

        hdu0.header['NAP'] = self.n_ap
        hdu0.header['NWAV'] = self.n_wav

        # Create wavelength table
        twav = Table()
        if self.wav is None:
            raise ValueError("Wavelengths are not set")
        else:
            twav['WAVELENGTH'] = self.wav
        if self.nu is None:
            raise ValueError("Frequencies are not set")
        else:
            twav['FREQUENCY'] = self.nu
        if self.stellar_flux is not None:
            twav['STELLAR_FLUX'] = self.stellar_flux
        twav.sort('FREQUENCY')

        # TODO: here sorting needs to be applied to fluxes too?

        hdu1 = fits.BinTableHDU(np.array(twav))
        hdu1.columns[0].unit = self.wav.unit.to_string(format='fits')
        hdu1.columns[1].unit = self.nu.unit.to_string(format='fits')
        if self.stellar_flux is not None:
            hdu1.columns[2].unit = self.stellar_flux.unit.to_string(format='fits')
        hdu1.header['EXTNAME'] = "WAVELENGTHS"

        # Create aperture table
        tap = Table()
        if self.apertures is None:
            tap['APERTURE'] = [1.e-30]
        else:
            tap['APERTURE'] = self.apertures
        hdu2 = fits.BinTableHDU(np.array(tap))
        if self.apertures is None:
            hdu2.columns[0].unit = 'cm'
        else:
            hdu2.columns[0].unit = self.apertures.unit.to_string(format='fits')
        hdu2.header['EXTNAME'] = "APERTURES"

        # Create flux table
        tflux = Table()
        tflux['TOTAL_FLUX'] = self.flux
        if self.flux is None:
            raise ValueError("Fluxes are not set")
        else:
            tflux['TOTAL_FLUX'] = self.flux
        if self.error is None:
            raise ValueError("Errors are not set")
        else:
            tflux['TOTAL_FLUX_ERR'] = self.error
        hdu3 = fits.BinTableHDU(np.array(tflux))
        hdu3.columns[0].unit = self.flux.unit.to_string(format='fits')
        hdu3.columns[1].unit = self.error.unit.to_string(format='fits')
        hdu3.header['EXTNAME'] = "SEDS"

        hdus = [hdu0, hdu1, hdu2, hdu3]

        if self.linpol is not None or self.circpol is not None:

            tflux = Table()

            if self.linpol is not None:
                tflux['LINPOL'] = self.linpol
            if self.linpol_error is not None:
                tflux['LINPOL_ERROR'] = self.linpol_error
            if self.circpol is not None:
                tflux['CIRCPOL'] = self.circpol
            if self.circpol_error is not None:
                tflux['CIRCPOL_ERROR'] = self.circpol_error

            hdu4 = fits.BinTableHDU(np.array(tflux))
            hdu4.header['EXTNAME'] = "POLARIZATION"

            hdus.append(hdu4)

        # Create overall FITS file
        hdulist = fits.HDUList(hdus)

        # if filename.endswith('.gz'):
        #     g = gzip.open(filename, 'wb')
        #     hdulist.writeto(g, clobber=overwrite)
        #     g.close()
        # else:
        #     hdulist.writeto(filename, clobber=overwrite)

        if '.gz' in filename:
            import gzip
            from tempfile import NamedTemporaryFile
            f = NamedTemporaryFile()
            hdulist.writeto(f)
            g = gzip.open(filename, 'wb')
            content = open(f.name, 'rb').read()
            g.write(content)
            g.close()
            f.close()
        else:
            hdulist.writeto(filename, clobber=overwrite)



    def interpolate(self, apertures):
        """
        Interpolate the SED to different apertures
        """

        # If there is only one aperture, we can't interpolate, we can only repeat
        if self.n_ap == 1:
            return np.repeat(self.flux[0, :], len(apertures)).reshape(self.n_wav, len(apertures))

        # Create interpolating function
        flux_interp = interp1d(self.apertures, self.flux.swapaxes(0, 1))

        # If any apertures are larger than the defined max, reset to max
        apertures[apertures > self.apertures.max()] = self.apertures.max()

        # If any apertures are smaller than the defined min, raise Exception
        if np.any(apertures < self.apertures.min()):
            raise Exception("Aperture(s) requested too small")

        return flux_interp(apertures)

    def interpolate_variable(self, wavelengths, apertures):
        """
        Interpolate the SED to a variable aperture as a function of
        wavelength. This method should be called with an interpolating
        function for aperture as a function of wavelength, in log10 space.
        """

        if self.n_ap == 1:
            return self.flux[0, :]

        sed_apertures = self.apertures.to(u.au).value
        sed_wav = self.wav.to(u.micron).value

        # If any apertures are larger than the defined max, reset to max
        apertures[apertures > sed_apertures.max()] = sed_apertures.max() * 0.999

        # If any apertures are smaller than the defined min, raise Exception
        if np.any(apertures < sed_apertures.min()):
            raise Exception("Aperture(s) requested too small")

        # Find wavelength order
        order = np.argsort(wavelengths)

        # Interpolate apertures vs wavelength
        log10_ap_interp = interp1d(np.log10(wavelengths[order]), np.log10(apertures[order]), bounds_error=False, fill_value=np.nan)

        # Create interpolating function
        flux_interp = interp1d(sed_apertures, self.flux.swapaxes(0, 1))

        # Interpolate the apertures
        apertures = 10. ** log10_ap_interp(np.log10(sed_wav))

        # Extrapolate on either side
        apertures[np.log10(sed_wav) < log10_ap_interp.x[0]] = 10. ** log10_ap_interp.y[0]
        apertures[np.log10(sed_wav) > log10_ap_interp.x[-1]] = 10. ** log10_ap_interp.y[-1]

        # Interpolate and return only diagonal elements
        return flux_interp(apertures).diagonal()
