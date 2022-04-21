# mdsac
MySQL Database as Code. A script developed to resize and copy MySQL Database Service instances in the Oracle Cloud (OCI). The script leverages the [OCI Python SDK](https://oracle-cloud-infrastructure-python-sdk.readthedocs.io/en/latest/api/landing.html). Its usage is described below:

./mdsac.py -h

./mdsac.py -a RESIZE -D \<database-ocid\> \[-d \<directory-name\> -o \<oci-conf-file\>\]

./mdsac.py -a REVERT -R \<revert-file\> \[-d \<directory-name\> -o \<oci-conf-file\>\]

./mdsac.py -a LOCAL_COPY -D \<database-ocid\> \[-A \<ip-address\> -N \<name\> -d \<directory-name\> -o \<oci-conf-file\>\]

./mdsac.py -a REMOTE_COPY -D \<database-ocid\> -C \<compartment-ocid\> -S \<subnet-ocid\> \[-A \<ip-address\> -N \<name\> -d \<directory-name\> -o \<oci-conf-file\>\]


Modal Flags
===========

-h | --help

  Displays this page. If help is requested then this page will be displayed
  regardless of any other actions being requested or flags used.

-a | --action <RESIZE | REVERT | LOCAL_COPY | REMOTE_COPY>

  The argument to the action flag must be one of the options specified above.

  RESIZE
    The resize action will resize the database specified by the database
    option. The resized database will be hosted in the same compartment
    and database as the original. It will also keep the same name and IP
    address and so there should be no need to change any connecting clients.
    When a database is resized it will create a revert file which provides
    an easy rollback path to its former size.

  REVERT
    Will revert a resized database to its former size. The reverted database
    will keep the same name and IP address and so there should be no need to
    change any connecting clients.

  LOCAL_COPY
    Copies and optionally resizes a database. The copy will be hosted in the
    same compartment and subnet as the original. The copy will have a new
    name and IP address which will automatically be provided unless specified
    otherwise on the command line.

  REMOTE_COPY
    Copies and optionally resizes a database. The copy will be hosted in a
    different subnet to the original. This subnet can be in a different
    compartment. The copy will have a new name and IP address. The copy will
    have a new name and IP address which will automatically be provided unless
    specified otherwise on the command line.

Additional Action Flags
=======================

-d | --output-dir <directory-name>

   An optional flag and argument that can be used with all actions. If this
   flag and argument is used then the session.log and revert file (if the
   RESIZE action is used) will be written to the directory/folder specified.
   If this argument is not specified then these files will be written to the
   current working directory. For more details see the section on Files
   Created and Used below.

-o | --oci-conf <oci-conf-file>

   An optional flag and argument that can be used with all actions. If this
   flag and argument is used the the OCI configuration file will be read from
   the location specified. If this flag and argument is not used then the 02

-A | --address <ip-address>

  An optional flag and argument for the LOCAL_COPY and REMOTE_COPY actions.
  If this argument is not specified for these actions then OCI will
  automatically provide a new IP address. This flag and argument has no
  effect when used with other actions.

-C | --compartment <compartment-ocid>

  A mandatory flag and argument for the REMOTE_COPY action. This flag and
  argument has no effect when used with other actions. The argument provided
  must be an OCID for a compartment other than the one used by the database
  being copied.

-D | --database <database-ocid>

  A mandatory flag and argument for the RESIZE, LOCAL_COPY and REMOTE_COPY
  actions. This flag and argument has no effect when used with other actions.
  The argument provides the source database to be either resized or copied.

-N | --display-name <name>

  An optional flag and argument for the LOCAL_COPY and REMOTE_COPY actions.
  This flag and argument has no effect when used with other actions. If the
  flag and argument is not supplied then the copied database's display name
  shall take the form copy-<original-display-name>.

-R | --revert <revert-file>

  A mandatory flag and argument for the REVERT action. This argument has no
  effect when used with other actions. The argument provides the path and name
  of the revert-file. This file provides all the details necessary to rollback
  a resized database to its former size. For more options and details please
  see both the -B flag above and the section on Files Created and Used below.

-S | --subnet <subnet-ocid>

  A mandatory flag and argument for the REMOTE_COPY action. This argument has
  no effect when used with other actions. The argument provided must be an
  OCID for a subnet other than the one used by the database being copied.

Files Created and Used
======================

If help is requested then no files will be read or written to.

If an action is requested then an output directory will either be reused or
created. Please refer to the -d flag documentation above for details.

If an action is requested then either the existing session.log in the
specified output directory will be used, or if a session.log does not exist
then one will be created and used. Note that reuse of a session.log is not
destructive because all entries are appended.

If a RESIZE action is requested then a revert file whose name shall take the
form revert.<timestamp> will be written to the output directory. The contents
of this file may be used to revert a resized database to its original size.

If a REVERT action is requested then the user must specify an input
revert-file (see the -I flag for details). Note that when a REVERT action is
requested it will also create a REVERT file. No revert-file is created when
using either the local or remote copy actions.
