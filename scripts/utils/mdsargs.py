import os
from pathlib import Path

class MdsargsError(Exception):
    def __init__(self,message):
        super().__init__(message)


class Mdsargs(object):
    HELP = "HELP"
    LOCAL_COPY = "LOCAL_COPY"
    REMOTE_COPY = "REMOTE_COPY"
    RESIZE = "RESIZE"
    REVERT = "REVERT"

    def __init__(self):
        self._action = self.HELP
        self._address = None
        self._comp_ocid = None
        self._db_ocid = None
        self._oci_cfg_file = None
        self._name = None
        self._revert_file = None
        self._subnet_ocid = None
        self._output_dir = None

    @property
    def action(self):
        return self._action

    @action.setter
    def action(self,a):
        if a in (self.HELP, self.RESIZE, self.REVERT, self.LOCAL_COPY, self.REMOTE_COPY):
            self._action = a
        else:
            raise MdsargsError("Unknown action.")

    @property
    def oci_cfg_file(self):
        return self._oci_cfg_file

    @oci_cfg_file.setter
    def oci_cfg_file(self,fname):
        if os.path.isfile(fname) and os.access(fname,os.R_OK):
            self._oci_cfg_file = fname
        else:
            raise MdsargsError("OCI config file is not accessible.")

    @property
    def display_name(self):
        return self._name

    @display_name.setter
    def display_name(self,name):
        self._name = name

    @property
    def revert_file(self):
        return self._revert_file

    @revert_file.setter
    def revert_file(self,fname):
        if os.path.isfile(fname) and os.access(fname,os.W_OK):
            self._revert_file = fname
        else:
            raise MdsargsError("Input revert file is not accessible.")

    @property
    def output_dir(self):
        return self._output_dir

    @output_dir.setter
    def output_dir(self,dirname):
        if os.path.isdir(dirname) == False:
            try:
                path = Path(dirname)
                path.mkdir(parents=True)
            except:
                raise  MdsargsError("Cannot create directory " + dirname + ".")

        if os.path.isdir(dirname) and os.access(dirname,(os.X_OK | os.W_OK)):
            self._output_dir = dirname
        else:
            raise MdsargsError("Directory " + dirname + " is not accessible.")

    @property
    def address(self):
        return self._address

    @address.setter
    def address(self,addr):
        self._address = addr

    @property
    def db_ocid(self):
        return self._db_ocid

    @db_ocid.setter
    def db_ocid(self,ocid):
        self._db_ocid = ocid

    @property
    def comp_ocid(self):
        return self._comp_ocid

    @comp_ocid.setter
    def comp_ocid(self,comp_ocid):
        self._comp_ocid = comp_ocid

    @property
    def subnet_ocid(self):
        return self._subnet_ocid

    @subnet_ocid.setter
    def subnet_ocid(self,subnet_ocid):
        self._subnet_ocid = subnet_ocid
