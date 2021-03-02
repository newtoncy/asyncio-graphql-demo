#!/usr/bin/env python
# -*- encoding: utf-8 -*-
"""
@Author  :   王超逸
@File    :   graphene_model_base.py
@Time    :   2021/2/23 10:28
@Desc    :
"""
import traceback
from copy import copy
from functools import partial
from typing import Type, Awaitable, AsyncIterable, Callable, List, Dict

from graphene import ObjectType, Int, String, Field, List as GqlList
from graphene.types.base import BaseType
from graphene.types.mountedtype import MountedType
from graphene.types.structures import Structure
from graphene.types.unmountedtype import UnmountedType
from graphene.utils.subclass_with_meta import SubclassWithMeta_Meta
from tortoise import Model
from tortoise.queryset import QuerySet

from graphene_backend import SKIP

from collections import namedtuple
from uuid import uuid4

PrefetchPath = namedtuple("PrefetchPath", ("related_name", "orm_type"))
PrefetchInfo = namedtuple("PrefetchInfo", ("prefetch_path", "orm_type"))

def to_underline(name):
    assert name
    words = []
    start = 0
    for i in range(1, len(name)):
        if name[i].isupper():
            words.append(name[start:i])
            start = i
    words.append(name[start:])
    return "_".join([i.lower() for i in words])

def to_camel(name: str):
    s = "".join([i.capitalize() for i in name.split("_")])
    return s[0].lower()+s[1:]


class GrapheneModelObjectMeta(SubclassWithMeta_Meta):

    @classmethod
    def get_resolve_from_base(mcs, name, bases, default=None):
        for i in bases:
            if hasattr(i, name):
                return getattr(i, name)
        return default

    def __new__(mcs, name, bases, ns, **kwargs):
        resolve_fn = ns.get("resolve", mcs.get_resolve_from_base("resolve", bases))
        new_ns: dict = copy(ns)
        for k, v in ns.items():
            if resolve_fn is not None:
                if isinstance(v, BaseType) or isinstance(v, MountedType) \
                        or isinstance(v, UnmountedType) or isinstance(v, Structure):
                    new_ns.setdefault(f"resolve_{k}", partial(resolve_fn, k))
        cls = super().__new__(mcs, name, bases, new_ns, **kwargs)
        return cls


class GrapheneModelObject(ObjectType, metaclass=GrapheneModelObjectMeta):
    model: Type[Model]

    @classmethod
    async def resolve(cls, item, parent, info, **kwargs):

        if not isinstance(parent, Model) or item not in parent._meta.fields:
            value = None
            try:
                # 如果是类似字典的，那么使用in操作
                if item in parent:
                    value = parent[item]
            except TypeError:
                # 如果使用in关键字发生异常，那么尝试取属性
                try:
                    if hasattr(parent, item):
                        value = getattr(parent, item)
                except:
                    traceback.print_exc()
            except:
                traceback.print_exc()
            return value

        meta_info = parent._meta
        if item in meta_info.fields_db_projection:
            # 这种字段和数据库字段对应，可以直接取得值
            return getattr(parent, item)
        elif item in meta_info.fetch_fields:
            # 这种字段可能需要加载
            value = getattr(parent, item)
            if not isinstance(value, QuerySet):
                if isinstance(value, Awaitable):
                    return await value
                return value
            else:
                # 如果是查询集，那分情况讨论
                if item in meta_info.o2o_fields or item in meta_info.fk_fields:
                    # 一对一或者外键
                    if isinstance(value, Awaitable):
                        return await value
                    return value
                elif item in meta_info.backward_fk_fields or item in meta_info.m2m_fields:
                    if isinstance(value, AsyncIterable):
                        return [i async for i in value]
                    return list(value)
                assert False, "不该执行到这里"
        assert False, "不该执行到这里"

    @classmethod
    def prefetch_fn(cls, action_id, prefetch_name, prefetch_field_def,
                    path: List[PrefetchPath], add_prefetch_info, set_action_id):
        if hasattr(cls, f"prefetch_{prefetch_name}"):
            return getattr(cls, f"prefetch_{prefetch_name}")(prefetch_name, prefetch_field_def, path)

        meta_info = cls.model._meta
        if prefetch_name not in meta_info.fetch_fields:
            return SKIP

        name_path = [i.related_name for i in path]
        if path:
            root = path[0].orm_type
        else:
            root = cls.model
        prefetch_path = "__".join([to_underline(i) for i in name_path + [prefetch_name]])
        add_prefetch_info(PrefetchInfo(prefetch_path, root))
        return PrefetchPath(prefetch_name, cls.model)


