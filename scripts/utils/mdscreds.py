import re

class MdsCredentialsError(Exception):
    def __init__(self,message):
        super().__init__(message)

class MdsCredentials(object):
    _MIN_PASS_CHARS = 8
    _MAX_PASS_CHARS = 32
    _MIN_USER_CHARS = 1
    _MAX_USER_CHARS = 32
    _REGEX_SET = ["[a-z]","[A-Z]","[0-9]","[^a-zA-Z0-9_]"]
   
    def __init__(self):
        self._username = None
        self._password = None

    def set_username(self,user):
        if self._username is not None:
            self._username = None
        if len(user) < self._MIN_USER_CHARS or len(user) > self._MAX_USER_CHARS:
            raise MdsCredentialsError("Username must contain %s-%s characters." % (self._MIN_USER_CHARS, self._MAX_USER_CHARS))  
        self._username = user;

    def set_password(self,pass1,pass2):
        if self._password is not None:
            self._password = None
        if len(pass1) < self._MIN_PASS_CHARS or len(pass1) > self._MAX_PASS_CHARS:
            raise MdsCredentialsError("Password must contain %s-%s characters." % (self._MIN_USER_CHARS, self._MAX_USER_CHARS)) 
        if len(pass2) < self._MIN_PASS_CHARS or len(pass2) > self._MAX_PASS_CHARS:
            raise MdsCredentialsError("Password must contain %s-%s characters." % (self._MIN_PASS_CHARS, self._MAX_PASS_CHARS))
        if pass1 != pass2:
            raise MdsCredentialsError("Passwords do not match.")
        for regex in self._REGEX_SET:
            if not re.search(regex,pass1):
                raise MdsCredentialsError("Password must contain 1 uppercase character, 1 lowercase character, 1 numeric character, and 1 special character.")
        self._password = pass1

    def get_password(self):
        return self._password

    def get_username(self):
        return self._username
