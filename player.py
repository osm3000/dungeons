from entity import Component, Entity
from actor import Actor
from actions import MoveAction, PickupAction, WaitAction, DropAction
from blocker import Blocker
from fight import Fighter
from fov import FOV
from health import Health
from inventory import Inventory
from command import Command
from position import Position, Movement
from render import Renderable
from temp import player_tex


class Player(Component):

    COMPONENT_NAME = 'player'


def is_player(entity):
    return entity.has(Player)


def create_player(x, y):
    return Entity(
        Player(),
        Position(x, y, Position.ORDER_PLAYER),
        Actor(100, player_act),
        FOV(10),
        Movement(),
        Renderable(player_tex),
        Blocker(blocks_movement=True),
        Health(100),
        Fighter(1, 0),
        Inventory(),
    )


def player_act(player, level, game):
    command = game.get_command()

    if command.name == Command.MOVE:
        return MoveAction(*command.data)
    elif command.name == Command.PICKUP:
        return PickupAction()
    elif command.name == Command.DROP:
        return DropAction()

    return WaitAction()
