import collections
import random

import pyglet

from entity import Component
from fov import InFOV
from generator import LayoutGenerator
from hud import HUD
from light import LightOverlay
from message import LastMessagesView
from position import Position
from temp import floor_tex, get_wall_tex, dungeon_tex
from util import event_property


class TextureGroup(pyglet.graphics.TextureGroup):
    """A batch group that binds texture and sets mag filter to NEAREST not to screw our pretty pixel art"""

    def set_state(self):
        super(TextureGroup, self).set_state()
        pyglet.gl.glTexParameteri(self.texture.target, pyglet.gl.GL_TEXTURE_MAG_FILTER, pyglet.gl.GL_NEAREST)


class ZoomGroup(pyglet.graphics.Group):

    def __init__(self, zoom, parent=None):
        super(ZoomGroup, self).__init__(parent)
        self.zoom = zoom

    def set_state(self):
        pyglet.gl.glPushMatrix()
        pyglet.gl.glScalef(self.zoom, self.zoom, 1)

    def unset_state(self):
        pyglet.gl.glPopMatrix()

    def __eq__(self, other):
        return (
            self.__class__ is other.__class__ and
            self.zoom == other.zoom and
            self.parent == other.parent
        )

    def __hash__(self):
        return hash((self.zoom, self.parent))

    def __repr__(self):
        return '%s(zoom=%d)' % (self.__class__.__name__, self.zoom)


class CameraGroup(pyglet.graphics.Group):

    def __init__(self, window, zoom_factor, focus=None, parent=None):
        super(CameraGroup, self).__init__(parent)
        self.window = window
        self.zoom_factor = zoom_factor
        self.focus = focus

    def set_state(self):
        if self.focus is not None:
            cam_x = self.window.width / 2 - self.focus.x * self.zoom_factor
            cam_y = self.window.height / 2 - self.focus.y * self.zoom_factor
            pyglet.gl.gl.glPushMatrix()
            pyglet.gl.gl.glTranslatef(cam_x, cam_y, 0)

    def unset_state(self):
        if self.focus is not None:
            pyglet.gl.glPopMatrix()

    def __eq__(self, other):
        return (
            self.__class__ is other.__class__ and
            self.window is other.window and
            self.zoom_factor == other.zoom_factor and
            self.parent == other.parent
            )

    def __hash__(self):
        return hash((self.window, self.zoom_factor, self.parent))


class Animation(pyglet.event.EventDispatcher):

    def __init__(self, duration):
        self.elapsed = 0.0
        self.duration = duration
        pyglet.clock.schedule_interval(self._animate, 0.001)

    def cancel(self):
        pyglet.clock.unschedule(self._animate)
        self.dispatch_event('on_finish', self)

    def get_elapsed_ratio(self):
        return self.elapsed / self.duration

    def _animate(self, dt):
        self.elapsed += dt
        if self.elapsed > self.duration:
            self.cancel()
        else:
            self.dispatch_event('on_update', self, dt)

Animation.register_event_type('on_update')
Animation.register_event_type('on_finish')


class Renderable(Component):

    COMPONENT_NAME = 'renderable'

    def __init__(self, image, memorable=False):
        self._image = image
        self.memorable = memorable

    image = event_property('_image', 'image_change')


class LayoutRenderable(Component):

    COMPONENT_NAME = 'layout_renderable'

    def __init__(self, tile):
        self.tile = tile


