#!/bin/python

import datetime
import getopt
import json
import oci
import os
import sys
import time
from utils.mdsconfigbuilder import ConfigBuilder
from utils.mdsconfigbuilder import ConfigIterator
from utils.mdsargs import Mdsargs
from utils.mdsargs import MdsargsError
from utils.mdscreds import MdsCredentials
from utils.mdscreds import MdsCredentialsError
from utils.mdsdatabase import MdsDatabase
from utils.mdsdatabase import MdsMetaDatabase
from utils.spinner import Spinner
from utils.tio import Tio

# Constants
DESTRUCTIVE = True
NON_DESTRUCTIVE = False
MAX_DESC_LEN = 399
# Effective constants (variables set once outside of main())
TIMESTAMP = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
OUTPUT_REVERT_FILE = "revert." + TIMESTAMP
SESSION_LOG = "session.log"
# Global: object to handle both the printing to screen and session logging
tio = None    

def get_source_shape(src_shape_name, shape_list):
    for shape in shape_list:
        if src_shape_name == shape.name:
            break
    return shape


def get_shape_menu(src_shape_name, shape_list):
    menu = list()
    for shape in shape_list:
        if src_shape_name != shape.name:
            menu.append(shape)
    return menu


def get_target_shape(src_shape_name, shape_list):
    src_shape = get_source_shape(src_shape_name,shape_list)
    menu_list = get_shape_menu(src_shape_name,shape_list)
    selected = -1
      
    tio.writeln("Resize Shape Menu")
    tio.writeln("Current shape: %s [%d ocpu, %dGB]" % (src_shape.name,src_shape.cpu_core_count,src_shape.memory_size_in_gbs))
    idx=0
    for shape in menu_list:
        tio.writeln("%2d %-32s %3d ocpu %4dGB" % (idx,shape.name,shape.cpu_core_count,shape.memory_size_in_gbs))
        idx += 1
    tio.writeln("%2d To quit application" % (idx))

    while selected < 0 or selected > len(menu_list):
        try:
            selected = int(tio.input("\nEnter option number: "))
        except:
            selected = -1

    if selected == idx:
        tio.writeln("\nApplication ended normally at user request.")
        sys.exit(0)

    return menu_list[selected]


def check_config_input(default_value, test_val):
    val = None
    try:
        if isinstance(default_value,str):
            val = new_val
        elif isinstance(default_value,int):
            val = int(test_val)
        elif isinstance(default_value,float):
            val = float(test_val)
        elif isinstance(default_value,bool):
            if test_val == "True":
                val = True
            elif test_val == "False":
                val = False
            else:
                val = None
        else:
            val = None
    except:
        val = None
    return val


def select_cfg_item(choices):
    cfg_item = None
    validated_input = False
    tio.writeln("\nOption:            %s" % choices[ConfigBuilder.OPTION])
    tio.writeln("Existing value:    %s" % choices[ConfigBuilder.SOURCE])
    tio.writeln("Default new value: %s" % choices[ConfigBuilder.TARGET])

    while cfg_item is None:
        suggested_value = choices[ConfigBuilder.SUGGESTED]
        tmp_val = tio.input("Enter required value [%s]: " % (suggested_value)) or suggested_value
        cfg_item = check_config_input(suggested_value,tmp_val)
        if cfg_item is None: 
            tio.writeln("The input value must be of the same type as the suggested value.")

    return cfg_item


def cfg_id_for_name(cfg_list, shape_name):
    for cfg in cfg_list:
        if cfg.shape_name == shape_name:
            return cfg.id
    return None


