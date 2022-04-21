import oci

class ConfigBuilder(object):

    # Public constants
    OPTION = "mysql_option_name"
    SOURCE = "source_value"
    SUGGESTED = "suggested_value"
    TARGET = "target_value"

    def __init__(self,src,tgt):

        if not isinstance(src,oci.mysql.models.configuration.Configuration):
            raise TypeError("src attribute must be set to an instance of oci.mysql.models.Configuration")
        if not isinstance(tgt,oci.mysql.models.configuration.Configuration):
            raise TypeError("tgt attribute must be set to an instance of oci.mysql.models.Configuration")

        # Private variables
        self._sv = src.variables
        self._tv = tgt.variables
        self._keys = tgt.variables.attribute_map.keys()
        self._cfg_dict = None

    def __get_wip_dict(self):
        wip = dict()
        for k in self._keys:
            s = getattr(self._sv,k)
            t = getattr(self._tv,k)
            if s is None:
                if t is not None:
                    wip.update({k: {ConfigBuilder.OPTION: k, ConfigBuilder.SUGGESTED: t, ConfigBuilder.SOURCE: s, ConfigBuilder.TARGET: t}})
            elif t is None:
                wip.update({k: {ConfigBuilder.OPTION: k, ConfigBuilder.SUGGESTED: s, ConfigBuilder.SOURCE: s, ConfigBuilder.TARGET: t}})
            else:
                if s != t:
                    wip.update({k: {ConfigBuilder.OPTION: k, ConfigBuilder.SUGGESTED: t, ConfigBuilder.SOURCE: s, ConfigBuilder.TARGET: t}})
        return wip

    def get_config(self):
        # Create a ConfigurationVariables object then assign values to it from either those that
        # have been specified in self._cfg_dict or from the target config variables (self._tv)
        cfg = oci.mysql.models.configuration_variables.ConfigurationVariables()
        for k in self._keys:
            if k in self._cfg_dict:
                setattr(cfg,k,self._cfg_dict[k])
            else:
                setattr(cfg,k,getattr(self._tv,k))
        return cfg

    def iterator(self):
        self._cfg_dict = dict()
        return ConfigIterator(self.__get_wip_dict())

    def requires_new_config(self):
        for k in self._cfg_dict.keys():
            if self._cfg_dict[k] != getattr(self._tv,k):
                return True
        return False

    def set_config_item(self,k,v):
        if k in self._keys and type(v) == type(getattr(self._tv,k)):
            self._cfg_dict.update({k: v})
            return True
        return False


class ConfigIterator(object):

    def __init__(self,input_dict):
        self._input_dict = input_dict
        self._iter = iter(self._input_dict)

    def next(self):
        try:
            return self._input_dict[next(self._iter)]
        except:
            return None
