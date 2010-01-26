import os
import sys
import shutil


def create_dir(dir_name):
    delete_dir(dir_name)
    os.system("mkdir "+dir_name)


def delete_dir(dir_name):

    if os.path.exists(dir_name):
        reply = raw_input("Delete directory "+dir_name+"? [y/[n]] ")
        if reply=='y':
            shutil.rmtree(dir_name)
        else:
            print "Aborting..."
            sys.exit()
        print ""


def delete_file(file_name):

    if os.path.exists(file_name):
        reply = raw_input("Delete file "+file_name+"? [y/[n]] ")
        if reply=='y':
            os.remove(file_name)
        else:
            print "Aborting..."
            sys.exit()
        print ""