def get_target_config_id(svc_client, shape_name, src):
    cfg_list_response = svc_client.list_configurations(
            src.database.compartment_id,
            lifecycle_state = oci.mysql.models.Configuration.LIFECYCLE_STATE_ACTIVE)
    tgt_cfg_response = svc_client.get_configuration(cfg_id_for_name(cfg_list_response.data,shape_name))

    cfg_builder = None
    while True:
        tio.writeln("\nAccept or change database configuration options.\n")
        tio.writeln("In order to achieve optimal performance it is suggested that you accept the")
        tio.writeln("default values. Only enter a different value for an option if you have a")
        tio.writeln("valid reason, otherwise press enter to accept the suggested default value.")

        cfg_builder = ConfigBuilder(src.config,tgt_cfg_response.data)
        it = cfg_builder.iterator()
        while True:
            choices = it.next()
            if choices is None:
                break
            cfg_builder.set_config_item(choices[ConfigBuilder.OPTION],select_cfg_item(choices))

        confirmation = None
        while confirmation not in ("Yes","yes","Y","y","No","no","N","n","Quit","quit","Q","q"):
            confirmation = tio.input("\nConfirm the configuration options [yes|no|quit]: ")

        if confirmation in ("Yes","yes","Y","y"):
            break
        elif confirmation in ("Quit","quit","Q","q"):
            tio.writeln("\nApplication ended normally at user request.")
            sys.exit(0)
        else:
            continue

    if cfg_builder.requires_new_config():
        name = shape_name + ".Custom." + TIMESTAMP
        tio.writeln("\nConfiguration changes require a custom configuration.")
        tio.write("Creating configuration, %s..." % name)
        cfg_details = oci.mysql.models.CreateConfigurationDetails(
            compartment_id = src.database.compartment_id,
            defined_tags = src.config.defined_tags,
            description = "Created as part of the resizing of database, " + src.database.display_name,
            freeform_tags = src.config.freeform_tags,
            display_name = (shape_name + ".Custom." + TIMESTAMP),
            # parent_configuration_id = src_cfg.data.id,
            shape_name = shape_name,
            variables = cfg_builder.get_config()
        )
        tgt_cfg_response = svc_client.create_configuration(cfg_details)
        if tgt_cfg_response.data.lifecycle_state != oci.mysql.models.Configuration.LIFECYCLE_STATE_ACTIVE:
            raise(cfg.lifecycle_state)
        tio.writeln("Done.")

    return tgt_cfg_response.data.id


def backup_db(oci_cfg, dbid):
    client = oci.mysql.DbBackupsClient(oci_cfg)

    backup_details = oci.mysql.models.CreateBackupDetails(
        backup_type = oci.mysql.models.CreateBackupDetails.BACKUP_TYPE_FULL,
        db_system_id = dbid,
        display_name = ("custom-" + TIMESTAMP),
        retention_in_days = 6
    )

    tio.write("Backing up the existing database service...")
    spinner = Spinner()
    spinner.start()
    backup_response = client.create_backup(backup_details)
    while backup_response.data.lifecycle_state == oci.mysql.models.Backup.LIFECYCLE_STATE_CREATING:
        time.sleep(20)
        backup_response = client.get_backup(backup_response.data.id)
    spinner.stop()

    if backup_response.data.lifecycle_state != oci.mysql.models.Backup.LIFECYCLE_STATE_ACTIVE:
        raise(backup_response.data.lifecycle_details)
    else:
        tio.writeln("Done.")

    return backup_response.data


def shutdown_db(oci_cfg, dbid):
    client = oci.mysql.DbSystemClient(oci_cfg)

    shutdown_details = oci.mysql.models.StopDbSystemDetails(
        shutdown_type = oci.mysql.models.StopDbSystemDetails.SHUTDOWN_TYPE_FAST
    )

    tio.write("Shutting down the existing database service...")
    spinner = Spinner()
    spinner.start()
    client.stop_db_system(dbid,shutdown_details)
    db_response = client.get_db_system(dbid)
    while db_response.data.lifecycle_state == oci.mysql.models.DbSystem.LIFECYCLE_STATE_UPDATING:
        time.sleep(20)
        db_response = client.get_db_system(dbid)
    spinner.stop()

    if db_response.data.lifecycle_state != oci.mysql.models.DbSystem.LIFECYCLE_STATE_INACTIVE:
        raise(db_response.data.lifecycle_details)
    else:
        tio.writeln("Done.")
    return

 
def delete_db(oci_cfg, dbid):
    client = oci.mysql.DbSystemClient(oci_cfg)

    tio.write("Deleting the existing database service...")
    spinner = Spinner()
    spinner.start()
    client.delete_db_system(dbid)
    db_response = client.get_db_system(dbid)
    while db_response.data.lifecycle_state == oci.mysql.models.DbSystem.LIFECYCLE_STATE_DELETING:
        time.sleep(20)
        db_response = client.get_db_system(dbid)
    spinner.stop()
    
    if db_response.data.lifecycle_state != oci.mysql.models.DbSystem.LIFECYCLE_STATE_DELETED:
        raise(db_response.data.lifecycle_details)
    else:
        tio.writeln("Done.")
    return


