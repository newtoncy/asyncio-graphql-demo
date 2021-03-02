#!/usr/bin/env python
# -*- encoding: utf-8 -*-
"""
@Author  :   王超逸
@File    :   graphene_backend.py
@Time    :   2021/2/22 12:50
@Desc    :   修补graphene，使得n+1问题能够被解决
"""
import asyncio
import traceback
from collections import defaultdict

from graphql import MiddlewareManager, GraphQLList
from graphql.backend.core import GraphQLCoreBackend, validate, ExecutionResult
from functools import partial

from graphql.execution.executor import execute_operation
from graphql.execution.executors.asyncio import AsyncioExecutor
from graphql.execution.utils import ExecutionContext, get_operation_root_type, collect_fields, get_field_def
from graphql.pyutils.default_ordered_dict import DefaultOrderedDict
from promise import Promise
from rx import Observable
from six import string_types

from graphql.language.base import parse, print_ast
from graphql.language import ast
from graphql.backend.base import GraphQLDocument
import warnings

# Necessary for static type checking
from typing import Any, Optional, Union, Awaitable
from graphql.language.ast import Document, OperationDefinition, SelectionSet
from graphql.type.schema import GraphQLSchema

# 我们本质上是要拼凑出合适的路径给orm，让它prefetch
# 返回这个常量表示这玩意不出现在路径中
__skip = type("SKIP", (object,), {"__str__": lambda self: "SKIP"})
SKIP = __skip()


# 解决N+1问题
def resolve_prefetch(
        exe_context,  # type: ExecutionContext
        operation,  # type: OperationDefinition
        root_type=None,  # type: Any
        type_=None,
        path=None,
        selection_set=None,  # type: Optional[SelectionSet]
        action_id=None
):
    if path is None:
        path = []
    if type_ is None:
        type_ = get_operation_root_type(exe_context.schema, operation)
    if isinstance(type_, GraphQLList):
        type_ = type_.of_type
    if root_type is None:
        root_type = type_.graphene_type
    if selection_set is None:
        selection_set = operation.selection_set
    fields = collect_fields(
        exe_context, type_, selection_set, DefaultOrderedDict(list), set()
    )
    try:
        prefetch_fn = getattr(type_.graphene_type, "prefetch_fn")
    except AttributeError:
        prefetch_fn = None
    for response_name, field_asts in fields.items():
        # todo: 这里可能有bug
        field_ast = field_asts[0]
        field_name = field_ast.name.value
        try:
            field_def = get_field_def(exe_context.schema, type_, field_name)
        except:
            field_def = None
        path_name = SKIP
        if prefetch_fn:
            try:
                # 在 prefetch_fn 中进行类似于select_related prefetch_related等操作
                # 告诉orm应该加载关系
                # 返回的东西会被拼凑到path里面，如果返回SKIP，那么不会拼路径，如果不返回，那么字段名将拼凑到路径中
                new_action_id = action_id

                def set_action_id(x):
                    nonlocal new_action_id
                    new_action_id = x

                def add_prefetch_info(x):
                    exe_context.context_value["prefetch"][action_id].append(x)

                path_name = prefetch_fn(action_id=action_id, prefetch_name=field_name,
                                        prefetch_field_def=field_def, path=path,
                                        add_prefetch_info=add_prefetch_info,
                                        set_action_id=set_action_id)
            except:
                traceback.print_exc()
        if field_def and field_ast.selection_set:
            if path_name == SKIP:
                new_path = path
            else:
                new_path = path + [path_name]
            resolve_prefetch(exe_context, operation, root_type,
                             field_def.type, new_path, field_ast.selection_set, new_action_id)


