#!/usr/bin/python
from common.util import *

__author__ = 'S. Federici (DESY)'
__version__ = '0.1.0'


class CleanMosaic(object):
    def __init__(self, obs, scale_data):
        """
        Clean HI and CO mosaics from artifacts
        """
        self.survey = obs.survey
        self.mosaic = obs.mosaic
        self.species = obs.species
        self.type = obs.type

        self.logger = initLogger(self.survey + '_' + self.mosaic + '_' + self.species + '_CleanMosaic')
        path, flag = '', ''

        if self.species == 'HI':
            if self.survey == 'CGPS':
                path = getPath(self.logger, key="lustre_cgps_hi")
            if self.survey == 'SGPS':
                path = getPath(self.logger, key="lustre_sgps_hi")
            if self.survey == 'VGPS':
                path = getPath(self.logger, key="lustre_vgps_hi")
        elif self.species == 'CO':
            path = getPath(self.logger, key="lustre_cgps_co")
        else:
            self.logger.critical("This module can only be used with HI and CO species.")
            sys.exit(0)

        if not (self.survey == 'CGPS' or self.survey == 'SGPS' or self.survey == 'VGPS'):
            self.logger.critical("This module can only be used with CGPS, SGPS and VGPS.")
            sys.exit(0)

        filename = self.survey + '_' + self.mosaic + '_' + self.species + '_line_image_clean.fits'
        file = path + filename
        checkForFiles(self.logger, [file], existence=True)

        self.logger.info("Getting the data from...")
        self.logger.info("%s" % obs.filename)

        # Get emission data and velocity interval
        # ndim = len(obs.observation.shape)
        # if ndim == 3:
        #	Tb = obs.observation[:,:,:]
        # else:
        #	Tb = obs.observation[0,:,:,:]

        Tb = obs.observation[:, :, :, :].astype(float32)
        dv = fabs(obs.dz / 1000.)  # [velocity] = km s-1
        vel = obs.zarray / 1000.
        zmin = obs.zmin
        zmax = obs.zmax

        # free memory
        del obs.observation
        del obs.zarray
        # print Tb.shape,zmin,zmax
        # exit(0)
        if self.species == 'HI':

            # Data correction
            # Using Multiprocessing if enough cpus are available
            import multiprocessing
            ncpu = glob_ncpu  # int(ceil(multiprocessing.cpu_count()/1))
            self.logger.info("Running on %i cpu(s)" % (ncpu))

            if self.survey == 'CGPS' or self.survey == 'VGPS':

                # Get HI continuum data
                pathc = getPath(self.logger, self.survey.lower() + '_hi_continuum')
                continuum = pathc + self.survey + '_' + self.mosaic + '_1420_MHz_I_image.fits'
                checkForFiles(self.logger, [continuum])
                data, header = pyfits.getdata(continuum, 0, header=True)
                if self.survey == 'CGPS': cdata = data[0, 0, :, :]
                if self.survey == 'VGPS':
                    long = int(self.mosaic.split('G0')[1])
                    if long <= 45:
                        cdata = data[0, 0, 247:-248, :]
                    elif long <= 61:
                        cdata = data[0, 0, 52:-53, :]
                    elif long == 65:
                        cdata = data[0, 0, 52:-53, 50:-50]

                self.logger.info("Removing artifacts due to continuum subtraction...")
                if ncpu > 1:
                    import itertools
                    samples_list = array_split(Tb[0, zmin:zmax, :, :], ncpu)
                    # print Tb.shape, cdata.shape
                    pool = multiprocessing.Pool(processes=ncpu)
                    results = pool.map(correct_continuum, itertools.izip(samples_list, itertools.repeat(cdata)))
                    pool.close()
                    pool.join()
                    Tb[0, zmin:zmax, :, :] = concatenate(results).astype(Tb.dtype)
                    del samples_list
                    del results
                else:
                    Tb[0, zmin:zmax, :, :] = correct_continuum((Tb[0, zmin:zmax, :, :], cdata))

                del cdata

            if self.survey == 'SGPS':
                vec = []
                vec = [obs.xarray, obs.yarray, vel, dv, self.mosaic]
                Tb[0, zmin:zmax, :, :] = correct_continuum2((Tb[0, zmin:zmax, :, :], vec))

            self.logger.info("Smoothing negative pixels...")
            if ncpu > 1:
                samples_list = array_split(Tb[0, zmin:zmax, :, :], ncpu)
                pool = multiprocessing.Pool(processes=ncpu)
                results = pool.map(correct_data, samples_list)
                pool.close()
                pool.join()
                Tb[0, zmin:zmax, :, :] = concatenate(results).astype(Tb.dtype)
                del samples_list
                del results
            else:
                Tb[0, zmin:zmax, :, :] = correct_data(Tb[0, zmin:zmax, :, :])
            Tb[Tb < -50.] = 0.
        elif self.species == 'CO':

            self.logger.info("Applying Moment Mask method (T.M.Dame)...")
            Tb[0, :, :, :] = moment_mask(self.logger, Tb[0, :, :, :], zmax, obs.dx, dv)

        obs.keyword['datamin'] = amin(Tb)
        obs.keyword['datamax'] = amax(Tb)

        obs.keyword['minfil'] = unravel_index(argmin(Tb), Tb.shape)[1]
        obs.keyword['mincol'] = unravel_index(argmin(Tb), Tb.shape)[2]
        obs.keyword['minrow'] = unravel_index(argmin(Tb), Tb.shape)[3]

        obs.keyword['maxfil'] = unravel_index(argmax(Tb), Tb.shape)[1]
        obs.keyword['maxcol'] = unravel_index(argmax(Tb), Tb.shape)[2]
        obs.keyword['maxrow'] = unravel_index(argmax(Tb), Tb.shape)[3]

        # Output file
        # results = pyfits.CompImageHDU(Tb[0],obs.keyword,'image')
        results = pyfits.PrimaryHDU(Tb, obs.keyword)
        if scale_data:
            results.scale('int16', '', bscale=obs.bscale, bzero=obs.bzero)
            self.logger.info("Writing scaled data to a fits file in...")
        else:
            self.logger.info("Writing data to a fits file in...")
        results.writeto(file, output_verify='fix')
        # results.writeto('/afs/ifh.de/group/that/work-sf/survey/batch/sgps/hi/test.fits', output_verify='fix')
        self.logger.info("%s" % path)
        self.logger.info("Done")
