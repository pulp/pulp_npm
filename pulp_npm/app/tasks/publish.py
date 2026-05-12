from asgiref.sync import sync_to_async

from pulpcore.plugin.tasking import add_and_remove


async def aadd_and_remove(*args, **kwargs):
    return await sync_to_async(add_and_remove)(*args, **kwargs)
