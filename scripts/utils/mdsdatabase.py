import oci

class MdsDatabase:

    def __init__(self, db, cfg): 
        if not isinstance(db,oci.mysql.models.DbSystem):
            raise TypeError("mdsdatabase init: db parameter must be an instance of oci.mysql.models.DbSystem")
        if not isinstance(cfg,oci.mysql.models.configuration.Configuration):
            raise TypeError("mdsdatabase init: cfg parameter must be an instance of oci.mysql.models.configuration.Configuration")
        self._database = db
        self._config = cfg

    @property
    def database(self):
        return self._database

    @property
    def config(self):
        return self._config


class MdsMetaDatabase:

    def __init__(self, shape_name, config_id):
        if not isinstance(shape_name,str):
            raise TypeError("mdsmetadatabase init: shape_name must be a string")
        if not isinstance(config_id,str):
            raise TypeError("mdsmetadatabase init: cfg_id must be a string")
        self._shape_name = shape_name
        self._config_id = config_id

    @property
    def shape_name(self):
        return self._shape_name

    @property
    def config_id(self):
        return self._config_id
