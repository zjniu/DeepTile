import gc


class Job:

    """ Job class that stores jobs created by a DeepTile object.

    Parameters
    ----------
        job_input
            Input data for the job.
        job_type : str
            Type of job.
        job_kwargs : dict
            Keyword arguments for the job.
        profile : Profile
            New profile used when ``job_input`` is a tile source.
    """

    def __init__(self, job_input, job_type, job_kwargs, profile=None):

        job_kwargs = job_kwargs.pop('self')

        if profile is None:
            self.profile = job_input.profile
        else:
            self.profile = profile
        self.profile.jobs.append(self)

        self.dt = self.profile.dt

        if self.dt.link_data:
            self.input = job_input
        else:
            self.input = None

        self.id = len(self.profile.jobs)
        self.type = job_type
        self.kwargs = job_kwargs
        self.output = None

        gc.collect()