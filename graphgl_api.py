#!/usr/bin/env python
# -*- encoding: utf-8 -*-
"""
@Author  :   王超逸
@File    :   graphgl_api.py
@Time    :   2021/2/25 14:15
@Desc    :   graphgl风格的api
"""

from model import *
from graphene_model_base import BaseCURD, GraphQLViewSet, GrapheneModelObject
from graphene import Int, String, Field, List, Schema


class TeamObject(GrapheneModelObject):
    model = Team
    id = Int()
    name = String()
    events = List(lambda: EventObject)


class EventObject(GrapheneModelObject):
    model = Event
    id = Int()
    name = String()
    tournament = Field(lambda: TournamentObject)
    participants = List(TeamObject)


class TournamentObject(GrapheneModelObject):
    model = Tournament
    id = Int()
    name = String()
    events = List(EventObject)


class TournamentCurd(BaseCURD):
    model_object = TournamentObject


class EventCurd(BaseCURD):
    model_object = EventObject


class TeamCurd(BaseCURD):
    model_object = TeamObject


class DemoViewSet(GraphQLViewSet):
    curds = [TournamentCurd, EventCurd, TeamCurd]


schema = Schema(query=DemoViewSet)
print(schema)
