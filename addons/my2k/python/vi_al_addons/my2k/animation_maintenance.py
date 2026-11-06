# SPDX-License-Identifier: GPL-2.0-or-later
"""Explicit user-triggered maintenance only; never called by ordinary library work."""
from pathlib import Path
import time
from vi_al_addons.my2k.animation_library_protocol import available_mounts
from vi_al_addons.my2k.animation_files_protocol import AnimationFilesClient

def asset_partitions(sysfs=Path('/sys/class/block')):
    found=[]
    for entry in sysfs.iterdir():
        if not(entry/'partition').exists()or int((entry/'size').read_text())<=0:continue
        node=entry.resolve()
        for parent in (node,*node.parents):
            if(parent/'idVendor').exists()and(parent/'idProduct').exists():
                if(parent/'idVendor').read_text().strip().lower()=='4d58'and(parent/'idProduct').read_text().strip().lower()=='f1fc':
                    found.append(Path('/dev')/entry.name)
                break
    return found

def filesystem_ready(partition):
    """A kernel partition may precede UDisks' Filesystem interface by seconds."""
    from .system_storage import filesystem_ready as ready
    return ready(partition)

def mount_partition(partition):
    from .system_storage import mount_partition as mount
    return mount(partition)

def mount_maintenance(keyboard,cancelled=lambda:False,clock=time.monotonic,sleep=time.sleep):
    mounts=available_mounts()
    if len(mounts)>1:raise RuntimeError('Multiple MY-2K drives are mounted; choose one keyboard before maintenance.')
    if mounts:return str(mounts[0])
    # Idempotent enter, never toggle an existing maintenance session back out.
    AnimationFilesClient(keyboard).maintenance()
    deadline=clock()+45
    while clock()<deadline:
        if cancelled():raise RuntimeError('Mount wait cancelled. Use the storage-toggle key to return after safely ejecting any drive.')
        found=asset_partitions()
        if len(found)>1:raise RuntimeError('Multiple MY-2K partitions detected; no volume was mounted.')
        if found and filesystem_ready(found[0]):
            mount_partition(found[0])
            mounts=available_mounts()
            if len(mounts)==1:return str(mounts[0])
            raise RuntimeError('UDisks returned without one verified MY-2K mount.')
        sleep(.25)
    raise RuntimeError('No nonzero MY-2K partition appeared. No format, repair or rescan was attempted.')