def get_db_creds():

    creds = MdsCredentials()
    while True:
        try: 
            creds.set_username(tio.input("Enter username: "))
            break
        except MdsCredentialsError as e:
            tio.writeln(e.__str__())
            continue

    while True:
        try:
            p1 = tio.password_input("Enter password: ")
            p2 = tio.password_input("Confirm password: ")
            creds.set_password(p1,p2)
            break
        except MdsCredentialsError as e:
            tio.writeln(e.__str__())
            continue

    return creds


def create_db(oci_cfg, db_details):
    client = oci.mysql.DbSystemClient(oci_cfg)

    tio.write("Creating a new database service...")
    spinner = Spinner()
    spinner.start()
    db_response = client.create_db_system(db_details)
    while db_response.data.lifecycle_state == oci.mysql.models.DbSystem.LIFECYCLE_STATE_CREATING:
        time.sleep(20)
        db_response = client.get_db_system(db_response.data.id)
    spinner.stop()

    if db_response.data.lifecycle_state != oci.mysql.models.DbSystem.LIFECYCLE_STATE_ACTIVE:
        raise(db_response.data.lifecycle_details)
    else:
        tio.writeln("Done.")

    return db_response.data


def get_target_db(oci_cfg, src):
    client = oci.mysql.MysqlaasClient(oci_cfg)
    available_shapes_response = client.list_shapes(src.database.compartment_id)
    shape = get_target_shape(src.database.shape_name,available_shapes_response.data)
    cfg_id = get_target_config_id(client,shape.name,src)
    return MdsMetaDatabase(shape.name,cfg_id)
    

def get_source_db(oci_cfg, db_ocid):
    db_client = oci.mysql.DbSystemClient(oci_cfg)
    svc_client = oci.mysql.MysqlaasClient(oci_cfg)
    db_response = db_client.get_db_system(db_ocid)
    cfg_response = svc_client.get_configuration(db_response.data.configuration_id)
    return MdsDatabase(db_response.data,cfg_response.data)


def create_revert_file(src, backup, revert_filename):
    f = open(revert_filename,"w")
    f.write("{\n")
    f.write("\"backup\": {\n")
    f.write("  \"display_name\": \"" + backup.display_name + "\",\n")
    f.write("  \"id\": \"" + backup.id + "\"\n")
    f.write("},\n")
    f.write("\"database\": " + src.database.__str__())
    f.write(",\n")
    # JSON is purposely not concluded here with a final close bracket, '}'
    # because we will later need to append a metadata object to it.
    # See update_revert_file()
    f.flush()
    f.close()
    return

def update_revert_file(src, db, revert_filename):
    f = open(revert_filename,"a")
    f.write("\"metadata\": {\n")
    f.write("  \"created\": \"" + TIMESTAMP + "\",\n")
    f.write("  \"display_name\": \"" + src.database.display_name + "\",\n")
    f.write("  \"from\": {\n")
    f.write("    \"shape_name\": \"" + src.database.shape_name + "\"\n")
    f.write("  },\n")
    f.write("  \"to\": {\n")
    f.write("    \"id\": \"" + db.id + "\",\n")
    f.write("    \"shape_name\": \"" + db.shape_name + "\"\n")
    f.write("  }\n")
    f.write("}\n")
    f.write("}")
    f.flush()
    f.close()
    return


def start_db(oci_cfg, db_ocid):
    client = oci.mysql.DbSystemClient(oci_cfg)
    client.start_db_system(db_ocid)
    return


def accept_changes(destructive):
    tio.writeln("The following operations will occur:")
    if destructive:
        tio.writeln("  1. The existing database service will be shutdown.")
        tio.writeln("  2. The existing database service will then be backed up.")
        tio.writeln("  3. The existing database service will then be DELETED.")
        tio.writeln("  4. A new database service will be created and the backup will be restored to it.")
    else:
        tio.writeln("  1. The existing database service will be shutdown.")
        tio.writeln("  2. The existing database service will then be backed up")
        tio.writeln("  3. A new database service will be created and the backup will be restored to it.")
        tio.writeln("  4. The original (existing) database service will be restarted.")

    tio.writeln("\nEach of the above operations may take a number of minutes to complete.\n")
    confirmation = None
    while confirmation not in ("Yes","yes","Y","y","No","no","N","n"):
        confirmation = tio.input("Do you want to proceed [yes|no]: ")
    if confirmation in ("Yes","yes","Y","y"):
        return True
    return False


