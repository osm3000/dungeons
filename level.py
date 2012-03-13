from bisect import insort_right
from collections import defaultdict, deque
import random

import pyglet
from temp import corpse_texes

from level_generator import TILE_EMPTY, TILE_WALL, TILE_DOOR_CLOSED, TILE_DOOR_OPEN, TILE_FLOOR
from shadowcaster import ShadowCaster


class LevelObject(object):

    order = 0

    def __init__(self, *components):
        self.x = None
        self.y = None
        self.level = None

        for component in components:
            self.add_component(component)

    def add_component(self, component):
        assert isinstance(component, Component)
        if hasattr(self, component.component_name):
            raise RuntimeError('Trying to add duplicate component with name %s: %r' % (component.component_name, component))
        setattr(self, component.component_name, component)
        component.owner = self

    def remove_component(self, name):
        component = getattr(self, name, None)
        if component:
            assert isinstance(component, Component)
            delattr(self, name)
            component.owner = None

    @property
    def name(self):
        if hasattr(self, Description.component_name):
            return self.description.name
        return 'Something'

    def __lt__(self, other):
        if isinstance(other, LevelObject):
            return self.order > other.order
        return True


class Level(object):

    def __init__(self, game, size_x, size_y):
        self.game = game
        self.size_x = size_x
        self.size_y = size_y
        self.grid = [TILE_EMPTY for _ in xrange(size_x * size_y)]
        self.rooms = []
        self.objects = defaultdict(list)
        self.actors = deque()

    def blocks_sight(self, x, y):
        if not self.in_bounds(x, y):
            return True

        if self.get_tile(x, y) == TILE_WALL:
            return True

        if (x, y) in self.objects:
            for object in self.objects[x, y]:
                if hasattr(object, 'blocker') and object.blocker.blocks_sight:
                    return object

        return False

    def blocks_movement(self, x, y):
        if not self.in_bounds(x, y):
            return True

        if self.get_tile(x, y) == TILE_WALL:
            return True

        if (x, y) in self.objects:
            for object in self.objects[x, y]:
                if hasattr(object, 'blocker') and object.blocker.blocks_movement:
                    return object

        return False

    def get_tile(self, x, y):
        return self.grid[y * self.size_x + x]

    def set_tile(self, x, y, tile):
        if tile in (TILE_DOOR_CLOSED, TILE_DOOR_OPEN):
            is_open = (tile == TILE_DOOR_OPEN)
            tile = TILE_FLOOR
            self.add_object(Door(is_open), x, y)

        self.grid[y * self.size_x + x] = tile

    def in_bounds(self, x, y):
        return x >= 0 and x < self.size_x and y >= 0 and y < self.size_y

    def add_object(self, obj, x, y):
        insort_right(self.objects[x, y], obj)
        obj.x = x
        obj.y = y
        obj.level = self

        actor = getattr(obj, Actor.component_name, None)
        if actor:
            self.actors.append(actor)

    def remove_object(self, obj):
        self.objects[obj.x, obj.y].remove(obj)
        obj.x = None
        obj.y = None
        obj.level = None

        actor = getattr(obj, Actor.component_name, None)
        if actor:
            self.actors.remove(actor)

    def move_object(self, obj, x, y):
        self.objects[obj.x, obj.y].remove(obj)
        insort_right(self.objects[x, y], obj)
        obj.x = x
        obj.y = y

    def tick(self):
        if self.actors:
            actor = self.actors[0]
            self.actors.rotate()
            actor.energy += actor.speed
            while actor.energy > 0:
                actor.energy -= actor.act()


class Component(object):

    component_name = None
    owner = None


class Blocker(Component):

    component_name = 'blocker'

    def __init__(self, blocks_sight=False, blocks_movement=False, bump_function=None):
        self.blocks_sight = blocks_sight
        self.blocks_movement = blocks_movement
        if bump_function:
            self.bump = bump_function

    @staticmethod
    def bump(blocker, who):
        if hasattr(who, 'player'):
            who.level.game.message('You bump into %r' % blocker.owner)


class Actor(Component):

    component_name = 'actor'

    def __init__(self, speed, act=None):
        self.energy = 0
        self.speed = speed
        self._act = act

    def act(self):
        if self._act is None:
            raise NotImplementedError()
        return self._act(self)


class FOV(Component):

    component_name = 'fov'

    def __init__(self, radius):
        self.radius = radius
        self.lightmap = {}

    def update_light(self):
        self.lightmap.clear()
        self.lightmap[self.owner.x, self.owner.y] = 1
        caster = ShadowCaster(self.owner.level.blocks_sight, self.set_light)
        caster.calculate_light(self.owner.x, self.owner.y, self.radius)
        self.on_fov_updated()

    def set_light(self, x, y, intensity):
        self.lightmap[x, y] = intensity

    def is_in_fov(self, x, y):
        return self.lightmap.get((x, y), 0) > 0

    def on_fov_updated(self):
        pass


class Movement(Component):

    component_name = 'movement'

    def move(self, dx, dy):
        new_x = self.owner.x + dx
        new_y = self.owner.y + dy

        blocker = self.owner.level.blocks_movement(new_x, new_y)
        if not blocker:
            self.owner.level.move_object(self.owner, new_x, new_y)
        elif isinstance(blocker, LevelObject):
            blocker.blocker.bump(blocker.blocker, self.owner)

        # TODO: use some kind of events/signals
        if hasattr(self.owner, 'fov'):
            self.owner.fov.update_light()


class Player(Component):

    component_name = 'player'


class Renderable(Component):

    component_name = 'renderable'

    def __init__(self, tex, save_memento=False):
        self.sprite = pyglet.sprite.Sprite(tex)
        self.save_memento = save_memento

    def get_memento_sprite(self):
        return self.sprite


class Fighter(Component):

    component_name = 'fighter'

    def __init__(self, max_health, attack, defense):
        self.health = self.max_health = max_health
        self.attack = attack
        self.defense = defense

    def do_attack(self, target):
        dmg = max(0, self.attack - target.fighter.defense)
        target.fighter.take_damage(dmg, self.owner)

    def take_damage(self, damage, source):
        self.health -= damage

        if hasattr(source, Player.component_name):
            source.level.game.message('You hit %s for %d hp' % (self.owner.name, damage))
        if self.health <= 0:
            self.die()

    def die(self):
        self.owner.level.game.message('%s dies' % self.owner.name)
        corpse = LevelObject(Renderable(random.choice(corpse_texes)))
        self.owner.level.add_object(corpse, self.owner.x, self.owner.y)
        self.owner.level.remove_object(self.owner)


class Description(Component):

    component_name = 'description'

    def __init__(self, name):
        self.name = name


from door import Door
