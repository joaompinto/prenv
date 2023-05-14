import os
import sys

from .colorhelper import info, print_error
from .images import download_image
from .rootfs import RootFS
from .socket import create_socket_bind, get_process_socket
from .tar import extract_tar
from .verbose import verbose


def manager_process(image_name: str, ram_disk_size: int) -> None:
    """The manager proccess performs the follwing maint tasks

    1. Creates a unix socket and waits to receive a connection and a "setup" message
    2. Once the message is received, it calls prepare_rootfs() function
    3. Once the rootfs is ready, it sends an "ok" message to the connection accepted on 1
    4. Keeps in a loop accepting connections and responding to "info" messages with the mount dir

    """
    sock = create_socket_bind()
    sock.listen(1)
    conn, _ = sock.accept()

    message = conn.recv(1024).decode("utf-8")
    if message != "setup":
        raise Exception(f"Unexpected message from parent process: {message}")
    verbose(f"Received message from parent process: {message}")

    rootfs = RootFS(ram_disk_size)
    root_mnt = rootfs.get_root()

    if ":" in image_name:
        image_fname = download_image(image_name)
    extract_tar(image_fname, root_mnt)

    conn.sendall(b"ok")
    conn.close()

    while True:
        conn, _ = sock.accept()
        message = conn.recv(1024).decode("utf-8")
        if message == "terminate":
            conn.close()
            break
        if message == "info":
            conn.sendall(root_mnt.as_posix().encode("utf-8"))
        else:
            print("Received unexpeted message from parent process: ", message)
        conn.close()


def setup_master_process(pid: int, verbose=False) -> None:
    # Connect to the child process's Unix socket
    conn = get_process_socket(pid)
    conn.sendall(b"setup")

    # Wait for the setup result
    message = conn.recv(1024).decode("utf-8")
    if message == "ok":
        if verbose:
            if sys.stdout.isatty():
                print("Instance setup successfully with PID:", info(pid))
            else:
                print(pid)
    else:
        print_error(f"Failed to setup the instance: {message}")
        exit(2)


def create_manager_process(tar_fname: str, ram_disk_size: int) -> int:
    """Create a master process that will create a new process namespace and
    mount a new root filesystem."""
    pid = os.fork()

    if pid == 0:
        manager_process(tar_fname, ram_disk_size)
    else:
        setup_master_process(pid)
        return pid
