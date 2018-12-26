import os
import socket
import time
from enum import Enum
from ftplib import FTP, error_perm
from telnetlib import Telnet

from app.commons import log
from app.properties import Profile

__DATA_FILES_LIST = ("tv", "radio", "lamedb", "lamedb5", "blacklist", "whitelist",  # enigma 2
                     "services.xml", "myservices.xml", "bouquets.xml", "ubouquets.xml")  # neutrino

_SATELLITES_XML_FILE = "satellites.xml"
_WEBTV_XML_FILE = "webtv.xml"


class DownloadDataType(Enum):
    ALL = 0
    BOUQUETS = 1
    SATELLITES = 2
    PICONS = 3
    WEBTV = 4


def download_data(*, properties, download_type=DownloadDataType.ALL, callback=None):
    with FTP(host=properties["host"]) as ftp:
        ftp.login(user=properties["user"], passwd=properties["password"])
        ftp.encoding = "utf-8"
        save_path = properties["data_dir_path"]
        os.makedirs(os.path.dirname(save_path), exist_ok=True)
        files = []
        # bouquets section
        if download_type is DownloadDataType.ALL or download_type is DownloadDataType.BOUQUETS:
            ftp.cwd(properties["services_path"])
            ftp.dir(files.append)

            for file in files:
                name = str(file).strip()
                if name.endswith(__DATA_FILES_LIST):
                    name = name.split()[-1]
                    download_file(ftp, name, save_path)
        # satellites.xml and webtv section
        if download_type in (DownloadDataType.ALL, DownloadDataType.SATELLITES, DownloadDataType.WEBTV):
            ftp.cwd(properties["satellites_xml_path"])
            files.clear()
            ftp.dir(files.append)

            for file in files:
                name = str(file).strip()
                if download_type in (DownloadDataType.ALL, DownloadDataType.SATELLITES):
                    if name.endswith(_SATELLITES_XML_FILE):
                        download_file(ftp, _SATELLITES_XML_FILE, save_path)
                elif download_type in (DownloadDataType.ALL, DownloadDataType.WEBTV):
                    if name.endswith(_WEBTV_XML_FILE):
                        download_file(ftp, _WEBTV_XML_FILE, save_path)

        if callback is not None:
            callback()


def upload_data(*, properties, download_type=DownloadDataType.ALL, remove_unused=False, profile=Profile.ENIGMA_2,
                callback=None):
    data_path = properties["data_dir_path"]
    host = properties["host"]
    # telnet
    tn = telnet(host=host, user=properties.get("telnet_user", "root"), password=properties.get("telnet_password", ""),
                timeout=properties.get("telnet_timeout", 5))
    next(tn)
    # terminate enigma or neutrino
    tn.send("init 4")

    with FTP(host=host) as ftp:
        ftp.login(user=properties["user"], passwd=properties["password"])
        ftp.encoding = "utf-8"

        if download_type is DownloadDataType.ALL or download_type is DownloadDataType.SATELLITES:
            ftp.cwd(properties["satellites_xml_path"])
            send = send_file(_SATELLITES_XML_FILE, data_path, ftp)
            if download_type is DownloadDataType.SATELLITES:
                tn.send("init 3" if profile is Profile.ENIGMA_2 else "init 6")
                if callback is not None:
                    callback()
                return send

        if profile is Profile.NEUTRINO_MP and download_type in (DownloadDataType.ALL, DownloadDataType.WEBTV):
            ftp.cwd(properties["satellites_xml_path"])
            send = send_file(_WEBTV_XML_FILE, data_path, ftp)
            if download_type is DownloadDataType.WEBTV:
                tn.send("init 6")
                if callback is not None:
                    callback()
                return send

        if download_type is DownloadDataType.ALL or download_type is DownloadDataType.BOUQUETS:
            ftp.cwd(properties["services_path"])
            if remove_unused:
                files = []
                ftp.dir(files.append)
                for file in files:
                    name = str(file).strip()
                    if name.endswith(__DATA_FILES_LIST):
                        name = name.split()[-1]
                        ftp.delete(name)

            for file_name in os.listdir(data_path):
                if file_name == _SATELLITES_XML_FILE or file_name == _WEBTV_XML_FILE:
                    continue
                if file_name.endswith(__DATA_FILES_LIST):
                    send_file(file_name, data_path, ftp)

        if download_type is DownloadDataType.PICONS:
            picons_dir_path = properties.get("picons_dir_path")
            picons_path = properties.get("picons_path")
            try:
                ftp.cwd(picons_path)
            except error_perm as e:
                if str(e).startswith("550"):
                    ftp.mkd(picons_path)  # if not exist
                    ftp.cwd(picons_path)

            files = []
            ftp.dir(files.append)
            picons_suf = (".jpg", ".png")

            for file in files:
                name = str(file).strip()
                if name.endswith(picons_suf):
                    name = name.split()[-1]
                    ftp.delete(name)
            for file_name in os.listdir(picons_dir_path):
                if file_name.endswith(picons_suf):
                    send_file(file_name, picons_dir_path, ftp)

        # resume enigma or restart neutrino
        tn.send("init 3" if profile is Profile.ENIGMA_2 else "init 6")

        if callback is not None:
            callback()


def download_file(ftp, name, save_path):
    with open(save_path + name, "wb") as f:
        ftp.retrbinary("RETR " + name, f.write)
        

def send_file(file_name, path, ftp):
    """ Opens the file in binary mode and transfers into receiver """
    with open(path + file_name, "rb") as f:
        return ftp.storbinary("STOR " + file_name, f)


def telnet(host, port=23, user="", password="", timeout=5):
    try:
        tn = Telnet(host=host, port=port, timeout=timeout)
    except socket.timeout:
        log("telnet error: socket timeout")
    else:
        time.sleep(1)
        command = yield
        if user != "":
            tn.read_until(b"login: ")
            tn.write(user.encode("utf-8") + b"\n")
            time.sleep(timeout)
        if password != "":
            tn.read_until(b"Password: ")
            tn.write(password.encode("utf-8") + b"\n")
            time.sleep(timeout)
        tn.write("{}\r\n".format(command).encode("utf-8"))
        time.sleep(timeout)
        command = yield
        time.sleep(timeout)
        tn.write("{}\r\n".format(command).encode("utf-8"))
        time.sleep(timeout)
        tn.close()
        yield


if __name__ == "__main__":
    pass
