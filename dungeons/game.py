import random

import greenlet
import pyglet
from pyglet.window import key
from pyglet import gl

from dungeons.level import Level, LevelObject, Actor, Movement, Renderable, FOV
from dungeons.level_generator import LevelGenerator, TILE_EMPTY, TILE_WALL, TILE_FLOOR
from dungeons.temp import monster_tex, dungeon_tex, wall_tex_row, floor_tex, player_tex
from eight2empire import TRANSITION_TILES


class GameExit(Exception):
    pass


class Game(object):

    EVT_KEY_PRESS = 'key-press'

    def __init__(self):
        self._g_root = greenlet.getcurrent()
        self._g_mainloop = greenlet.greenlet(self.gameloop)
        self._waiting_event = None

    def _add_monsters(self):
        for room in self.level.rooms:
            for i in xrange(random.randint(0, 5)):
                x = random.randrange(room.x, room.x + room.size_x)
                y = random.randrange(room.y, room.y + room.size_y)

                if (x, y) in self.level.objects and self.level.objects[x, y]:
                    continue

                monster = LevelObject(Actor(100, monster_act), Movement(), Renderable(monster_tex))
                monster.blocks_movement = True
                self.level.add_object(monster, x, y)

    def _render_level(self):
        self._level_sprites = {}
        for y in xrange(self.level.size_y):
            for x in xrange(self.level.size_x):
                tile = self.level.get_tile(x, y)
                if tile == TILE_WALL:
                    tex = self._get_transition_tile(x, y)
                    sprite = pyglet.sprite.Sprite(tex, x * 8, y * 8)
                elif tile == TILE_FLOOR:
                    sprite = pyglet.sprite.Sprite(floor_tex, x * 8, y * 8)
                else:
                    sprite = None
                self._level_sprites[x, y] = sprite

    def _is_wall(self, x, y):
        if not self.level.in_bounds(x, y):
            return True
        return self.level.get_tile(x, y) in (TILE_WALL, TILE_EMPTY)

    def _get_transition_tile(self, x, y):
        n = 1
        e = 2
        s = 4
        w = 8
        nw = 128
        ne = 16
        se = 32
        sw = 64

        v = 0
        if self._is_wall(x, y + 1):
            v |= n
        if self._is_wall(x + 1, y):
            v |= e
        if self._is_wall(x, y - 1):
            v |= s
        if self._is_wall(x - 1, y):
            v |= w
        if self._is_wall(x - 1, y + 1):
            v |= nw
        if self._is_wall(x + 1, y + 1):
            v |= ne
        if self._is_wall(x - 1, y - 1):
            v |= sw
        if self._is_wall(x + 1, y - 1):
            v |= se

        if v not in TRANSITION_TILES:
            v &= 15

        return dungeon_tex[wall_tex_row, TRANSITION_TILES[v]]

    def gameloop(self):
        self.level = Level(self, 70, 50)
        generator = LevelGenerator(self.level)
        generator.generate()

        self._render_level()

        self._add_monsters()

        self.player = LevelObject(Actor(100, player_act), FOV(10), Movement(), Renderable(player_tex))
        self.player.blocks_movement = True
        room = random.choice(self.level.rooms)
        self.level.add_object(self.player, room.x + room.size_x / 2, room.y + room.size_y / 2)
        self.player.fov.update_light()

        while True:
            self.level.tick()

    def start(self):
        self._switch_to_gameloop()

    def wait_key_press(self):
        return self._g_root.switch(Game.EVT_KEY_PRESS)

    def _switch_to_gameloop(self, *data):
        self._waiting_event = self._g_mainloop.switch(*data)

    def on_draw(self):
        gl.glClear(gl.GL_COLOR_BUFFER_BIT)

        for x, y in self.player.fov.lightmap:
            self._level_sprites[x, y].draw()

            sprite = None

            if (x, y) in self.level.objects and len(self.level.objects[x, y]) > 0:
                for obj in self.level.objects[x, y]:
                    if hasattr(obj, Renderable.component_name):
                        sprite = obj.renderable.sprite
                        break

            if sprite is not None:
                gl.glPushMatrix()
                gl.glTranslatef(x * 8, y * 8, 0)
                sprite.draw()
                gl.glPopMatrix()


    def on_key_press(self, sym, mod):
        if self._waiting_event == Game.EVT_KEY_PRESS:
            self._switch_to_gameloop(sym, mod)


def player_act(actor):
    player = actor.owner
    sym, mod = player.level.game.wait_key_press()
    if sym == key.NUM_8:
        player.movement.move(0, 1)
    elif sym == key.NUM_2:
        player.movement.move(0, -1)
    elif sym == key.NUM_4:
        player.movement.move(-1, 0)
    elif sym == key.NUM_6:
        player.movement.move(1, 0)
    elif sym == key.NUM_7:
        player.movement.move(-1, 1)
    elif sym == key.NUM_9:
        player.movement.move(1, 1)
    elif sym == key.NUM_1:
        player.movement.move(-1, -1)
    elif sym == key.NUM_3:
        player.movement.move(1, -1)
    return 100


def monster_act(actor):
    dx = random.randint(-1, 1)
    dy = random.randint(-1, 1)
    actor.owner.movement.move(dx, dy)
    return 100