def resize_copy():
    tio.writeln("\n")
    confirmation = None
    while confirmation not in ("Yes","yes","Y","y","No","no","N","n"):
        confirmation = tio.input("Do you want to resize the copy database [yes|no]: ")
    if confirmation in ("Yes","yes","Y","y"):
        return True
    return False


def rcopy(oci_cfg, args):
    copy_db = None
    tio.writeln("\nINFORMATION GATHERING PHASE\n")

    tio.write("Getting existing database's details...")
    src = get_source_db(oci_cfg,args.db_ocid)
    tio.writeln("Done.")

    # Get values for attributes that have been specified on the command line
    # otherwise assign their value from the source database
    name = None
    if args.display_name is not None:
        name = args.display_name
    else:
        name = "copy-" + src.database.display_name

    # Get values for attributes which may vary according to whether the 
    # copied database is to be resized.
    desc = None
    shape = None
    config_id = None
    if resize_copy():
        tio.writeln("\nGet resize information.\n")
        tgt = get_target_db(oci_cfg,src)
        shape = tgt.shape_name
        config_id = tgt.config_id
        desc = "Resized copy " + TIMESTAMP
    else:
        shape = src.database.shape_name
        config_id = src.database.configuration_id
        desc = "Copy " + TIMESTAMP
    if src.database.description is not None:
        desc = desc + ". " + src.database.description
    if len(desc) > MAX_DESC_LEN:
        desc = desc[0:MAX_DESC_LEN]

    tio.writeln("\nProvide credentials for the database administrator.")
    credentials = get_db_creds()

    tio.writeln("\nEXECUTION PHASE\n")
    if accept_changes(NON_DESTRUCTIVE):
        tio.write("\n")
        shutdown_db(oci_cfg,src.database.id)
        backup = backup_db(oci_cfg,src.database.id)

        # Posit that the remote copy is to another subnet in the same
        # compartment, then test and alter accordingly
        comp_id = src.database.compartment_id
        if args.comp_ocid is not None:
            # Remote copy is to another compartment, so move the backup to it
            comp_id = args.comp_ocid
            client = oci.mysql.DbBackupsClient(oci_cfg)
            client.change_backup_compartment(
                backup.id,
                oci.mysql.models.ChangeBackupCompartmentDetails(
                    compartment_id = args.comp_ocid
                )
            )

        # Now create the details for the (new) resized database 
        copy_db_details = oci.mysql.models.CreateDbSystemDetails(
            admin_password = credentials.get_password(),
            admin_username = credentials.get_username(),
            compartment_id = comp_id,
            shape_name = shape,
            source = oci.mysql.models.CreateDbSystemSourceFromBackupDetails(
                source_type = oci.mysql.models.CreateDbSystemSourceDetails.SOURCE_TYPE_BACKUP,
                backup_id = backup.id
            ),
            subnet_id = args.subnet_ocid,
            availability_domain = src.database.availability_domain,
            backup_policy = oci.mysql.models.CreateBackupPolicyDetails(
                is_enabled = src.database.backup_policy.is_enabled,
                window_start_time = src.database.backup_policy.window_start_time,
                retention_in_days = src.database.backup_policy.retention_in_days,
                defined_tags = src.database.backup_policy.defined_tags,
                freeform_tags = src.database.backup_policy.freeform_tags
            ), 
            configuration_id = config_id,
            data_storage_size_in_gbs = src.database.data_storage_size_in_gbs, 
            defined_tags = src.database.defined_tags,
            description = desc,
            display_name = name,
            freeform_tags = src.database.freeform_tags,
            hostname_label = src.database.hostname_label,
            is_highly_available = src.database.is_highly_available,
            maintenance = oci.mysql.models.CreateMaintenanceDetails(
                window_start_time = src.database.maintenance.window_start_time
            ),
            mysql_version = src.database.mysql_version,
            port = src.database.port,
            port_x = src.database.port_x
            # Unassigned attribute: fault_domain
        )
        # IP address has not been specified in the above construction of
        # the copy_db_details. If we leave it unspecified then OCI will give
        # the copied database an IP address, however if an IP address was
        # specified on the command line then we should use it.
        if args.address is not None:
            if args.address != src.database.ip_address:
                copy_db_details.ip_address = args.address
            else:
                raise MdsargsError("IP address, %s, cannot be the same as the source in a local copy." % args.address)

        copy_instance = create_db(oci_cfg,copy_db_details)
        tio.writeln("\nRestarting original (existing) database service instance in the background.")
        tio.writeln("This process will continue/complete after the application shuts down.")
        start_db(oci_cfg,src.database.id)
    else:
        tio.writeln("\nRemote copy has been aborted by user.")

    return copy_instance