class BaseCURD:
    filter_args: Dict[str, dict] = {
        "page": {"type": Int, "default_value": 0},
        "page_size": {"type": Int, "default_value": 30}
    }

    query_set: QuerySet = ...
    model_object: GrapheneModelObject = ...
    name: str = ...

    @classmethod
    def wrap_resolver(cls, func: Callable):
        func.action_id = id(func)
        return func

    @classmethod
    def get_name(cls):
        if cls.name is ...:
            return cls.model_object.model.__name__
        return cls.name

    @classmethod
    def get_underline_name(cls):
        name = cls.get_name()
        return to_underline(name)

    @classmethod
    def do_prefetch(cls, query_set, prefetch: List[PrefetchInfo]):
        ret = query_set
        for i in prefetch:
            if i.orm_type is query_set.model:
                ret = query_set.prefetch_related(i.prefetch_path)
                print(f"prefetch {query_set.model} {i.prefetch_path}")
        return ret

    @classmethod
    def get_query_set(cls, prefetch=None):
        if cls.query_set is ...:
            assert hasattr(cls.model_object, "model")
            qs = cls.model_object.model.all()
        else:
            qs = cls.query_set
        if prefetch is not None:
            return cls.do_prefetch(qs, prefetch)
        return qs

    @classmethod
    def get_list_args(cls):
        ret = {}
        for k, v in cls.filter_args.items():
            args = {}
            if "default_value" in v:
                args["default_value"] = v["default_value"]
            ret[k] = v.get("type", String)(**args)
        return ret

    @classmethod
    def get_list_def(cls):
        return Field(GqlList(cls.model_object), args=cls.get_list_args())

    @classmethod
    def get_retrieve_def(cls):
        return Field(cls.model_object, pk=Int())

    @classmethod
    def get_count_def(cls):
        return Int(args=cls.get_list_args())

    @classmethod
    def get_all_allow_filter_args(cls):
        ret = set()
        for k, v in cls.filter_args.items():
            for suffix in set(v.get("suffix", [])) | {""}:
                ret.add(k + suffix)
        return ret

    @classmethod
    def filter_query_set(cls, prefetch=None, *_, page=0, page_size=30, **kwargs):
        assert not _, "奇怪的位置参数增加了"
        filter_args = {}
        allow = cls.get_all_allow_filter_args()
        for k in kwargs:
            if k in allow:
                filter_args[k] = kwargs[k]
        return cls.get_query_set(prefetch).filter(**filter_args).limit(page_size).offset(page * page_size)

    @classmethod
    def build_list_fn(cls) -> Callable[..., Awaitable[List[Model]]]:
        @cls.wrap_resolver
        async def fn(parent, info, **kwargs):
            return [i async for i in cls.filter_query_set(info.context.get("prefetch", {}).get(fn.action_id), **kwargs)]

        return fn

    @classmethod
    def build_retrieve_fn(cls) -> Callable[..., Awaitable[Model]]:
        @cls.wrap_resolver
        async def fn(parent, info, pk):
            return await cls.filter_query_set(
                info.context.get("prefetch", {}).get(fn.action_id)).get(pk=pk)

        return fn

    @classmethod
    def build_count_fn(cls) -> Callable[..., Awaitable[Model]]:
        @cls.wrap_resolver
        async def fn(parent, info, **kwargs):
            count = await cls.filter_query_set(**kwargs).count()
            return count

        return fn

    name_map = {
        "retrieve": ("get_retrieve_def", "build_retrieve_fn"),
        "list": ("get_list_def", "build_list_fn"),
        "count": ("get_count_def", "build_count_fn")
    }

    action_id_map = {}

    @classmethod
    def get_all_action(cls, prefix=None):
        if prefix is None:
            prefix = cls.get_underline_name()

        ret = {}
        action_id_map = {}
        for k, v in cls.name_map.items():
            field_name = f"{cls.get_underline_name()}_{k}"
            define = getattr(cls, v[0])()
            resolve = getattr(cls, v[1])()
            ret[field_name] = define
            ret[f"resolve_{field_name}"] = resolve
            action_id_map[resolve.action_id] = field_name
        cls.action_id_map.update(action_id_map)
        return ret, action_id_map


class ViewSetMeta(SubclassWithMeta_Meta):
    action_name_to_id_map = {}




    def __new__(mcs, name, bases, ns, **kwargs):
        # 说实话，我也不知道这个这个元类本来是用来干嘛的
        # 我重载之后用它来生成一些定义

        curds: List[BaseCURD] = ns.get("curds", [])
        for curd in curds:
            define, action_id = curd.get_all_action()
            ns.update(define)
            mcs.action_name_to_id_map.update({to_camel(v): k for k, v in action_id.items()})
        return super().__new__(mcs, name, bases, ns, **kwargs)


class GraphQLViewSet(ObjectType, metaclass=ViewSetMeta):

    @classmethod
    def prefetch_fn(cls, action_id, prefetch_name, prefetch_field_def, path: List[PrefetchPath],
                    add_prefetch_info, set_action_id):
        assert action_id is None
        set_action_id(cls.action_name_to_id_map[prefetch_name])
        return SKIP

    curds: List[BaseCURD] = []
