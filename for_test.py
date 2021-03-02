#!/usr/bin/env python
# -*- encoding: utf-8 -*-
"""
@Author  :   王超逸
@File    :   for_test.py
@Time    :   2021/2/23 12:57
@Desc    :
"""
from typing import Coroutine

from graphgl_api import DemoViewSet
from model import *


async def main():
    await init()
    events = [event async for event in Event.all()]
    print(await events[0].tournament)
    events2 = [event async for event in Event.all().select_related("tournament")]
    print(events2[0].tournament)
    print(await DemoViewSet.resolve_Event_count(None, None, **{'page': 0, 'page_size': 30}))


def run_async(coro: Coroutine) -> None:
    loop = asyncio.get_event_loop()
    loop.run_until_complete(coro)



run_async(main())