def lcopy(oci_cfg, args):
    copy_instance = None
    tio.writeln("\nINFORMATION GATHERING PHASE\n")

    tio.write("Getting existing database's details...")
    src = get_source_db(oci_cfg,args.db_ocid)
    tio.writeln("Done.")

    # Get values for attributes that have been specified on the command line
    # otherwise assign their value from the source database
    name = None
    if args.display_name is not None:
        if args.display_name != src.database.display_name:
            name = args.display_name
        else:
            raise MdsargsError("Display name, %s, cannot be the same as the source in a local copy." % args.display_name)
    else:
        name = "copy-" + src.database.display_name

    # Get values for attributes which may vary according to whether the 
    # copied database is to be resized.
    desc = None
    shape = None
    config_id = None

    if resize_copy():
        tio.writeln("\nGet resize information.\n")
        tgt = get_target_db(oci_cfg,src)
        shape = tgt.shape_name
        config_id = tgt.config_id
        desc = "Resized copy " + TIMESTAMP
    else:
        tio.write("\n")
        shape = src.database.shape_name
        config_id = src.database.configuration_id
        desc = "Copy " + TIMESTAMP

    if src.database.description is not None:
        desc = desc + ". " + src.database.description
    if len(desc) > MAX_DESC_LEN:
        desc = desc[0:MAX_DESC_LEN]

    tio.writeln("\nProvide credentials for the database administrator.")
    credentials = get_db_creds()

    tio.writeln("\nEXECUTION PHASE\n")
    if accept_changes(NON_DESTRUCTIVE):
        tio.write("\n")
        shutdown_db(oci_cfg,src.database.id)
        backup = backup_db(oci_cfg,src.database.id)

        # Now create the details for the (new) resized database 
        copy_db_details = oci.mysql.models.CreateDbSystemDetails(
            admin_password = credentials.get_password(),
            admin_username = credentials.get_username(),
            compartment_id = src.database.compartment_id,
            shape_name = shape,
            source = oci.mysql.models.CreateDbSystemSourceFromBackupDetails(
                source_type = oci.mysql.models.CreateDbSystemSourceDetails.SOURCE_TYPE_BACKUP,
                backup_id = backup.id
            ),
            subnet_id = src.database.subnet_id,
            availability_domain = src.database.availability_domain,
            backup_policy = oci.mysql.models.CreateBackupPolicyDetails(
                is_enabled = src.database.backup_policy.is_enabled,
                window_start_time = src.database.backup_policy.window_start_time,
                retention_in_days = src.database.backup_policy.retention_in_days,
                defined_tags = src.database.backup_policy.defined_tags,
                freeform_tags = src.database.backup_policy.freeform_tags
            ), 
            configuration_id = config_id,
            data_storage_size_in_gbs = src.database.data_storage_size_in_gbs, 
            defined_tags = src.database.defined_tags,
            description = desc,
            display_name = name,
            freeform_tags = src.database.freeform_tags,
            hostname_label = src.database.hostname_label,
            is_highly_available = src.database.is_highly_available,
            maintenance = oci.mysql.models.CreateMaintenanceDetails(
                window_start_time = src.database.maintenance.window_start_time
            ),
            mysql_version = src.database.mysql_version,
            port = src.database.port,
            port_x = src.database.port_x
            # Unassigned attribute: fault_domain
        )
        # IP address has not been specified in the above construction of
        # the copy_db_details. If we leave it unspecified then OCI will give
        # the copied database an IP address, however if an IP address was
        # specified on the command line then we should use it.
        if args.address is not None:
            if args.address != src.database.ip_address:
                copy_db_details.ip_address = args.address
            else:
                raise MdsargsError("IP address, %s, cannot be the same as the source in a local copy." % args.address)

        copy_instance = create_db(oci_cfg,copy_db_details)
        tio.writeln("\nRestarting original (existing) database service instance in the background.")
        tio.writeln("This process will continue/complete after the application shuts down.")
        start_db(oci_cfg,src.database.id)
    else:
        tio.writeln("\nLocal copy has been aborted by user.")

    return copy_instance


