import sys
import getpass

class Tio(object):

    SCREEN = "screen"
    FILE = "output-file"
    ON = True
    OFF = False

    def __init__(self,file_handle):
        self._screen = True
        self._output_file = True
        self._file_handle = file_handle


    def set_mode(self,dest,mode):
        mode_set = True
        if type(mode) == bool:
            if dest == self.SCREEN:
                self._screen = mode
            elif dest == self.FILE:
                self._output_file = mode
            else:
                mode_set = False
        else:
            mode_set = False

        return mode_set

    def write(self,message):
        if self._screen:
            print(message,end="")
        if self._output_file:
            self._file_handle.write(message)
            self._file_handle.flush()

    def writeln(self,message):
        if self._screen:
            print(message)
        if self._output_file:
            self._file_handle.write(message + "\n")
            self._file_handle.flush()
    
    def input(self,message):
        val = input(message) # prints message to screen
        if self._output_file:
            self._file_handle.write(message + val + "\n")
            self._file_handle.flush()
        return val

    def password_input(self,prompt_message):
        passwd = getpass.getpass(prompt_message)
        if self._output_file:
            self._file_handle.write(prompt_message + "\n")
            self._file_handle.flush()
        return passwd