# 参考 graphql.execution.executor.execute
# 对这个函数适当修改,使得resolve_prefetch函数生效
def execute(
        schema,  # type: GraphQLSchema
        document_ast,  # type: Document
        root_value=None,  # type: Any
        context_value=None,  # type: Optional[Any]
        variable_values=None,  # type: Optional[Any]
        operation_name=None,  # type: Optional[str]
        executor=None,  # type: Any
        middleware=None,  # type: Optional[Any]
        allow_subscriptions=False,  # type: bool
        **options  # type: Any
):
    # type: (...) -> Awaitable[ExecutionResult]

    if root_value is None and "root" in options:
        warnings.warn(
            "The 'root' alias has been deprecated. Please use 'root_value' instead.",
            category=DeprecationWarning,
            stacklevel=2,
        )
        root_value = options["root"]
    if context_value is None and "context" in options:
        warnings.warn(
            "The 'context' alias has been deprecated. Please use 'context_value' instead.",
            category=DeprecationWarning,
            stacklevel=2,
        )
        context_value = options["context"]
    if variable_values is None and "variables" in options:
        warnings.warn(
            "The 'variables' alias has been deprecated. Please use 'variable_values' instead.",
            category=DeprecationWarning,
            stacklevel=2,
        )
        variable_values = options["variables"]
    assert schema, "Must provide schema"
    assert isinstance(schema, GraphQLSchema), (
            "Schema must be an instance of GraphQLSchema. Also ensure that there are "
            + "not multiple versions of GraphQL installed in your node_modules directory."
    )

    if middleware:
        if not isinstance(middleware, MiddlewareManager):
            middleware = MiddlewareManager(*middleware)

        assert isinstance(middleware, MiddlewareManager), (
            "middlewares have to be an instance"
            ' of MiddlewareManager. Received "{}".'.format(middleware)
        )

    # 只能采用协程执行器
    if executor is None:
        executor = AsyncioExecutor()
    assert isinstance(executor, AsyncioExecutor)

    # 初始化 context value 的结构
    if context_value is None:
        context_value = {}

    context_value.setdefault("prefetch", defaultdict(list))

    exe_context = ExecutionContext(
        schema,
        document_ast,
        root_value,
        context_value,
        variable_values or {},
        operation_name,
        executor,
        middleware,
        allow_subscriptions,
    )

    def promise_executor(v):
        # type: (Optional[Any]) -> Union[Dict, Promise[Dict], Observable]
        return execute_operation(exe_context, exe_context.operation, root_value)

    def on_rejected(error):
        # type: (Exception) -> None
        exe_context.errors.append(error)
        return None

    def on_resolve(data):
        # type: (Union[None, Dict, Observable]) -> Union[ExecutionResult, Observable]
        if isinstance(data, Observable):
            return data

        if not exe_context.errors:
            return ExecutionResult(data=data)

        return ExecutionResult(data=data, errors=exe_context.errors)

    def prefetch(data):
        resolve_prefetch(exe_context, exe_context.operation, root_value)
        return data

    if exe_context.operation.operation == 'query':
        promise = Promise.resolve(None).then(prefetch).then(promise_executor).catch(on_rejected).then(on_resolve)
    else:
        promise = Promise.resolve(None).then(promise_executor).catch(on_rejected).then(on_resolve)

    # 类似于调用 executor.wait_until_finished
    # 但是 executor.wait_until_finished 要求当前线程没有loop
    async def wait_until_finished():
        while executor.futures:
            futures = executor.futures
            executor.futures = []
            await asyncio.gather(*tuple(futures))
            return await promise

    return wait_until_finished()


# 和 graphql.execution.executor.execute_and_validate 相同
# 但是它最后调用的execute函数被覆盖了
def execute_and_validate(
        schema,  # type: GraphQLSchema
        document_ast,  # type: Document
        *args,  # type: Any
        **kwargs  # type: Any
):
    # type: (...) -> Awaitable[ExecutionResult]
    do_validation = kwargs.get("validate", True)
    if do_validation:
        validation_errors = validate(schema, document_ast)
        if validation_errors:
            return Promise.resolve(ExecutionResult(errors=validation_errors, invalid=True))

    return execute(schema, document_ast, *args, **kwargs)


class MyGraphQLBackend(GraphQLCoreBackend):

    # 和父类相同，但是execute_and_validate方法被覆盖
    def document_from_string(self, schema, document_string):
        # type: (GraphQLSchema, Union[Document, str]) -> GraphQLDocument
        if isinstance(document_string, ast.Document):
            document_ast = document_string
            document_string = print_ast(document_ast)
        else:
            assert isinstance(
                document_string, string_types
            ), "The query must be a string"
            document_ast = parse(document_string)
        return GraphQLDocument(
            schema=schema,
            document_string=document_string,
            document_ast=document_ast,
            execute=partial(
                execute_and_validate, schema, document_ast, **self.execute_params
            ),
        )