def revert(oci_cfg, args):
    reverted_instance = None
    input_revert_file = args.revert_file
    output_revert_filename = os.path.join(args.output_dir,OUTPUT_REVERT_FILE)

    tio.writeln("INFORMATION GATHERING PHASE\n")
    
    rvt = json.load(open(input_revert_file,"r"))
    tio.writeln("Revert details read and parsed.")

    src_id = rvt["metadata"]["to"]["id"]
    tio.write("\nGetting existing database's details...")
    src = get_source_db(oci_cfg,src_id)
    tio.writeln("Done.")

    tio.writeln("\nProvide credentials for the database administrator.")
    credentials = get_db_creds()

    tio.writeln("\nEXECUTION PHASE\n")
    if accept_changes(DESTRUCTIVE):
        tio.write("\n")
        shutdown_db(oci_cfg,src_id)
        backup = backup_db(oci_cfg,src_id)
        create_revert_file(get_source_db(oci_cfg,src_id),backup,output_revert_filename)

        # Now create the details for the (new) resized database 
        desc = "Reverted " + TIMESTAMP
        if rvt["database"]["description"] is not None:
            desc = desc + ". " + rvt["database"]["description"] 

        if len(desc) > MAX_DESC_LEN:
            desc = desc[0:MAX_DESC_LEN]

        reverted_db_details = oci.mysql.models.CreateDbSystemDetails(
            admin_password = credentials.get_password(),
            admin_username = credentials.get_username(),
            compartment_id = rvt["database"]["compartment_id"],
            shape_name = rvt["database"]["shape_name"],
            source = oci.mysql.models.CreateDbSystemSourceFromBackupDetails(
                source_type = oci.mysql.models.CreateDbSystemSourceDetails.SOURCE_TYPE_BACKUP,
                backup_id = rvt["backup"]["id"]
            ),
            subnet_id = rvt["database"]["subnet_id"],
            availability_domain = rvt["database"]["availability_domain"],
            backup_policy = oci.mysql.models.CreateBackupPolicyDetails(
                is_enabled = rvt["database"]["backup_policy"]["is_enabled"],
                window_start_time = rvt["database"]["backup_policy"]["window_start_time"],
                retention_in_days = rvt["database"]["backup_policy"]["retention_in_days"],
                defined_tags = rvt["database"]["backup_policy"]["defined_tags"],
                freeform_tags = rvt["database"]["backup_policy"]["freeform_tags"]
            ), 
            configuration_id = rvt["database"]["configuration_id"],
            data_storage_size_in_gbs = rvt["database"]["data_storage_size_in_gbs"], 
            defined_tags = rvt["database"]["defined_tags"],
            description = desc,
            display_name = rvt["database"]["display_name"],
            freeform_tags = rvt["database"]["freeform_tags"],
            hostname_label = rvt["database"]["hostname_label"],
            ip_address = rvt["database"]["ip_address"],
            is_highly_available = rvt["database"]["is_highly_available"],
            maintenance = oci.mysql.models.CreateMaintenanceDetails(
                window_start_time = rvt["database"]["maintenance"]["window_start_time"]
            ),
            mysql_version = rvt["database"]["mysql_version"],
            port = rvt["database"]["port"],
            port_x = rvt["database"]["port_x"]
            # Unassigned attribute: fault_domain
        )
        delete_db(oci_cfg,src_id)
        reverted_instance = create_db(oci_cfg,reverted_db_details)
        update_revert_file(src,reverted_instance,output_revert_filename)
    else:
        tio.writeln("\nReverting has been abandoned by the user.")

    return reverted_instance


