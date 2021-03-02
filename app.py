#!/usr/bin/env python
# -*- encoding: utf-8 -*-
"""
@Author  :   王超逸
@File    :   app.py
@Time    :   2021/2/7 10:07
@Desc    :
"""

from sanic import Sanic
from sanic.response import text, json
import time

from tortoise import Tortoise

from graphene_backend import MyGraphQLBackend
from graphgl_api import schema, DemoViewSet
import asyncio


async def init_orm(generate_schemas=False):
    # Here we create a SQLite DB using file "db.sqlite3"
    #  also specify the app name of "models"
    #  which contain models from "app.models"
    await Tortoise.init(
        db_url='sqlite://db.sqlite3',
        modules={'models': ["model"]}
    )
    # Generate the schema
    if generate_schemas:
        await Tortoise.generate_schemas()
        print("模式创建完成")
    print("orm初始化完成")


app = Sanic("hello_example")


@app.route("/")
async def ping(request):
    return json({"status": "Ok.",
                 "time": time.time()})


@app.route("/api/", methods=["GET", "POST"])
async def api(request):
    if request.method == "GET":
        query_str = request.args.get("query")
    else:
        assert request.method == "POST"
        query_str = request.json.get("query")
    result = await schema.execute(query_str, backend=MyGraphQLBackend())
    return json(result.to_dict())


async def main():
    await init_orm()
    server = await app.create_server(host="0.0.0.0", port=8000, return_asyncio_server=True)
    await server.wait_closed()


if __name__ == "__main__":
    asyncio.run(main())
