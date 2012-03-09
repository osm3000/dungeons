from collections import deque
import random

import greenlet
import pyglet
from pyglet.window import key
from pyglet import gl

from level import Level, LevelObject, Actor, Movement, Renderable, FOV
from level_generator import LevelGenerator, TILE_EMPTY, TILE_WALL, TILE_FLOOR
from temp import monster_tex, dungeon_tex, wall_tex_row, floor_tex, player_tex

from data.eight2empire import WALL_TRANSITION_TILES # load this dynamically, not import as python module


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
                    tex = self._get_wall_transition_tile(x, y)
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

    def _get_wall_transition_tile(self, x, y):
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

        if v not in WALL_TRANSITION_TILES:
            v &= 15

        return dungeon_tex[wall_tex_row, WALL_TRANSITION_TILES[v]]

    def gameloop(self):
        self._message_log = deque(maxlen=5)
        self._messages_layout = pyglet.text.layout.TextLayout(pyglet.text.document.UnformattedDocument(), width=800, multiline=True)
        self._messages_layout.anchor_y = 'top'
        self._messages_layout.y = 600

        self.level = Level(self, 70, 50)
        generator = LevelGenerator(self.level)
        generator.generate()

        self._render_level()

        self._add_monsters()

        self.player = LevelObject(Actor(100, player_act), FOV(10), Movement(), Renderable(player_tex))
        self.player.blocks_movement = True
        self.player.order = 1
        room = random.choice(self.level.rooms)
        self.level.add_object(self.player, room.x + room.size_x / 2, room.y + room.size_y / 2)
        self.player.fov.on_fov_updated = self._on_player_fov_updated
        self.player.fov.update_light()

        self._memento = {}

        self.zoom = 3

        while True:
            self.level.tick()

    def start(self):
        self._switch_to_gameloop()

    def wait_key_press(self):
        return self._g_root.switch(Game.EVT_KEY_PRESS)

    def message(self, text, color=(255, 255, 255, 255)):
        if color:
            text = '{color (%d, %d, %d, %d)}%s' % (color + (text,))
        self._message_log.append(text)
        self._messages_layout.document = pyglet.text.decode_attributed('{}\n'.join(self._message_log))

    def _switch_to_gameloop(self, *data):
        self._waiting_event = self._g_mainloop.switch(*data)

    def _on_player_fov_updated(self, old_lightmap):
        new_lightmap = self.player.fov.lightmap
        keys = set(old_lightmap).union(new_lightmap)

        for key in keys:
            intensity = new_lightmap.get(key, 0)
            v = int((0.3 + intensity * 0.7) * 255)
            self._level_sprites[key].color = (v, v, v)

    def on_draw(self):
        gl.glClear(gl.GL_COLOR_BUFFER_BIT)

        gl.glPushMatrix()

        gl.glScalef(self.zoom, self.zoom, 1)
        gl.glTranslatef(400 / self.zoom - self.player.x * 8, 300 / self.zoom - self.player.y * 8, 0)

        for x in xrange(self.level.size_x):
            for y in xrange(self.level.size_y):

                if self.player.fov.is_in_fov(x, y):
                    level_sprite = self._level_sprites[x, y]
                    level_sprite.draw()

                    renderable = None
                    objects_memento = []

                    if (x, y) in self.level.objects and len(self.level.objects[x, y]) > 0:
                        for obj in self.level.objects[x, y]:
                            if hasattr(obj, Renderable.component_name):
                                renderable = obj.renderable
                                break

                    if renderable is not None:
                        gl.glPushMatrix()
                        gl.glTranslatef(x * 8, y * 8, 0)
                        renderable.sprite.draw()
                        gl.glPopMatrix()
                        if renderable.save_memento:
                            objects_memento.append(renderable.get_memento_sprite())

                    self._memento[x, y] = (level_sprite, objects_memento)

                elif (x, y) in self._memento:
                    level_sprite, object_sprites = self._memento[x, y]
                    level_sprite.draw()

                    for sprite in object_sprites:
                        gl.glPushMatrix()
                        gl.glTranslatef(x * 8, y * 8, 0)
                        sprite.draw()
                        gl.glPopMatrix()

        gl.glPopMatrix()

        self._messages_layout.draw()


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