def resize(oci_cfg, args): 
    resized_instance = None
    revert_filename = os.path.join(args.output_dir,OUTPUT_REVERT_FILE)
    
    tio.writeln("\nINFORMATION GATHERING PHASE\n")

    tio.write("Getting existing database's details...")
    src = get_source_db(oci_cfg,args.db_ocid)
    tio.writeln("Done.")

    tio.writeln("\nGet resize information.\n")
    tgt = get_target_db(oci_cfg,src)
    
    tio.writeln("\nProvide credentials for the database administrator.")
    credentials = get_db_creds()

    tio.writeln("\nEXECUTION PHASE\n")
    if accept_changes(DESTRUCTIVE):
        tio.write("\n")
        shutdown_db(oci_cfg,src.database.id)
        backup = backup_db(oci_cfg,src.database.id)
        create_revert_file(src,backup,revert_filename)

        # Now create the details for the (new) resized database 
        desc = "Resized " + TIMESTAMP
        if src.database.description is not None:
            desc = desc + ". " + src.database.description

        if len(desc) > MAX_DESC_LEN:
            desc = desc[0:MAX_DESC_LEN]

        resized_db_details = oci.mysql.models.CreateDbSystemDetails(
            admin_password = credentials.get_password(),
            admin_username = credentials.get_username(),
            compartment_id = src.database.compartment_id,
            shape_name = tgt.shape_name,
            source = oci.mysql.models.CreateDbSystemSourceFromBackupDetails(
                source_type = oci.mysql.models.CreateDbSystemSourceDetails.SOURCE_TYPE_BACKUP,
                backup_id = backup.id
            ),
            subnet_id = src.database.subnet_id,
            availability_domain = src.database.availability_domain,
            backup_policy = oci.mysql.models.CreateBackupPolicyDetails(
                is_enabled = src.database.backup_policy.is_enabled,
                window_start_time = src.database.backup_policy.window_start_time,
                retention_in_days = src.database.backup_policy.retention_in_days,
                defined_tags = src.database.backup_policy.defined_tags,
                freeform_tags = src.database.backup_policy.freeform_tags
            ), 
            configuration_id = tgt.config_id,
            data_storage_size_in_gbs = src.database.data_storage_size_in_gbs, 
            defined_tags = src.database.defined_tags,
            description = desc,
            display_name = src.database.display_name,
            freeform_tags = src.database.freeform_tags,
            hostname_label = src.database.hostname_label,
            ip_address = src.database.ip_address,
            is_highly_available = src.database.is_highly_available,
            maintenance = oci.mysql.models.CreateMaintenanceDetails(
                window_start_time = src.database.maintenance.window_start_time
            ),
            mysql_version = src.database.mysql_version,
            port = src.database.port,
            port_x = src.database.port_x
            # Unassigned attribute: fault_domain
        )
        delete_db(oci_cfg,src.database.id)
        resized_instance = create_db(oci_cfg,resized_db_details)
        update_revert_file(src,resized_instance,revert_filename)
    else:
        tio.writeln("\nResizing has been aborted by the user.")

    return resized_instance


def summary(oci_cfg, db, args):
    tio.writeln("\nSUMMARY PHASE\n")
    if db is not None:
        id_client = oci.identity.IdentityClient(oci_cfg)
        nwk_client = oci.core.VirtualNetworkClient(oci_cfg)
        compartment = id_client.get_compartment(db.compartment_id)
        subnet = nwk_client.get_subnet(db.subnet_id)
        tio.writeln("Resultant database:")
        tio.writeln("  Display name:  %s" % (db.display_name))
        tio.writeln("  IP address:    %s" % (db.ip_address))
        tio.writeln("  Shape:         %s" % (db.shape_name))
        tio.writeln("  Compartment:   %s" % (compartment.data.name))
        tio.writeln("  Subnet:        %s" % (subnet.data.display_name))
        tio.writeln("  OCIDs:")
        tio.writeln("    Database:    %s" % (db.id))
        tio.writeln("    Compartment: %s" % (db.compartment_id))
        tio.writeln("    Subnet:      %s" % (db.subnet_id))
        tio.writeln("\nFiles written:")
        tio.writeln("  Session log: %s" % (os.path.join(args.output_dir,SESSION_LOG)))
        if args.action == Mdsargs.RESIZE or args.action == Mdsargs.REVERT:
            tio.writeln("  Revert file: %s" % (os.path.join(args.output_dir,OUTPUT_REVERT_FILE)))
    else:
        tio.writeln("Files written:")
        tio.writeln("  Session log: %s" % (os.path.join(args.output_dir,SESSION_LOG)))
    return
    

