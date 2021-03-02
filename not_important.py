#!/usr/bin/env python
# -*- encoding: utf-8 -*-
"""
@Author  :   王超逸
@File    :   not_important.py
@Time    :   2021/2/22 10:35
@Desc    :
"""
import asyncio

from graphene import ObjectType, String, Schema, Field

from graphene_backend import MyGraphQLBackend


class Human:
    first_name = "Luke"
    last_name = "Skywalker"


def get_human(*_, **__):
    return Human()


class Person(ObjectType):
    full_name = String()

    @classmethod
    def prefetch_fn(cls, **kwargs):
        print(kwargs)
        return "Human"

    @staticmethod
    async def resolve_full_name(parent, info):
        print("内层开始")
        await asyncio.sleep(5)
        print("内层结束")
        return f"{parent.first_name} {parent.last_name}"


class Query(ObjectType):
    me = Field(Person)
    hello = String(name=String(default_value="Luke"))

    @classmethod
    def prefetch_fn(cls, **kwargs):
        print(kwargs)

    @staticmethod
    async def resolve_me(parent, info):
        # returns an object that represents a Person
        print("外层开始")
        await asyncio.sleep(2)
        print("外层结束")
        return get_human(name="Luke Skywalker")

    @staticmethod
    async def resolve_hello(parent, info, name):
        print("标量开始")
        await asyncio.sleep(5)
        print("标量结束")
        return f"hello {name}"


schema = Schema(query=Query)

query_string = '{ hello(name: "王超逸") me { fullName } }'
result = schema.execute(query_string, backend=MyGraphQLBackend())
print(result)
...