class RenderSystem(object):

    zoom = 3

    GROUP_LEVEL = pyglet.graphics.OrderedGroup(0)
    GROUP_DIGITS = pyglet.graphics.OrderedGroup(1)
    GROUP_HUD = pyglet.graphics.OrderedGroup(2)

    def __init__(self, level):
        self._level = level
        self._window = level.game.game.window
        self._batch = pyglet.graphics.Batch()
        self._animations = set()
        self._sprites = {}
        self._level_vlist = None
        self._light_overlay = None
        self._last_messages_view = LastMessagesView(level.game.message_log, self._window.width, self._window.height, batch=self._batch, group=self.GROUP_HUD)
        self._hud = HUD(batch=self._batch, group=self.GROUP_HUD)
        self._level_group = ZoomGroup(self.zoom, CameraGroup(self._window, self.zoom, self.GROUP_LEVEL))
        self._digits_group = CameraGroup(self._window, self.zoom, self.GROUP_DIGITS)
        self._memory = collections.defaultdict(list)

    def update_player(self):
        player_sprite = self._sprites[self._level.player]
        self._digits_group.focus = player_sprite
        self._level_group.parent.focus = player_sprite
        self._hud.player = self._level.player

    def render_level(self):
        vertices = []
        tex_coords = []

        for x in xrange(self._level.size_x):
            for y in xrange(self._level.size_y):
                x1 = x * 8
                x2 = x1 + 8
                y1 = y * 8
                y2 = y1 + 8

                for entity in self._level.position_system.get_entities_at(x, y):
                    renderable = entity.get(LayoutRenderable)
                    if renderable:
                        tile = renderable.tile
                        break
                else:
                    continue

                # always add floor, because we wanna draw walls above floor
                vertices.extend((x1, y1, x2, y1, x2, y2, x1, y2))
                tex_coords.extend(floor_tex.tex_coords)

                if tile == LayoutGenerator.TILE_WALL:
                    # if we got wall, draw it above floor
                    tex = get_wall_tex(self._level.get_wall_transition(x, y))
                    vertices.extend((x1, y1, x2, y1, x2, y2, x1, y2))
                    tex_coords.extend(tex.tex_coords)

        group = TextureGroup(dungeon_tex, pyglet.graphics.OrderedGroup(Position.ORDER_FLOOR, self._level_group))
        self._level_vlist = self._batch.add(len(vertices) / 2, pyglet.gl.GL_QUADS, group,
            ('v2i/static', vertices),
            ('t3f/statc', tex_coords),
        )

        group = pyglet.graphics.OrderedGroup(Position.ORDER_PLAYER + 1, self._level_group)
        self._light_overlay = LightOverlay(self._level.size_x, self._level.size_y, self._batch, group)

    def update_light(self, old_lightmap, new_lightmap):
        # for all changed cells
        for key in set(old_lightmap).union(new_lightmap):
            lit = key in new_lightmap
            memory = self._memory[key]

            # if cell is lit, add it to memory and clear all memory sprites, if there are any
            if lit:
                for sprite in memory:
                    sprite.delete()
                memory[:] = []

            # for every entity in cell
            for entity in self._level.position_system.get_entities_at(*key):
                # set in_fov flag
                # TODO: this doesnt belong to rendering, but i don't want to loop twice
                infov = entity.get(InFOV)
                if infov:
                    infov.in_fov = key in new_lightmap

                # if renderable, manage sprites/memory
                renderable = entity.get(Renderable)
                if not renderable:
                    continue

                # if object is lit, show its sprite
                sprite = self._sprites[entity]
                if lit:
                    sprite.visible = True
                else:
                    sprite.visible = False

                    # if it's memorable, add its current image to the memory
                    if renderable.memorable:
                        pos = entity.get(Position)
                        group = pyglet.graphics.OrderedGroup(pos.order, self._level_group)
                        sprite = pyglet.sprite.Sprite(renderable.image, pos.x * 8, pos.y * 8, batch=self._batch, group=group)
                        memory.append(sprite)


        # update light overlay
        self._light_overlay.update_light(new_lightmap, self._memory)

    def add_entity(self, entity):
        image = entity.get(Renderable).image
        pos = entity.get(Position)
        group = pyglet.graphics.OrderedGroup(pos.order, self._level_group)
        sprite = pyglet.sprite.Sprite(image, pos.x * 8, pos.y * 8, batch=self._batch, group=group)
        self._sprites[entity] = sprite
        entity.listen('image_change', self._on_image_change)
        entity.listen('move', self._on_move)

    def remove_entity(self, entity):
        sprite = self._sprites.pop(entity)
        sprite.delete()
        entity.unlisten('image_change', self._on_image_change)
        entity.unlisten('move', self._on_move)

    def _on_image_change(self, entity):
        self._sprites[entity].image = entity.get(Renderable).image

    def _on_move(self, entity, old_x, old_y, new_x, new_y):
        sprite = self._sprites[entity]
        target_x = new_x * 8
        target_y = new_y * 8

        if not sprite.visible:
            # don't animate invisible sprites
            sprite.set_position(target_x, target_y)
        else:
            start_x = sprite.x
            start_y = sprite.y

            anim = Animation(0.25)

            @anim.event
            def on_update(animation, dt, sprite=sprite, dx=(target_x - start_x), dy=(target_y - start_y)):
                ratio = animation.get_elapsed_ratio()
                x = round(start_x + dx * ratio)
                y = round(start_y + dy * ratio)
                sprite.set_position(x, y)

            @anim.event
            def on_finish(animation, sprite=sprite):
                sprite.set_position(target_x, target_y)

            self.add_animation(anim)

    def draw(self):
        self._window.clear()
        pyglet.gl.glEnable(pyglet.gl.GL_BLEND)
        pyglet.gl.glBlendFunc(pyglet.gl.GL_SRC_ALPHA, pyglet.gl.GL_ONE_MINUS_SRC_ALPHA)
        self._batch.draw()

    def dispose(self):
        for anim in tuple(self._animations):
            anim.cancel()
        assert not self._animations

        for sprite in self._sprites.values():
            sprite.delete()
        self._sprites.clear()

        for sprites in self._memory.values():
            for sprite in sprites:
                sprite.delete()
        self._memory.clear()

        if self._level_vlist:
            self._level_vlist.delete()
            self._level_vlist = None

        if self._light_overlay:
            self._light_overlay.delete()
            self._light_overlay = None

        self._last_messages_view.delete()
        self._hud.delete()

    def add_animation(self, animation):
        self._animations.add(animation)
        animation.push_handlers(on_finish=self._animations.remove)

    def animate_damage(self, x, y, dmg):
        x = (x * 8 + random.randint(2, 6)) * self.zoom
        start_y = (y * 8 + random.randint(0, 4)) * self.zoom

        label = pyglet.text.Label('-' + str(dmg), font_name='eight2empire', color=(255, 0, 0, 255),
            x=x, y=start_y, anchor_x='center', anchor_y='bottom',
            batch=self._batch, group=self._digits_group)

        anim = Animation(1)

        @anim.event
        def on_update(animation, dt, label=label, start_y=start_y, zoom=self.zoom):
            ratio = animation.get_elapsed_ratio()
            label.y = start_y + 12 * ratio * zoom
            label.color = (255, 0, 0, int((1.0 - ratio) * 255))

        @anim.event
        def on_finish(animation, label=label):
            label.delete()

        self.add_animation(anim)