def usage():
    print("\nUsage: %s -h" % (sys.argv[0]))
    print("=====\n")
    print("%s -h\n" % (sys.argv[0]))
    print("%s -a RESIZE -D <database-ocid> [-d <directory-name> -o <oci-conf-file>]\n" % (sys.argv[0]))
    print("%s -a REVERT -R <revert-file> [-d <directory-name> -o <oci-conf-file>]\n" % (sys.argv[0]))
    print("%s -a LOCAL_COPY -D <database-ocid> [-A <ip-address> -N <name> -d <directory-name> -o <oci-conf-file>]\n" % (sys.argv[0]))
    print("%s -a REMOTE_COPY -D <database-ocid> -S <subnet-ocid> [-C <compartment-ocid> -A <ip-address> -N <name> -d <directory-name> -o <oci-conf-file>]\n" % (sys.argv[0]))
    print("""
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
    name and IP address, both of which will be automatically assigned unless
    their values are specified on the command line (see -A and -N flags in 
    Additional Action Flags below).

  REMOTE_COPY
    Copies and optionally resizes a database. The copy will be hosted in a
    different subnet to the original. This subnet can be in a different 
    compartment. The copy will have a new name and IP address, both of which
    will be automatically assigned unless their values are specified on the
    command line (see -A and -N flags in Additional Action Flags below).

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
    """)
    return


def process_cmd_line(cmdargs):
    arg_handler = Mdsargs()
    arguments, values = getopt.getopt(cmdargs,"ha:d:o:A:C:D:N:R:S:", ["help","action=","output-dir=","oci-conf=","address=","compartment=","database=","display-name","revert=","subnet="])
    for current_arg, current_val in arguments:
        if current_arg in ("-h","--help"):
            arg_handler.action = Mdsargs.HELP
            break
        elif current_arg in ("-a","--action"):
            arg_handler.action = current_val
        elif  current_arg in ("-d","--output-dir"):
            arg_handler.output_dir = current_val
        elif current_arg in ("-o","--oci-conf"):
            arg_handler.oci_cfg_file = current_val
        elif current_arg in ("-A","--address"):
            arg_handler.address = current_val
        elif current_arg in ("-C","--compartment"):
            arg_handler.comp_ocid = current_val
        elif current_arg in ("-D","--database"):
            arg_handler.db_ocid = current_val
        elif current_arg in ("-N","--display-name"):
            arg_handler.display_name = current_val
        elif current_arg in ("-R","--revert"):
            arg_handler.revert_file = current_val
        elif current_arg in ("-S","--subnet"):
            arg_handler.subnet_ocid = current_val
        else:
            arg_handler.action = None
            break
    return arg_handler


# main routine
def main(cmdargs):
    global tio

    try:
        args = process_cmd_line(cmdargs[1:])
        if args.action == Mdsargs.HELP:
            usage()
        elif args.action is not None:
            # If the output directory hasn't been set, use the current working 
            # directory, then open the session log in append mode
            if args.output_dir is None:
                args.output_dir = os.getcwd()

            tio = Tio(open(os.path.join(args.output_dir,"session.log"),"a"))

            # Use Tee so that anything printed to screen (using the stdout file
            # descriptor) will also be written to the session log. When there is
            # no requirement for an echo to screen use the session_log file handle
            # and its write method as detailed below:

            tio.set_mode(Tio.SCREEN,Tio.OFF)
            tio.writeln("##########################################i####################################")
            tio.writeln("#")
            tio.writeln("# New session commenced %s" % (TIMESTAMP)) 
            tio.writeln("#")
            tio.writeln("###############################################################################\n")
            tio.writeln("Command line:")
            for item in cmdargs:
                tio.write(item + " ")
            tio.write("\n")
            tio.set_mode(Tio.SCREEN,Tio.ON)

            # Load the OCI Config file
            oci_cfg = None
            if args.oci_cfg_file is None:
                oci_cfg = oci.config.from_file()
            else:
                oci_cfg = oci.config.from_file(filename)

            # Now execute the action
            try:
                db = None
                if args.action == Mdsargs.RESIZE:
                    db = resize(oci_cfg,args)
                elif args.action == Mdsargs.REVERT:
                    db = revert(oci_cfg,args)
                elif args.action == Mdsargs.LOCAL_COPY:
                    db = lcopy(oci_cfg,args)
                elif args.action == Mdsargs.REMOTE_COPY:
                    db = rcopy(oci_cfg,args)
                summary(oci_cfg,db,args)
                tio.writeln("\nExiting normally.")
            except Exception as e:
                # Exception raised during the processing of an action
                tio.writeln("\nERROR: %s\n" % e.__str__())
                sys.exit(1)
        else:
            usage()
            print("Additional information: either help or an action must be specified.")
            sys.exit(1)
    except Exception as e:
        # Exception raisd during initialization
        usage()
        print("Additional information:")
        print(e)
        sys.exit(1)


if __name__ == "__main__":
    main(sys.argv)
